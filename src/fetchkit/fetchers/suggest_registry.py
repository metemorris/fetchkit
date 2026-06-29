"""Registry for per-source discoverability helpers ("suggesters").

A *suggester* answers the question "what can I query for this source?" — the
selectable knobs an agent needs to fill a fetcher config: Lobsters/Stack Exchange
tags, arXiv categories, Stack Exchange sites, Mastodon trending hashtags, Bluesky
feeds/actors, RSS feeds (via the discovery subpackage). It is the cross-source
analog of the RSS-only ``discover()`` pipeline.

Each fetcher module registers one suggester with :func:`register_suggester`;
importing :mod:`fetchkit.fetchers` triggers registration as a side effect, exactly
like the fetcher registry. Suggesters share a uniform keyword signature so a single
dispatcher (and one CLI command) can drive them:

    suggest(*, query=None, site=None, instance=None, what=None, limit=20) -> list[dict]

Every suggester accepts ``**kwargs`` and simply ignores the parameters it does not
use. Results are plain JSON-ready dicts so they flow straight to the CLI / an agent.
"""

from typing import Any, Callable

# A suggester takes the shared keyword params and returns JSON-ready rows.
Suggester = Callable[..., list[dict[str, Any]]]

REGISTRY: dict[str, Suggester] = {}


def register_suggester(source: str) -> Callable[[Suggester], Suggester]:
    """Decorator registering ``func`` as the suggester for ``source``."""

    def decorator(func: Suggester) -> Suggester:
        REGISTRY[source] = func
        return func

    return decorator


def get_suggester(source: str) -> Suggester:
    """Return the suggester registered for ``source`` (or raise ValueError)."""
    if source not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise ValueError(f"No discovery helper for source: {source!r}. Known: {known}")
    return REGISTRY[source]


def list_suggesters() -> list[str]:
    """Return the sorted names of all registered suggesters."""
    return sorted(REGISTRY)


def run_suggester(source: str, **params: Any) -> list[dict[str, Any]]:
    """Dispatch to the suggester for ``source`` with the shared keyword params."""
    return get_suggester(source)(**params)
