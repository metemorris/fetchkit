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


def test_invalid_calls_per_second_rejected() -> None:
    with pytest.raises(ValueError):
        RateLimiter(calls_per_second=0.0)
    with pytest.raises(ValueError):
        RateLimiter(calls_per_second=-1.0)
