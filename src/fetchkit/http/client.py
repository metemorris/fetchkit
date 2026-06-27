"""Shared HTTP client with connection pooling, retries, backoff, and rate limiting."""

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from fetchkit.http.rate_limit import RateLimiter
from fetchkit.schemas.config import HttpConfig

logger = logging.getLogger(__name__)

# Default pool sizes for the shared session adapter.
_POOL_CONNECTIONS = 10
_POOL_MAXSIZE = 10


class HttpClient:
    """A thin wrapper over :class:`requests.Session` providing:

    - connection pooling via a shared :class:`HTTPAdapter`,
    - configurable per-request timeout,
    - automatic retries with exponential backoff on transient HTTP errors and
      connection failures (honoring ``Retry-After`` on 429/503),
    - optional per-host rate limiting.

    Construct from an :class:`HttpConfig`, or use :meth:`default` for the
    built-in defaults. Fetchers should accept an injected client so tests can
    mock HTTP via the ``responses`` library (which patches ``requests`` at the
    transport layer and is transparent to this client).
    """

    def __init__(self, config: Optional[HttpConfig] = None) -> None:
        self._config = config or HttpConfig()
        self._session = self._build_session(self._config)
        self._rate_limiter: Optional[RateLimiter] = None
        if self._config.rate_limit_per_host is not None:
            self._rate_limiter = RateLimiter(self._config.rate_limit_per_host)

    @classmethod
    def default(cls) -> "HttpClient":
        """Return a client using built-in default settings."""
        return cls(HttpConfig())

    @property
    def config(self) -> HttpConfig:
        """The HTTP configuration this client was built from."""
        return self._config

    @property
    def session(self) -> requests.Session:
        """The underlying requests session (exposed for advanced use/testing)."""
        return self._session

    def get(self, url: str, params: Optional[dict[str, Any]] = None, **kwargs: Any) -> requests.Response:
        """Perform a GET with retries, backoff, timeout, and rate limiting.

        Extra ``kwargs`` are forwarded to :meth:`requests.Session.get` (e.g.
        ``headers``, ``auth``). The configured ``timeout`` is injected unless
        the caller overrides it.
        """
        return self._request("GET", url, params=params, **kwargs)

    def close(self) -> None:
        """Close the underlying session and release pooled connections."""
        self._session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    # ------------------------------------------------------------------ internal

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        cfg = self._config
        kwargs.setdefault("timeout", cfg.timeout)

        max_attempts = cfg.max_retries + 1
        last_exc: Optional[requests.RequestException] = None

        for attempt in range(1, max_attempts + 1):
            if self._rate_limiter is not None:
                self._rate_limiter.acquire(url)

            try:
                response = self._session.request(method, url, **kwargs)
            except requests.ConnectionError as exc:
                last_exc = exc
                if attempt >= max_attempts:
                    raise
                self._sleep_backoff(attempt, url, reason=str(exc))
                continue
            except requests.Timeout as exc:
                last_exc = exc
                if attempt >= max_attempts:
                    raise
                self._sleep_backoff(attempt, url, reason="timeout")
                continue

            if response.status_code in cfg.retry_statuses and attempt < max_attempts:
                wait = self._retry_after(response, attempt)
                logger.debug(
                    "HTTP %d for %s; retrying in %.2fs (attempt %d/%d)",
                    response.status_code, url, wait, attempt, max_attempts,
                )
                time.sleep(wait)
                continue

            return response

        # Exhausted retries on connection errors: re-raise the last exception.
        if last_exc is not None:
            raise last_exc
        # Should be unreachable; return a sentinel to satisfy the type checker.
        raise requests.RequestException("Request failed with no response captured")

    def _sleep_backoff(self, attempt: int, url: str, reason: str) -> None:
        wait = self._backoff_seconds(attempt)
        logger.debug(
            "Transient error for %s (%s); retrying in %.2fs (attempt %d)",
            url, reason, wait, attempt,
        )
        time.sleep(wait)

    def _backoff_seconds(self, attempt: int) -> float:
        return float(self._config.backoff_factor * (2 ** (attempt - 1)))

    def _retry_after(self, response: requests.Response, attempt: int) -> float:
        header = response.headers.get("Retry-After")
        if header is not None:
            try:
                return float(header)
            except ValueError:
                pass
        return self._backoff_seconds(attempt)

    @staticmethod
    def _build_session(config: HttpConfig) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=0,  # retries are handled by HttpClient itself for full control
            connect=0,
            read=0,
            status=0,
            backoff_factor=0,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=_POOL_CONNECTIONS,
            pool_maxsize=_POOL_MAXSIZE,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session


# ---------------------------------------------------------------------------
# Default client resolution
#
# Fetchers resolve their HTTP client via get_default_client() so a single shared
# session/pool is reused across sources. Resolution order:
#
#   1. a thread-local client installed for the current call (see use_client) —
#      this is what the collector installs per run, so concurrent collect_all()
#      calls on different threads are fully isolated and never clobber each other;
#   2. the process-wide default set via set_default_client();
#   3. a lazily-created, shared built-in default.
#
# requests.Session and the RateLimiter are themselves thread-safe, so a single
# HttpClient may safely back multiple threads; only the *selection* of which
# client is active needed isolating. Tests using the ``responses`` library are
# transparent to all of this since ``responses`` patches the urllib3 transport.
# ---------------------------------------------------------------------------
_global_lock = threading.Lock()
_global_client: Optional[HttpClient] = None
_thread_local = threading.local()


def get_default_client() -> HttpClient:
    """Return the active default HTTP client, creating one if none is set."""
    override: Optional[HttpClient] = getattr(_thread_local, "client", None)
    if override is not None:
        return override

    global _global_client
    with _global_lock:
        if _global_client is None:
            _global_client = HttpClient.default()
        return _global_client


def set_default_client(client: Optional[HttpClient]) -> None:
    """Install (or clear, with ``None``) the process-wide default HTTP client.

    A thread-local client installed via :func:`use_client` takes precedence over
    this for the duration of that context.
    """
    global _global_client
    with _global_lock:
        _global_client = client


@contextmanager
def use_client(client: HttpClient) -> Iterator[HttpClient]:
    """Make ``client`` the default for the current thread within this context.

    Isolated per thread, so concurrent runs don't interfere, and restored to the
    previous thread-local value on exit (re-entrant safe).
    """
    previous: Optional[HttpClient] = getattr(_thread_local, "client", None)
    _thread_local.client = client
    try:
        yield client
    finally:
        _thread_local.client = previous
