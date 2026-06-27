"""
arXiv fetcher.

Fetches papers from the arXiv export API (https://export.arxiv.org/api/query),
which returns Atom XML — parsed with feedparser, already a fetchkit dependency.
Multi-valued detail (all authors, categories, DOI, PDF link) is preserved in
``Post.metadata``.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import feedparser

from fetchkit.http import get_default_client
from fetchkit.schemas.post import Post, Source
from fetchkit.schemas.fetcher import ArxivFetchConfig, FetcherConfig
from fetchkit.fetchers.base import FetcherResult
from fetchkit.fetchers.registry import register_fetcher

logger = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
SOURCE_NAME = Source.ARXIV
DEFAULT_TIMEOUT_S = 30  # arXiv can be slow


def _build_search_query(config: ArxivFetchConfig) -> str:
    """Combine categories and free-text query into an arXiv ``search_query``."""
    clauses: list[str] = []
    if config.categories:
        cats = " OR ".join(f"cat:{c}" for c in config.categories)
        clauses.append(f"({cats})")
    if config.query:
        clauses.append(f"all:{config.query}")
    return " AND ".join(clauses) if clauses else "all:*"


def _parse_published(entry: Any) -> Optional[datetime]:
    """Extract the published date (UTC) from a feedparser entry."""
    for attr in ("published_parsed", "updated_parsed"):
        st = getattr(entry, attr, None)
        if st:
            return datetime(st[0], st[1], st[2], st[3], st[4], st[5], tzinfo=timezone.utc)
    return None


def _pdf_link(entry: Any) -> Optional[str]:
    """Return the PDF link for an entry, if present."""
    for link in getattr(entry, "links", []) or []:
        if getattr(link, "type", None) == "application/pdf" or getattr(link, "title", None) == "pdf":
            return str(getattr(link, "href", "")) or None
    return None


def _normalize_entry(entry: Any) -> Optional[Post]:
    """Convert a feedparser arXiv entry into a canonical Post."""
    created_at = _parse_published(entry)
    abs_url = str(getattr(entry, "id", "")) or None  # arXiv abs page
    if not abs_url:
        return None

    # arXiv id is the trailing path segment of the abs URL (e.g. 2401.12345v1).
    arxiv_id = abs_url.rstrip("/").rsplit("/", 1)[-1]

    authors = [str(a.get("name")) for a in getattr(entry, "authors", []) if a.get("name")]
    categories = [str(t.get("term")) for t in getattr(entry, "tags", []) if t.get("term")]

    metadata: dict[str, Any] = {}
    if authors:
        metadata["authors"] = authors
    if categories:
        metadata["categories"] = categories
    if getattr(entry, "arxiv_doi", None):
        metadata["doi"] = str(entry.arxiv_doi)
    pdf = _pdf_link(entry)
    if pdf:
        metadata["pdf_url"] = pdf
    if getattr(entry, "arxiv_primary_category", None):
        primary = entry.arxiv_primary_category.get("term") if isinstance(entry.arxiv_primary_category, dict) else None
        if primary:
            metadata["primary_category"] = str(primary)

    return Post(
        id=arxiv_id,
        source=SOURCE_NAME,
        title=getattr(entry, "title", None),
        text=getattr(entry, "summary", None),
        url=pdf or abs_url,
        author=", ".join(authors) if authors else None,
        created_at=created_at,
        source_url=abs_url,
        metadata=metadata,
    )


def fetch_posts(config: ArxivFetchConfig) -> list[Post]:
    """Fetch papers from arXiv matching the configured categories/query."""
    params = {
        "search_query": _build_search_query(config),
        "start": 0,
        "max_results": config.max_items,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    client = get_default_client()
    response = client.get(ARXIV_API_URL, params=params, timeout=DEFAULT_TIMEOUT_S)
    response.raise_for_status()

    feed = feedparser.parse(response.content)
    posts: list[Post] = []
    for entry in feed.entries:
        post = _normalize_entry(entry)
        if post is None:
            continue
        # Window filtering (datetimes are UTC-normalized by the schema).
        if config.start_time is not None and config.end_time is not None:
            if post.created_at is None or not (config.start_time <= post.created_at <= config.end_time):
                continue
        posts.append(post)
    return posts


@register_fetcher("arxiv")
def fetch(config: FetcherConfig) -> FetcherResult:
    """Fetcher protocol implementation for arXiv."""
    if not isinstance(config, ArxivFetchConfig):
        raise ValueError(f"Invalid config type for arxiv fetcher: {type(config)}")
    try:
        return FetcherResult(posts=fetch_posts(config), errors=[])
    except Exception as e:
        return FetcherResult(posts=[], errors=[e])
