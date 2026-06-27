import threading
import time
import pytest
from fetchkit.http.rate_limit import RateLimiter


def test_min_interval_derived_from_calls_per_second() -> None:
    rl = RateLimiter(calls_per_second=10.0)
    assert rl.min_interval.total_seconds() == pytest.approx(0.1)


def test_acquire_does_not_block_first_call() -> None:
    rl = RateLimiter(calls_per_second=1000.0)
    start = time.monotonic()
    rl.acquire("https://example.com/a")
    assert time.monotonic() - start < 0.05


def test_repeated_same_host_calls_enforce_spacing() -> None:
    rl = RateLimiter(calls_per_second=100.0)  # 0.01s interval
    rl.acquire("https://example.com/a")
    start = time.monotonic()
    rl.acquire("https://example.com/b")
    elapsed = time.monotonic() - start
    # Same host (example.com), different paths -> should wait ~min_interval.
    assert elapsed >= 0.005


def test_different_hosts_are_independent() -> None:
    rl = RateLimiter(calls_per_second=2.0)  # 0.5s interval
    rl.acquire("https://a.example.com/x")
    start = time.monotonic()
    rl.acquire("https://b.example.com/x")
    elapsed = time.monotonic() - start
    # Different hosts should not block.
    assert elapsed < 0.1


def test_concurrent_different_hosts_do_not_block_each_other() -> None:
    """Two threads hitting different hosts must not serialize on the sleep.

    With the sleep held under the lock this took ~2 intervals; reserving the slot
    and sleeping outside the lock lets both hosts wait their interval in parallel,
    so total wall time stays close to a single interval.
    """
    rl = RateLimiter(calls_per_second=4.0)  # 0.25s interval
    # Prime each host so the *second* acquire on each must wait one interval.
    rl.acquire("https://a.example.com/x")
    rl.acquire("https://b.example.com/x")

    def hit(host: str) -> None:
        rl.acquire(f"https://{host}.example.com/y")

    start = time.monotonic()
    threads = [threading.Thread(target=hit, args=(h,)) for h in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start

    # Both waits overlap: ~1 interval, not ~2. Generous upper bound for CI.
    assert elapsed < 0.4


def test_concurrent_same_host_calls_serialize() -> None:
    """Concurrent same-host acquires must still be spaced by min_interval each."""
    rl = RateLimiter(calls_per_second=20.0)  # 0.05s interval
    n = 4

    def hit() -> None:
        rl.acquire("https://same.example.com/x")

    start = time.monotonic()
    threads = [threading.Thread(target=hit) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start

    # n calls to one host -> at least (n-1) intervals of spacing.
    assert elapsed >= (n - 1) * 0.05


def test_invalid_calls_per_second_rejected() -> None:
    with pytest.raises(ValueError):
        RateLimiter(calls_per_second=0.0)
    with pytest.raises(ValueError):
        RateLimiter(calls_per_second=-1.0)
