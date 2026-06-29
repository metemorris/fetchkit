"""Query an external feed-search index for long-tail recall (opt-in).

The curated catalog covers the head and autodiscovery reaches sites the agent
already found; this tier reaches feeds neither knows about by querying a
third-party feed directory. It is **off by default** (``use_external=True`` /
``--external``) because it depends on a network service with its own rate limits
and terms of use.

v1 ships one provider — Feedly's public feed-search endpoint, which needs no API
key — behind a small :class:`ExternalSearchProvider` protocol so other providers
can be added without touching callers.
"""

import logging
from typing import Optional, Protocol, runtime_checkable

from fetchkit.discovery.schemas import FeedCandidate
from fetchkit.http import get_default_client
from fetchkit.http.client import HttpClient

logger = logging.getLogger(__name__)

_FEEDLY_SEARCH_URL = "https://cloud.feedly.com/v3/search/feeds"
DEFAULT_TIMEOUT_S = 10


@runtime_checkable
class ExternalSearchProvider(Protocol):
    """Searches a third-party index and returns feed candidates."""

    def search(self, query: str, *, limit: int) -> list[FeedCandidate]:
        """Return up to ``limit`` candidate feeds matching ``query``."""
        ...


class FeedlySearchProvider:
    """Provider backed by Feedly's public ``/v3/search/feeds`` endpoint (no auth)."""

    def __init__(self, client: Optional[HttpClient] = None) -> None:
        self._client = client

    def search(self, query: str, *, limit: int) -> list[FeedCandidate]:
        """Search Feedly and map results to :class:`FeedCandidate` objects."""
        client = self._client or get_default_client()
        response = client.get(
            _FEEDLY_SEARCH_URL,
            params={"query": query, "count": limit},
            timeout=DEFAULT_TIMEOUT_S,
        )
        response.raise_for_status()
        payload = response.json()
        candidates: list[FeedCandidate] = []
        for result in payload.get("results", []):
            url = _feed_url_from_result(result)
            if not url:
                continue
            candidates.append(
                FeedCandidate(
                    url=url,
                    name=result.get("title"),
                    description=result.get("description"),
                    topics=_topics(result.get("topics")),
                    language=result.get("language"),
                    homepage=result.get("website"),
                )
            )
        return candidates


def _topics(value: object) -> list[str]:
    """Normalize Feedly topics, which may be plain strings or ``{'label': ...}`` dicts."""
    if not isinstance(value, list):
        return []
    topics: list[str] = []
    for item in value:
        if isinstance(item, dict) and "label" in item:
            topics.append(str(item["label"]))
        elif isinstance(item, str):
            topics.append(item)
    return topics


def _feed_url_from_result(result: dict[str, object]) -> Optional[str]:
    """Extract the feed URL from a Feedly result (``feedId`` is ``feed/<url>``)."""
    feed_id = result.get("feedId")
    if isinstance(feed_id, str) and feed_id.startswith("feed/"):
        return feed_id[len("feed/") :]
    if isinstance(feed_id, str):
        return feed_id
    return None


def search_feeds_external(
    query: str,
    *,
    limit: int = 10,
    provider: Optional[ExternalSearchProvider] = None,
) -> list[FeedCandidate]:
    """Search an external feed index for ``query``.

    Args:
        query: Natural-language topic to search for.
        limit: Maximum number of candidates to request.
        provider: Override the search provider (defaults to Feedly).

    Returns:
        Candidate feeds from the external index (possibly empty).
    """
    provider = provider or FeedlySearchProvider()
    return provider.search(query, limit=limit)


__all__ = [
    "ExternalSearchProvider",
    "FeedlySearchProvider",
    "search_feeds_external",
]
