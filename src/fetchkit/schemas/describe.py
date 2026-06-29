"""Self-description: emit JSON Schema for every fetchkit config and output model.

fetchkit is meant to be a deterministic CLI primitive an agent shells out to. For
that to work the agent has to know *what* it can fetch and *how* to spell a config
without being told out of band. This module builds a single JSON document
describing the canonical output model (:class:`Post`), the top-level config, the
shared HTTP settings, and every builtin fetcher's typed config.

It leans entirely on Pydantic v2's ``model_json_schema()``, so the
``Field(description=...)`` text already attached to every model flows through
automatically — there is nothing to keep in sync by hand. New fetchers are picked
up for free because we iterate the same ``_BUILTIN_TYPES`` registry the validator
uses.
"""

from typing import Any

from fetchkit import __version__
from fetchkit.schemas.config import FetchKitConfig, HttpConfig
from fetchkit.schemas.fetcher import _BUILTIN_TYPES
from fetchkit.schemas.post import Post


def build_schema_document() -> dict[str, Any]:
    """Return a JSON-serializable description of every fetchkit schema.

    The document has the shape::

        {
          "version": "0.1.1",
          "config":  {<FetchKitConfig JSON Schema>},
          "http":    {<HttpConfig JSON Schema>},
          "fetchers": {"hackernews": {...}, "rss": {...}, ...},
          "post":    {<Post JSON Schema>},
          "discovery": {<RSS feed discovery capability>}
        }
    """
    return {
        "version": __version__,
        "config": FetchKitConfig.model_json_schema(),
        "http": HttpConfig.model_json_schema(),
        "fetchers": {
            fetcher_type: config_cls.model_json_schema()
            for fetcher_type, config_cls in _BUILTIN_TYPES.items()
        },
        "post": Post.model_json_schema(),
        "discovery": _discovery_section(),
    }


def _discovery_section() -> dict[str, Any]:
    """Describe the RSS feed discovery capability so agents know it exists.

    Discovery lives in an optional subpackage, so this is best-effort: if it can't
    be imported, a stub explains how to enable it rather than failing ``schema``.
    """
    try:
        from fetchkit.discovery.catalog import load_catalog
        from fetchkit.discovery.schemas import FeedMatch

        return {
            "summary": (
                "Find RSS feeds for a natural-language use case. Feeds are matched, "
                "not searched: candidates come from a curated catalog, from "
                "autodiscovery over sites you supply, and (opt-in) an external index, "
                "then are ranked against the query."
            ),
            "feed_match": FeedMatch.model_json_schema(),
            "candidate_sources": {
                "catalog": "Curated feed directory shipped with fetchkit; offline, always available.",
                "autodiscovery": (
                    "Extract feeds from caller-supplied site URLs (--from-urls / find_feeds). "
                    "Reaches the open web — you supply the sites from your own web search."
                ),
                "external": "Optional third-party feed-index search (--external; needs network).",
            },
            "ranker_backends": {
                "auto": "Embedding ranker if the discovery-embeddings extra is installed, else lexical.",
                "lexical": "Pure-Python BM25 over feed metadata; deterministic, no extra deps.",
                "embedding": "Local sentence-transformers model; needs the discovery-embeddings extra.",
            },
            "catalog_version": load_catalog().catalog_version,
            "maps_to_fetcher": "rss",
            "commands": {
                "discover": (
                    'fetchkit discover "<query>" [--top-k N] '
                    "[--backend auto|lexical|embedding] [--from-urls url1,url2] "
                    "[--external] [--min-score F] [--as-config]"
                ),
                "find_feeds": "fetchkit find-feeds <url> [<url> ...] [--max-feeds N]",
            },
            "library": {
                "discover": (
                    "fetchkit.discovery.discover(query, *, top_k=5, backend='auto', "
                    "from_urls=None, use_external=False, min_score=None) -> list[FeedMatch]"
                ),
                "find_feeds": (
                    "fetchkit.discovery.find_feeds(url, *, max_feeds=10) -> list[FeedCandidate]"
                ),
                "to_rss_config": (
                    "fetchkit.discovery.to_rss_config(matches, **rss_kwargs) -> RSSFetchConfig"
                ),
            },
            "note": (
                "Each match's 'url'/'name' drops into the rss fetcher's 'feeds'. Use "
                "`discover ... --as-config` (or to_rss_config) to get a runnable config, "
                "then `fetchkit run`."
            ),
        }
    except Exception as exc:  # pragma: no cover - defensive stub
        return {"available": False, "error": str(exc)}
