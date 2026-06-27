"""
Hacker News fetcher.

Fetches posts and comments from Hacker News using the Algolia API.
Returns canonical Post and Comment models.
"""

import logging
from typing import Callable, Union, Any

from fetchkit.http import get_default_client
from fetchkit.schemas.post import Post, Comment, Source
from fetchkit.schemas.fetcher import (
    SortOrder,
    CommentFetchConfig,
    HackerNewsFetchConfig,
    FetcherConfig,
)
from fetchkit.fetchers.base import FetcherResult
from fetchkit.fetchers.registry import register_fetcher
from fetchkit.utils.time import UTC_MIN


# =============================================================================
# Constants
# =============================================================================

ALGOLIA_API_BASE = "https://hn.algolia.com/api/v1"
HACKERNEWS_ITEM_URL = "https://news.ycombinator.com/item?id={item_id}"
SOURCE_NAME = Source.HACKERNEWS
DEFAULT_TIMEOUT_S = 10
logger = logging.getLogger(__name__)


# =============================================================================
# Sorting Utilities
# =============================================================================

def get_sort_key(order: SortOrder, item_type: str = "post") -> Callable:
    """
    Get the appropriate sort key function based on order type.

    Args:
        order: The SortOrder enum value
        item_type: Either "post" or "comment" for type-specific sorting

    Returns:
        A callable that extracts the sort key from an item
    """
    if order == SortOrder.TOP:
        return lambda item: item.score or 0
    elif order == SortOrder.NEW:
        return lambda item: item.created_at or UTC_MIN
    elif order == SortOrder.CONTROVERSIAL:
        if item_type == "comment":
            return lambda item: len(item.text or "")
        else:
            return lambda item: item.comment_count or 0

    elif order == SortOrder.ASC or order == SortOrder.DESC:
        # For general ASC/DESC, sort by creation time
        return lambda item: item.created_at or UTC_MIN

    return lambda item: item.score or 0  # type: ignore[unreachable]


def sort_items(items: list, order: SortOrder, item_type: str = "post") -> list:
    """
    Sort a list of items based on the specified order.

    Args:
        items: List of Post or Comment objects
        order: SortOrder enum value
        item_type: Either "post" or "comment"

    Returns:
        Sorted list of items
    """
    sort_key = get_sort_key(order, item_type)
    # ASC sorts low-to-high, all others sort high-to-low
    reverse = order != SortOrder.ASC
    return sorted(items, key=sort_key, reverse=reverse)


# =============================================================================
# Comment Fetching
# =============================================================================

def _build_comment_tree(comments: list[Comment], max_depth: int) -> list[Comment]:
    """
    Reconstruct a threaded comment tree from a flat list of comments,
    limited by max_depth.
    """
    # First pass: map all comments by ID
    lookup = {comment.id: comment for comment in comments}
    root_comments = []

    # Second pass: establish parent-child relationships
    for comment in comments:
        # If the parent is in our list, it might be a child
        parent = lookup.get(comment.parent_id) if comment.parent_id else None

        if not parent:
            # If no parent in this set, this is a "root" for this view
            root_comments.append(comment)
        else:
            # Only append to parent if it's within the requested depth
            parent.replies.append(comment)

    # Third pass: Prune the tree to max_depth
    def prune(comment: Comment, current_depth: int) -> None:
        """Recursively cap nested replies at the configured maximum depth."""
        if current_depth >= max_depth:
            comment.replies = []
        else:
            for reply in comment.replies:
                prune(reply, current_depth + 1)

    for rc in root_comments:
        prune(rc, 0)

    return root_comments


def fetch_comments(post_id: str, config: CommentFetchConfig) -> list[Comment]:
    """
    Fetch comments for a specific Hacker News post and reconstruct the thread tree.

    Args:
        post_id: The HN post ID to fetch comments for
        config: CommentFetchConfig specifying max_items, order, and max_depth

    Returns:
        List of Comment objects (root comments with nested replies)
    """
    api_url = f"{ALGOLIA_API_BASE}/search"

    # We fetch enough comments to build a meaningful tree
    fetch_limit = max(config.max_items * 5, 200)
    all_comments: list[Comment] = []
    page = 0
    client = get_default_client()

    while len(all_comments) < fetch_limit:
        params: dict[str, Any] = {
            "query": "",
            "tags": f"comment,story_{post_id}",
            "hitsPerPage": min(100, fetch_limit - len(all_comments)),
            "page": page,
        }

        response = client.get(api_url, params=params, timeout=DEFAULT_TIMEOUT_S)
        response.raise_for_status()

        data = response.json()
        hits = data.get("hits", [])
        if not hits:
            break

        all_comments.extend([Comment.from_api(hit) for hit in hits])

        page += 1
        if page >= data.get("nbPages", 0):
            break

    # 1. Build and prune the tree
    root_comments = _build_comment_tree(all_comments, config.max_depth)

    # 2. Sort and limit the roots
    sorted_roots = sort_items(root_comments, config.order, item_type="comment")
    return sorted_roots[:config.max_items]


# =============================================================================
# Post Fetching
# =============================================================================

def _fetch_raw_posts(
    start_ts: int,
    end_ts: int,
    fetch_limit: int,
    order: SortOrder,
) -> list[Post]:
    """
    Fetch raw post objects from Algolia API with pagination.
    Uses the appropriate endpoint based on the desired sort order.
    """

    # /search sorts by points/relevance, /search_by_date sorts by date
    # Optimization: Use /search_by_date for ALL time-filtered queries as it's more reliable
    # for strict window consistency, or strictly when SortOrder.NEW is requested.
    if order == SortOrder.NEW:
        api_url = f"{ALGOLIA_API_BASE}/search_by_date"
    else:
        # Algolia Search API performs better for relevance (TOP)
        api_url = f"{ALGOLIA_API_BASE}/search"

    raw_posts: list[Post] = []
    page = 0
    client = get_default_client()

    while len(raw_posts) < fetch_limit:
        params: dict[str, Union[str, int]] = {
            "query": "",
            "tags": "story",
            "numericFilters": f"created_at_i>={start_ts},created_at_i<={end_ts}",
            "hitsPerPage": min(100, fetch_limit - len(raw_posts)),
            "page": page,
        }

        response = client.get(api_url, params=params, timeout=DEFAULT_TIMEOUT_S)
        response.raise_for_status()

        data = response.json()
        hits = data.get("hits", [])
        if not hits:
            break

        for hit in hits:
            raw_posts.append(Post.from_api(hit, SOURCE_NAME, HACKERNEWS_ITEM_URL))
            if len(raw_posts) >= fetch_limit:
                break

        page += 1
        if page >= data.get("nbPages", 0):
            break

    return raw_posts


def _attach_comments_to_posts_inplace(posts: list[Post], config: CommentFetchConfig) -> None:
    """Fetch and attach comments to each post in-place."""
    for post in posts:
        try:
            post.comments = fetch_comments(post.id, config)
        except Exception as exc:
            logger.warning(
                "Failed to fetch comments for HN post %s: %s",
                post.id,
                exc,
            )
            post.comments = []


def fetch_posts(config: HackerNewsFetchConfig) -> list[Post]:
    """
    Fetch posts from Hacker News between start_time and end_time.

    Args:
        config: HackerNewsFetchConfig with time range and fetch options

    Returns:
        List of Post objects with optional comments attached
    """
    if config.start_time is None or config.end_time is None:
        raise ValueError("start_time and end_time must be set for HackerNews fetch")
    start_ts = int(config.start_time.timestamp())
    end_ts = int(config.end_time.timestamp())

    # For NEW/TOP orders, we fetch exactly what's needed.
    # For CONTROVERSIAL, we fetch a larger sample to sort by comments locally.
    max_items = config.posts.max_items
    if config.posts.order == SortOrder.CONTROVERSIAL:
        fetch_limit = max(max_items * 5, 200)
    else:
        fetch_limit = max_items

    # 1. Fetch raw posts from API
    raw_posts = _fetch_raw_posts(start_ts, end_ts, fetch_limit, config.posts.order)

    # 2. Sort and apply final limit
    sorted_posts = sort_items(raw_posts, config.posts.order, item_type="post")
    final_posts = sorted_posts[:max_items]

    # 3. Optionally attach comments (in-place)
    if config.comments.fetch:
        _attach_comments_to_posts_inplace(final_posts, config.comments)

    return final_posts


@register_fetcher("hackernews")
def fetch(config: FetcherConfig) -> FetcherResult:
    """
    Fetcher protocol implementation for Hacker News.
    """
    if not isinstance(config, HackerNewsFetchConfig):
        # Should be guaranteed by the registry dispatch, but good for safety
        raise ValueError(f"Invalid config type for hackernews fetcher: {type(config)}")

    try:
        posts = fetch_posts(config)
        return FetcherResult(posts=posts, errors=[])
    except Exception as e:
        return FetcherResult(posts=[], errors=[e])
