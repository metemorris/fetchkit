"""
RSS/Atom fetcher.

Fetches entries from one or more RSS/Atom feeds using feedparser.
Returns canonical Post objects.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, cast
from urllib.parse import urlparse
import feedparser

from fetchkit.http import get_default_client
from fetchkit.schemas.post import Post, Source
from fetchkit.schemas.fetcher import RSSFetchConfig, RSSFeedDescriptor, FetcherConfig
from fetchkit.fetchers.base import FetcherResult
from fetchkit.fetchers.registry import register_fetcher

logger = logging.getLogger(__name__)

SOURCE_NAME = Source.RSS
DEFAULT_TIMEOUT_S = 10


class RSSFeedFetchError(Exception):
    """Wraps a per-feed fetch error with the feed URL context."""

    def __init__(self, feed_url: str, cause: Exception):
        """Capture the feed URL and original exception for downstream error reporting."""
        super().__init__(f"Failed to fetch feed {feed_url}: {cause}")
        self.feed_url = feed_url
        self.cause = cause


@dataclass
class RSSFetchResult:
    """Aggregated RSS fetch result with successful posts and per-feed errors."""

    posts: list[Post]
    errors: list[RSSFeedFetchError] = field(default_factory=list)


def _generate_stable_id(entry: Any, feed_url: str) -> str:
    """
    Generate a deterministic stable ID for an RSS entry.
    Priority:
    1. entry.id (GUID)
    2. entry.link
    3. hash of (title + feed_url + published)
    """
    feed_hash = hashlib.sha256(feed_url.encode()).hexdigest()[:8]

    if hasattr(entry, 'id') and entry.id:
        return f"{feed_hash}:{entry.id}"

    if hasattr(entry, 'link') and entry.link:
        return f"{feed_hash}:{entry.link}"

    # Fallback to hash
    title = getattr(entry, 'title', "")
    published = getattr(entry, 'published', "")
    content = f"{title}|{feed_url}|{published}"
    return f"{feed_hash}:{hashlib.sha256(content.encode()).hexdigest()}"


def _parse_date(entry: Any) -> Optional[datetime]:
    """
    Extract and parse date from entry.
    Prefer published, fallback to updated.
    Returns UTC datetime or None.
    """
    for attr in ['published_parsed', 'updated_parsed', 'created_parsed']:
        if hasattr(entry, attr):
            struct_time = getattr(entry, attr)
            if struct_time:
                # feedparser returns time.struct_time which can be converted to datetime
                return datetime(
                    year=struct_time[0],
                    month=struct_time[1],
                    day=struct_time[2],
                    hour=struct_time[3],
                    minute=struct_time[4],
                    second=struct_time[5],
                    tzinfo=timezone.utc,
                )
    return None


def _get_content(entry: Any, include_content: bool) -> Optional[str]:
    """Extract best-effort content/summary."""
    if not include_content:
        return None

    if hasattr(entry, "content"):
        content = getattr(entry, "content")
        if content:
            first = content[0]
            if isinstance(first, dict):
                value = first.get("value")
                if value is not None:
                    return str(value)
            else:
                value = getattr(first, "value", None)
                if value is not None:
                    return str(value)
    summary = getattr(entry, "summary", None)
    if summary:
        return str(summary)
    return ""


def normalize_entry(
    entry: Any,
    feed_descriptor: RSSFeedDescriptor,
    include_content: bool = True,
) -> Optional[Post]:
    """Normalize a feedparser entry into a canonical Post."""
    created_at = _parse_date(entry)
    if not created_at:
        # Exclusion rule: Skip entries without valid timestamps
        return None

    source_id = _generate_stable_id(entry, feed_descriptor.url)

    return Post(
        id=source_id,
        source=SOURCE_NAME,
        title=getattr(entry, 'title', None),
        text=_get_content(entry, include_content),
        url=getattr(entry, 'link', None),
        author=getattr(entry, 'author', None),
        score=None,  # RSS doesn't typically have scores
        comment_count=None,
        created_at=created_at,
        source_url=getattr(entry, 'link', ""),  # For RSS, the source_url is usually the link
        comments=[],
    )


def fetch_posts_with_errors(config: RSSFetchConfig) -> RSSFetchResult:
    """
    Fetch posts from multiple RSS/Atom feeds between start_time and end_time.

    Args:
        config: RSSFetchConfig with multiple feeds and time range

    Returns:
        RSSFetchResult containing deduped/sorted posts and per-feed errors.
    """
    all_posts: dict[str, Post] = {}
    errors: list[RSSFeedFetchError] = []
    client = get_default_client()

    for feed_desc in config.feeds:
        try:
            feed_url = feed_desc.url
            local_path: Optional[Path] = None
            if config.allow_local_files:
                if feed_url.startswith("file://"):
                    candidate = Path(feed_url[7:])
                    if candidate.exists():
                        local_path = candidate
                else:
                    candidate = Path(feed_url)
                    if candidate.exists():
                        local_path = candidate
            elif urlparse(feed_url).scheme not in ("http", "https"):
                # Security: only http(s) feeds are permitted unless the caller
                # explicitly opts into local file reads via allow_local_files.
                raise ValueError(
                    f"Local/file feeds are disabled for '{feed_url}'. Set "
                    "'allow_local_files: true' on this rss fetcher to read local paths."
                )

            if local_path:
                feed = feedparser.parse(str(local_path))
            else:
                response = client.get(feed_url, timeout=DEFAULT_TIMEOUT_S)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
            if feed.bozo:
                logger.warning(f"Feed {feed_desc.url} is malformed: {feed.bozo_exception}")
                # We still try to process it as feedparser often extracts what it can

            feed_posts_count = 0
            for post_entry in feed.entries:
                if feed_posts_count >= config.max_items_per_feed:
                    break

                post = normalize_entry(post_entry, feed_desc, config.include_content)
                if not post:
                    continue

                # Time window filtering (datetimes are UTC-normalized by the schemas)
                s_t = config.start_time
                e_t = config.end_time
                if s_t is not None and e_t is not None:
                    assert post.created_at is not None
                    if not (s_t <= post.created_at <= e_t):
                        continue

                # Dedup by post.id
                if post.id not in all_posts:
                    all_posts[post.id] = post
                    feed_posts_count += 1

                if len(all_posts) >= config.max_total_items:
                    break

            if len(all_posts) >= config.max_total_items:
                break

        except Exception as e:
            logger.error(f"Failed to fetch feed {feed_desc.url}: {e}")
            errors.append(RSSFeedFetchError(feed_desc.url, e))
            # Continue to next feed
            continue

    # Sort by created_at descending, then by stable ID for determinism
    sorted_posts = sorted(
        all_posts.values(),
        key=lambda x: (x.created_at, x.id),
        reverse=True,
    )

    return RSSFetchResult(posts=sorted_posts[:config.max_total_items], errors=errors)


def fetch_posts(config: RSSFetchConfig) -> list[Post]:
    """Compatibility wrapper returning only successful posts."""
    return fetch_posts_with_errors(config).posts


@register_fetcher("rss")
def fetch(config: FetcherConfig) -> FetcherResult:
    """
    Fetcher protocol implementation for RSS.
    """
    if not isinstance(config, RSSFetchConfig):
        raise ValueError(f"Invalid config type for rss fetcher: {type(config)}")

    try:
        result = fetch_posts_with_errors(config)
        # Convert RSSFeedFetchError to generic Exception if needed,
        # but FetcherResult.errors expects list[Exception], so it's fine.
        return FetcherResult(posts=result.posts, errors=cast("list[Exception]", result.errors))
    except Exception as e:
        return FetcherResult(posts=[], errors=[e])
