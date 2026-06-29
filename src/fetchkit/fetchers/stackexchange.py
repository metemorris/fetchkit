"""
Stack Exchange fetcher.

Fetches questions (and optionally their top answers) from the Stack Exchange
API (https://api.stackexchange.com), which works anonymously without auth or an
API key, subject to a 300 requests/day/IP quota. Questions become canonical
``Post`` objects; answers, when requested, are attached as ``Comment`` objects.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fetchkit.http import get_default_client
from fetchkit.schemas.post import Post, Comment, Source
from fetchkit.schemas.fetcher import (
    SortOrder,
    CommentFetchConfig,
    StackExchangeFetchConfig,
    FetcherConfig,
)
from fetchkit.fetchers.base import FetcherResult
from fetchkit.fetchers.registry import register_fetcher

logger = logging.getLogger(__name__)

API_BASE = "https://api.stackexchange.com/2.3"
SOURCE_NAME = Source.STACKEXCHANGE
DEFAULT_TIMEOUT_S = 15
PAGE_SIZE = 100  # API maximum

# Map the shared SortOrder onto Stack Exchange's `sort` parameter.
_SORT_MAP = {
    SortOrder.TOP: "votes",
    SortOrder.NEW: "creation",
    SortOrder.CONTROVERSIAL: "activity",
    SortOrder.ASC: "creation",
    SortOrder.DESC: "creation",
}


def _epoch_to_dt(value: Any) -> Optional[datetime]:
    """Convert a Stack Exchange unix-epoch timestamp into a UTC datetime."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return None


def _owner_name(item: dict[str, Any]) -> Optional[str]:
    """Extract the display name of an item's owner, if present."""
    owner = item.get("owner")
    if isinstance(owner, dict):
        return owner.get("display_name")
    return None


def _answer_to_comment(answer: dict[str, Any]) -> Comment:
    """Convert a Stack Exchange answer payload into a canonical Comment."""
    return Comment(
        id=str(answer.get("answer_id", "unknown")),
        author=_owner_name(answer),
        text=answer.get("body"),
        score=answer.get("score"),
        created_at=_epoch_to_dt(answer.get("creation_date")),
        story_id=str(answer["question_id"]) if answer.get("question_id") is not None else None,
    )


def _question_to_post(question: dict[str, Any]) -> Post:
    """Convert a Stack Exchange question payload into a canonical Post."""
    qid = str(question.get("question_id", ""))
    link = question.get("link") or f"https://stackoverflow.com/q/{qid}"
    metadata: dict[str, Any] = {
        "tags": question.get("tags") or [],
        "is_answered": question.get("is_answered"),
        "answer_count": question.get("answer_count"),
    }
    if question.get("accepted_answer_id") is not None:
        metadata["accepted_answer_id"] = question["accepted_answer_id"]
    return Post(
        id=qid,
        source=SOURCE_NAME,
        title=question.get("title"),
        text=question.get("body"),
        url=link,
        author=_owner_name(question),
        score=question.get("score"),
        comment_count=question.get("answer_count"),
        created_at=_epoch_to_dt(question.get("creation_date")),
        source_url=link,
        metadata=metadata,
    )


def _base_params(config: StackExchangeFetchConfig) -> dict[str, Any]:
    """Build the shared query parameters for a questions/search request."""
    params: dict[str, Any] = {
        "site": config.site,
        "order": "asc" if config.posts.order == SortOrder.ASC else "desc",
        "sort": _SORT_MAP.get(config.posts.order, "votes"),
        "filter": "withbody",  # include question body text
        "pagesize": PAGE_SIZE,
    }
    if config.tagged:
        params["tagged"] = ";".join(config.tagged)
    if config.start_time is not None:
        params["fromdate"] = int(config.start_time.timestamp())
    if config.end_time is not None:
        params["todate"] = int(config.end_time.timestamp())
    return params


def _fetch_answers(question_ids: list[str], config: CommentFetchConfig, site: str) -> dict[str, list[Comment]]:
    """Fetch top answers for the given question ids, grouped by question id."""
    if not question_ids:
        return {}
    client = get_default_client()
    ids = ";".join(question_ids)
    params = {
        "site": site,
        "order": "desc",
        "sort": "votes",
        "filter": "withbody",
        "pagesize": PAGE_SIZE,
    }
    resp = client.get(f"{API_BASE}/questions/{ids}/answers", params=params, timeout=DEFAULT_TIMEOUT_S)
    resp.raise_for_status()

    by_question: dict[str, list[Comment]] = {}
    for answer in resp.json().get("items", []):
        comment = _answer_to_comment(answer)
        qid = str(answer.get("question_id", ""))
        bucket = by_question.setdefault(qid, [])
        if len(bucket) < config.max_items:
            bucket.append(comment)
    return by_question


def fetch_posts(config: StackExchangeFetchConfig) -> list[Post]:
    """Fetch questions (and optionally answers) from Stack Exchange."""
    client = get_default_client()
    params = _base_params(config)
    endpoint = f"{API_BASE}/search/advanced" if config.query else f"{API_BASE}/questions"
    if config.query:
        params["q"] = config.query

    posts: list[Post] = []
    page = 1
    while len(posts) < config.posts.max_items:
        params["page"] = page
        resp = client.get(endpoint, params=params, timeout=DEFAULT_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break

        for item in items:
            post = _question_to_post(item)
            # Defensive client-side window filter (the API also filters by from/todate).
            if config.start_time is not None and config.end_time is not None:
                if post.created_at is None or not (config.start_time <= post.created_at <= config.end_time):
                    continue
            posts.append(post)

        if not data.get("has_more"):
            break
        page += 1

    posts = posts[: config.posts.max_items]

    if config.comments.fetch and posts:
        try:
            answers = _fetch_answers([p.id for p in posts], config.comments, config.site)
            for post in posts:
                post.comments = answers.get(post.id, [])
        except Exception as exc:
            logger.warning("Failed to fetch Stack Exchange answers: %s", exc)

    return posts


@register_fetcher("stackexchange")
def fetch(config: FetcherConfig) -> FetcherResult:
    """Fetcher protocol implementation for Stack Exchange."""
    if not isinstance(config, StackExchangeFetchConfig):
        raise ValueError(f"Invalid config type for stackexchange fetcher: {type(config)}")
    try:
        return FetcherResult(posts=fetch_posts(config), errors=[])
    except Exception as e:
        return FetcherResult(posts=[], errors=[e])
