"""Simple per-host rate limiting via a minimum-interval gate."""

import threading
import time
from datetime import timedelta
from urllib.parse import urlparse


class RateLimiter:
    """Thread-safe per-host minimum-interval rate limiter.

    Given a target ``calls_per_second``, enforces a minimum spacing between
    consecutive requests to the *same host*. Different hosts are tracked
    independently and do not block each other.
    """

    def __init__(self, calls_per_second: float) -> None:
        if calls_per_second <= 0:
            raise ValueError("calls_per_second must be positive")
        self._min_interval: float = 1.0 / calls_per_second
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, url: str) -> None:
        """Block until a request to the host of ``url`` is permitted."""
        host = self._host_of(url)
        with self._lock:
            now = time.monotonic()
            last = self._last_call.get(host)
            if last is not None:
                elapsed = now - last
                wait = self._min_interval - elapsed
                if wait > 0:
                    time.sleep(wait)
                    now = time.monotonic()
            self._last_call[host] = now

    @staticmethod
    def _host_of(url: str) -> str:
        parsed = urlparse(url)
        return parsed.netloc or url

    @property
    def min_interval(self) -> timedelta:
        """The enforced minimum interval between same-host requests."""
        return timedelta(seconds=self._min_interval)
