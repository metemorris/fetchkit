"""
Lobsters fetcher.

Fetches stories from lobste.rs via its public JSON endpoints (no auth):
``/hottest.json``, ``/newest.json``, or ``/t/<tag>.json`` for a single tag.
"""

import logging
from typing import Any, Optional

from fetchkit.http import get_default_client
from fetchkit.schemas.post import Post, Source
from fetchkit.schemas.fetcher import LobstersFetchConfig, FetcherConfig
from fetchkit.fetchers.base import FetcherResult
from fetchkit.fetchers.registry import register_fetcher
from fetchkit.fetchers.suggest_registry import register_suggester

logger = logging.getLogger(__name__)

BASE_URL = "https://lobste.rs"
SOURCE_NAME = Source.LOBSTERS
DEFAULT_TIMEOUT_S = 15


def _endpoint(config: LobstersFetchConfig) -> str:
    """Resolve the Lobsters JSON endpoint for the config."""
    if config.tag:
        return f"{BASE_URL}/t/{config.tag}.json"
    return f"{BASE_URL}/{config.listing}.json"


def _submitter(story: dict[str, Any]) -> Optional[str]:
    """Extract the submitter username (the API shape has varied over time)."""
    user = story.get("submitter_user")
    if isinstance(user, dict):
        return user.get("username")
    if isinstance(user, str):
        return user
    return None


def _story_to_post(story: dict[str, Any]) -> Post:
    """Convert a Lobsters story payload into a canonical Post."""
    short_id = story.get("short_id") or story.get("short_id_url") or ""
    comments_url = story.get("comments_url") or f"{BASE_URL}/s/{short_id}"
    external_url = story.get("url") or comments_url
    return Post(
        id=str(short_id),
        source=SOURCE_NAME,
        title=story.get("title"),
        text=story.get("description") or None,
        url=external_url,
        author=_submitter(story),
        score=story.get("score"),
        comment_count=story.get("comment_count"),
        created_at=story.get("created_at"),
        source_url=comments_url,
        metadata={"tags": story.get("tags") or []},
    )


def fetch_posts(config: LobstersFetchConfig) -> list[Post]:
    """Fetch stories from a Lobsters listing."""
    client = get_default_client()
    resp = client.get(_endpoint(config), timeout=DEFAULT_TIMEOUT_S)
    resp.raise_for_status()

    posts: list[Post] = []
    for story in resp.json():
        post = _story_to_post(story)
        if config.start_time is not None and config.end_time is not None:
            if post.created_at is None or not (config.start_time <= post.created_at <= config.end_time):
                continue
        posts.append(post)
    return posts[: config.max_items]


@register_suggester("lobsters")
def suggest(*, query: Optional[str] = None, limit: int = 100, **kwargs: Any) -> list[dict[str, Any]]:
    """Discoverability for Lobsters: list available tags from ``/tags.json`` (no auth)."""
    client = get_default_client()
    resp = client.get(f"{BASE_URL}/tags.json", timeout=DEFAULT_TIMEOUT_S)
    resp.raise_for_status()
    out: list[dict[str, Any]] = []
    for t in resp.json():
        tag = t.get("tag")
        if query and query.lower() not in (tag or "").lower():
            continue
        out.append({
            "tag": tag,
            "description": t.get("description"),
            "category": t.get("category"),
        })
    return out[:limit]


@register_fetcher("lobsters")
def fetch(config: FetcherConfig) -> FetcherResult:
    """Fetcher protocol implementation for Lobsters."""
    if not isinstance(config, LobstersFetchConfig):
        raise ValueError(f"Invalid config type for lobsters fetcher: {type(config)}")
    try:
        return FetcherResult(posts=fetch_posts(config), errors=[])
    except Exception as e:
        return FetcherResult(posts=[], errors=[e])
