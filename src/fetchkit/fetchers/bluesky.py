"""
Bluesky fetcher.

Fetches posts from the public Bluesky AppView (https://public.api.bsky.app),
which serves read-only AT Protocol data with no authentication. Supports two
resources: full-text post search (``app.bsky.feed.searchPosts``) and a single
account's feed (``app.bsky.feed.getAuthorFeed``).
"""

import logging
from typing import Any, Optional

from fetchkit.http import get_default_client
from fetchkit.schemas.post import Post, Source
from fetchkit.schemas.fetcher import BlueskyFetchConfig, FetcherConfig
from fetchkit.fetchers.base import FetcherResult
from fetchkit.fetchers.registry import register_fetcher
from fetchkit.fetchers.suggest_registry import register_suggester

logger = logging.getLogger(__name__)

XRPC_BASE = "https://public.api.bsky.app/xrpc"
SOURCE_NAME = Source.BLUESKY
DEFAULT_TIMEOUT_S = 15
PAGE_SIZE = 100  # API maximum for searchPosts / getAuthorFeed


def _post_url(uri: str, handle: Optional[str]) -> str:
    """Build the bsky.app web URL for a post from its at:// URI and author handle."""
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    who = handle or (uri.split("/")[2] if uri.startswith("at://") else "")
    return f"https://bsky.app/profile/{who}/post/{rkey}"


def _to_post(post: dict[str, Any]) -> Optional[Post]:
    """Convert a Bluesky post view into a canonical Post."""
    uri = post.get("uri")
    if not uri:
        return None
    author = post.get("author") or {}
    record = post.get("record") or {}
    handle = author.get("handle")

    metadata: dict[str, Any] = {"uri": uri}
    if post.get("cid"):
        metadata["cid"] = post["cid"]
    if record.get("langs"):
        metadata["langs"] = record["langs"]
    if post.get("repostCount") is not None:
        metadata["repost_count"] = post["repostCount"]

    return Post(
        id=str(uri),
        source=SOURCE_NAME,
        text=record.get("text"),
        author=handle,
        score=post.get("likeCount"),
        comment_count=post.get("replyCount"),
        created_at=record.get("createdAt"),
        source_url=_post_url(str(uri), handle),
        metadata=metadata,
    )


def fetch_posts(config: BlueskyFetchConfig) -> list[Post]:
    """Fetch posts from Bluesky via search or an author feed."""
    if config.resource == "search":
        if not config.query:
            raise ValueError("bluesky resource 'search' requires a 'query'")
        endpoint = f"{XRPC_BASE}/app.bsky.feed.searchPosts"
        base_params: dict[str, Any] = {"q": config.query}
        items_key = "posts"
    else:  # author_feed
        if not config.actor:
            raise ValueError("bluesky resource 'author_feed' requires an 'actor'")
        endpoint = f"{XRPC_BASE}/app.bsky.feed.getAuthorFeed"
        base_params = {"actor": config.actor}
        items_key = "feed"

    client = get_default_client()
    posts: list[Post] = []
    cursor: Optional[str] = None

    while len(posts) < config.max_items:
        params = dict(base_params)
        params["limit"] = min(PAGE_SIZE, config.max_items - len(posts))
        if cursor:
            params["cursor"] = cursor

        resp = client.get(endpoint, params=params, timeout=DEFAULT_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()

        items = data.get(items_key, [])
        if not items:
            break

        for item in items:
            # getAuthorFeed wraps each post under a "post" key; searchPosts is flat.
            raw_post = item.get("post", item) if items_key == "feed" else item
            post = _to_post(raw_post)
            if post is None:
                continue
            if config.start_time is not None and config.end_time is not None:
                if post.created_at is None or not (config.start_time <= post.created_at <= config.end_time):
                    continue
            posts.append(post)

        next_cursor = data.get("cursor")
        # Stop on an absent or non-advancing cursor (guards against a spin if the
        # API echoes the same cursor while window-filtering drops every item).
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    return posts[: config.max_items]


@register_suggester("bluesky")
def suggest(
    *,
    query: Optional[str] = None,
    what: Optional[str] = None,
    limit: int = 25,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Discoverability for Bluesky (no auth, public AppView).

    ``what='actors'`` searches for accounts (handles) to use in an ``author_feed``;
    ``what='feeds'`` (default) lists popular custom feed generators.
    """
    client = get_default_client()
    if (what or "feeds") == "actors":
        if not query:
            raise ValueError("bluesky suggest with what='actors' requires a query")
        resp = client.get(
            f"{XRPC_BASE}/app.bsky.actor.searchActors",
            params={"q": query, "limit": min(100, limit)},
            timeout=DEFAULT_TIMEOUT_S,
        )
        resp.raise_for_status()
        return [
            {"handle": a.get("handle"), "displayName": a.get("displayName")}
            for a in resp.json().get("actors", [])
        ][:limit]

    params: dict[str, Any] = {"limit": min(100, limit)}
    if query:
        params["query"] = query
    resp = client.get(
        f"{XRPC_BASE}/app.bsky.unspecced.getPopularFeedGenerators",
        params=params,
        timeout=DEFAULT_TIMEOUT_S,
    )
    resp.raise_for_status()
    out: list[dict[str, Any]] = []
    for f in resp.json().get("feeds", []):
        out.append({
            "uri": f.get("uri"),
            "displayName": f.get("displayName"),
            "description": f.get("description"),
            "creator": (f.get("creator") or {}).get("handle"),
            "likeCount": f.get("likeCount"),
        })
    return out[:limit]


@register_fetcher("bluesky")
def fetch(config: FetcherConfig) -> FetcherResult:
    """Fetcher protocol implementation for Bluesky."""
    if not isinstance(config, BlueskyFetchConfig):
        raise ValueError(f"Invalid config type for bluesky fetcher: {type(config)}")
    try:
        return FetcherResult(posts=fetch_posts(config), errors=[])
    except Exception as e:
        return FetcherResult(posts=[], errors=[e])
