"""Top-level discovery orchestration: query -> ranked feeds -> RSS config.

:func:`discover` is the agent-facing surface. It assembles feed candidates from up
to three sources — the curated catalog (always), autodiscovery over caller-supplied
sites, and an optional external index — deduplicates them by URL, ranks them
against the query, and returns the best :class:`FeedMatch` objects.
:func:`to_rss_config` turns those matches into a ready-to-run
:class:`~fetchkit.schemas.fetcher.RSSFetchConfig`, completing the
discover -> config -> run pipeline.

The genuinely open-ended "topic -> candidate sites" step is intentionally left to
the caller (an agent already has web search): pass the sites it found via
``from_urls`` and fetchkit extracts, validates, and ranks their feeds.
"""

import logging
from typing import Any, Optional

from fetchkit.discovery.autodiscover import find_feeds
from fetchkit.discovery.catalog import load_catalog
from fetchkit.discovery.external import search_feeds_external
from fetchkit.discovery.ranking import get_ranker
from fetchkit.discovery.schemas import CandidateSource, CatalogEntry, FeedCandidate, FeedMatch
from fetchkit.schemas.fetcher import RSSFeedDescriptor, RSSFetchConfig

logger = logging.getLogger(__name__)


def _match_from_entry(entry: CatalogEntry) -> FeedMatch:
    """Build an unscored match from a curated catalog entry."""
    return FeedMatch(
        url=entry.url,
        name=entry.name,
        description=entry.description,
        topics=entry.topics,
        category=entry.category,
        language=entry.language,
        homepage=entry.homepage,
        source="catalog",
        score=0.0,
    )


def _match_from_candidate(candidate: FeedCandidate, source: CandidateSource) -> FeedMatch:
    """Build an unscored match from a runtime-discovered candidate."""
    return FeedMatch(
        url=candidate.url,
        name=candidate.name,
        description=candidate.description,
        topics=candidate.topics,
        category=candidate.category,
        language=candidate.language,
        homepage=candidate.homepage,
        source=source,
        score=0.0,
    )


def discover(
    query: str,
    *,
    top_k: int = 5,
    backend: str = "auto",
    from_urls: Optional[list[str]] = None,
    use_external: bool = False,
    min_score: Optional[float] = None,
    catalog_path: Optional[str] = None,
) -> list[FeedMatch]:
    """Find RSS feeds relevant to a natural-language ``query``.

    Args:
        query: The use case, e.g. "news and topics regarding AI safety".
        top_k: Maximum number of matches to return.
        backend: Ranker backend — ``"auto"`` (default), ``"lexical"``, or
            ``"embedding"`` (needs the ``discovery-embeddings`` extra).
        from_urls: Sites (e.g. from the agent's own web search) to autodiscover
            feeds from and include as candidates.
        use_external: Also query the external feed index (network; opt-in).
        min_score: Drop matches scoring below this threshold.
        catalog_path: Override the catalog file (mainly for tests).

    Returns:
        Up to ``top_k`` ranked :class:`FeedMatch` objects, best first.
    """
    candidates: list[FeedMatch] = []
    seen_urls: set[str] = set()

    def add(match: FeedMatch) -> None:
        if match.url in seen_urls:
            return
        seen_urls.add(match.url)
        candidates.append(match)

    # (1) Curated catalog — always available, offline, deterministic.
    for entry in load_catalog(catalog_path).entries:
        add(_match_from_entry(entry))

    # (2) Autodiscovery over caller-supplied sites — the open-web tail.
    for site in from_urls or []:
        try:
            for candidate in find_feeds(site):
                add(_match_from_candidate(candidate, "autodiscovery"))
        except Exception as exc:  # best-effort: one bad site shouldn't fail discovery
            logger.warning("Autodiscovery failed for %s: %s", site, exc)

    # (3) External index — opt-in long-tail recall.
    if use_external:
        try:
            for candidate in search_feeds_external(query):
                add(_match_from_candidate(candidate, "external"))
        except Exception as exc:  # best-effort: external outage shouldn't fail discovery
            logger.warning("External feed search failed: %s", exc)

    ranked = get_ranker(backend).rank(query, candidates)
    if min_score is not None:
        ranked = [m for m in ranked if m.score >= min_score]
    return ranked[:top_k]


def to_rss_config(matches: list[FeedMatch], **rss_kwargs: Any) -> RSSFetchConfig:
    """Build an :class:`RSSFetchConfig` whose feeds are the matched feeds.

    The result drops straight into ``fetchkit run`` (or ``collect_all``). Extra
    keyword arguments (e.g. ``max_items_per_feed``) are passed through to the config.
    """
    feeds = [RSSFeedDescriptor(url=m.url, name=m.name) for m in matches]
    return RSSFetchConfig(feeds=feeds, **rss_kwargs)


__all__ = ["discover", "to_rss_config"]
