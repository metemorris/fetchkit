"""RSS feed discovery for fetchkit.

The RSS fetcher needs a feed URL the agent must already know; this subpackage
closes that gap. Given a natural-language use case, :func:`discover` returns
ranked feeds the agent can drop straight into an RSS config.

Feeds are matched, not searched: candidates are gathered from a curated catalog,
from autodiscovery over caller-supplied sites (:func:`find_feeds`), and from an
optional external index, then ranked. The default ranker is pure-Python and needs
no extra dependencies; a local-embedding ranker is available behind the
``discovery-embeddings`` extra.

    from fetchkit.discovery import discover, to_rss_config

    matches = discover("news and topics regarding AI safety", top_k=5)
    config = to_rss_config(matches)   # ready for fetchkit run / collect_all
"""

from fetchkit.discovery.autodiscover import find_feeds
from fetchkit.discovery.catalog import load_catalog
from fetchkit.discovery.core import discover, to_rss_config
from fetchkit.discovery.errors import DiscoveryBackendUnavailable, DiscoveryError
from fetchkit.discovery.external import search_feeds_external
from fetchkit.discovery.schemas import (
    Catalog,
    CatalogEntry,
    FeedCandidate,
    FeedMatch,
)

__all__ = [
    "discover",
    "to_rss_config",
    "find_feeds",
    "search_feeds_external",
    "load_catalog",
    "Catalog",
    "CatalogEntry",
    "FeedCandidate",
    "FeedMatch",
    "DiscoveryError",
    "DiscoveryBackendUnavailable",
]
