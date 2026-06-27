"""
Unified fetcher orchestrator.

Orchestrates fetching from multiple data sources (Hacker News, RSS, etc.)
using a single top-level configuration. Preserves three core invariants:

1. Per-fetcher time windows inherit the global window when omitted.
2. Posts are de-duplicated by ``(source, id)`` (first occurrence wins).
3. Posts are sorted descending by ``(created_at or UTC_MIN, id)`` for determinism.
"""

import logging
from contextlib import nullcontext
from typing import Optional

from fetchkit.schemas.post import Post
from fetchkit.schemas.config import FetchKitConfig
from fetchkit.fetchers.registry import get_fetcher
from fetchkit.utils.time import UTC_MIN
from fetchkit.schemas.collector import CollectorResult
from fetchkit.http import HttpClient, use_client

logger = logging.getLogger(__name__)


def collect_all(
    config: FetchKitConfig,
    verbose: bool = False,
    http_client: Optional[HttpClient] = None,
) -> CollectorResult:
    """
    Collect posts from all enabled data sources.

    Args:
        config: Top-level FetchKitConfig with global time window and fetcher settings.
        verbose: When True, print per-source progress to stdout (off by default for
            library use).
        http_client: Optional shared HTTP client to install for this run. When
            provided, it becomes the active default client used by fetchers for the
            duration of the call. When None and ``config.http`` is set, a client is
            built from it; otherwise the built-in default client is used.

    Returns:
        CollectorResult containing posts and any errors that occurred.
        Callers should check result.has_errors to detect partial failures.
    """
    all_posts: list[Post] = []
    errors: list[tuple[str, Exception]] = []

    # Resolve the HTTP client for this run: the explicit override, else one built
    # from config.http, else None (fall back to the ambient default). When we do
    # have a run-specific client, install it thread-locally for the duration of
    # the run via use_client() so concurrent collect_all() calls never clobber
    # each other or a caller's set_default_client().
    run_client: Optional[HttpClient] = http_client
    if run_client is None and config.http is not None:
        run_client = HttpClient(config.http)
    client_ctx = use_client(run_client) if run_client is not None else nullcontext()

    def _log(msg: str) -> None:
        if verbose:
            print(msg)

    def _record_error(source: str, err: Exception) -> None:
        """Track a source failure and emit matching log/console diagnostics."""
        errors.append((source, err))
        logger.error("Failed to fetch from %s: %s", source, err)
        _log(f"Error: Failed to fetch from {source}: {err}")

    with client_ctx:
        for fetcher_config in config.fetchers:
            if not fetcher_config.enabled:
                continue

            source_name = fetcher_config.type

            try:
                # Inherit global time window if not set
                f_config = fetcher_config.model_copy()
                if f_config.start_time is None:
                    f_config.start_time = config.start_time
                if f_config.end_time is None:
                    f_config.end_time = config.end_time

                fetcher = get_fetcher(f_config.type)
                result = fetcher(f_config)

                msg_name = f_config.name if f_config.name else f_config.type
                _log(f"Fetched {len(result.posts)} posts from {msg_name}")

                all_posts.extend(result.posts)

                for err in result.errors:
                    _record_error(source_name, err)

            except Exception as e:
                _record_error(source_name, e)

    # Dedup by (source, id) for maximum safety
    seen_keys = set()
    unique_posts = []

    for post in all_posts:
        key = (post.source, post.id)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_posts.append(post)

    # Sort by created_at DESC, then by source-specific ID for determinism
    sorted_posts = sorted(
        unique_posts,
        key=lambda x: (x.created_at or UTC_MIN, x.id),
        reverse=True,
    )

    return CollectorResult(posts=sorted_posts, errors=errors)
