"""
Mastodon fetcher.

Fetches statuses from a Mastodon instance's public or hashtag timelines via the
public REST API (``/api/v1/timelines/public`` and ``/api/v1/timelines/tag/<tag>``),
which require no authentication when the instance keeps public preview enabled.
Statuses become canonical ``Post`` objects.
"""

import html
import logging
import re
from typing import Any, Optional

from fetchkit.http import get_default_client
from fetchkit.schemas.post import Post, Source
from fetchkit.schemas.fetcher import MastodonFetchConfig, FetcherConfig
from fetchkit.fetchers.base import FetcherResult
from fetchkit.fetchers.registry import register_fetcher

logger = logging.getLogger(__name__)

SOURCE_NAME = Source.MASTODON
DEFAULT_TIMEOUT_S = 15
PAGE_SIZE = 40  # API maximum per request

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(content: Optional[str]) -> Optional[str]:
    """Convert Mastodon's HTML status content to plain text (no new dependency)."""
    if not content:
        return None
    # Turn block/line breaks into newlines, then drop remaining tags and unescape.
    text = re.sub(r"(?i)</p>|<br\s*/?>", "\n", content)
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip() or None


def _endpoint(config: MastodonFetchConfig) -> str:
    """Resolve the timeline endpoint URL for the config."""
    base = f"https://{config.instance}/api/v1/timelines"
    if config.resource == "tag":
        if not config.tag:
            raise ValueError("mastodon resource 'tag' requires a 'tag'")
        return f"{base}/tag/{config.tag}"
    return f"{base}/public"


def _to_post(status: dict[str, Any], instance: str) -> Post:
    """Convert a Mastodon status payload into a canonical Post."""
    account = status.get("account") or {}
    url = status.get("url") or status.get("uri") or ""
    tags = [t.get("name") for t in status.get("tags", []) if isinstance(t, dict) and t.get("name")]

    metadata: dict[str, Any] = {
        "instance": instance,
        "tags": tags,
        "visibility": status.get("visibility"),
    }
    if status.get("reblogs_count") is not None:
        metadata["reblogs_count"] = status["reblogs_count"]
    if status.get("language"):
        metadata["language"] = status["language"]

    return Post(
        id=str(status.get("id", "")),
        source=SOURCE_NAME,
        text=_strip_html(status.get("content")),
        url=url or None,
        author=account.get("acct"),
        score=status.get("favourites_count"),
        comment_count=status.get("replies_count"),
        created_at=status.get("created_at"),
        source_url=url or f"https://{instance}",
        metadata=metadata,
    )


def fetch_posts(config: MastodonFetchConfig) -> list[Post]:
    """Fetch statuses from a Mastodon public or hashtag timeline."""
    endpoint = _endpoint(config)
    client = get_default_client()
    posts: list[Post] = []
    max_id: Optional[str] = None

    while len(posts) < config.max_items:
        limit = min(PAGE_SIZE, config.max_items - len(posts))
        params: dict[str, Any] = {"limit": limit}
        if config.local:
            params["local"] = "true"
        if max_id is not None:
            params["max_id"] = max_id

        resp = client.get(endpoint, params=params, timeout=DEFAULT_TIMEOUT_S)
        resp.raise_for_status()
        statuses = resp.json()
        if not statuses:
            break

        for status in statuses:
            post = _to_post(status, config.instance)
            if config.start_time is not None and config.end_time is not None:
                if post.created_at is None or not (config.start_time <= post.created_at <= config.end_time):
                    continue
            posts.append(post)

        # A short page means we've reached the end of the timeline.
        if len(statuses) < limit:
            break
        # Paginate using the id of the last status returned (oldest in the page).
        last_id = statuses[-1].get("id")
        if last_id is None or last_id == max_id:
            break
        max_id = str(last_id)

    return posts[: config.max_items]


@register_fetcher("mastodon")
def fetch(config: FetcherConfig) -> FetcherResult:
    """Fetcher protocol implementation for Mastodon."""
    if not isinstance(config, MastodonFetchConfig):
        raise ValueError(f"Invalid config type for mastodon fetcher: {type(config)}")
    try:
        return FetcherResult(posts=fetch_posts(config), errors=[])
    except Exception as e:
        return FetcherResult(posts=[], errors=[e])
