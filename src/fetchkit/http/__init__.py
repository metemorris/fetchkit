"""HTTP subpackage: shared client with retries, backoff, and rate limiting."""

from fetchkit.http.client import (
    HttpClient,
    get_default_client,
    set_default_client,
    use_client,
)
from fetchkit.http.rate_limit import RateLimiter

__all__ = [
    "HttpClient",
    "RateLimiter",
    "get_default_client",
    "set_default_client",
    "use_client",
]
