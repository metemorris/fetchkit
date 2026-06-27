"""
Registry for builtin data fetchers.

fetchkit ships a fixed set of builtin fetchers (hackernews, rss, arxiv, github,
lobsters). Each registers itself with ``@register_fetcher`` when its module is
imported (see ``fetchkit.fetchers.__init__``). New fetchers are added to the
library directly — there is no third-party plugin/entry-point discovery — so
every fetcher gets a typed config, validation, and tests. To add one, drop a
module in ``fetchkit/fetchers/`` and register it (see the README's "Adding a
fetcher" section).
"""
import logging
from typing import Callable, Any, TypeVar, cast

from fetchkit.fetchers.base import Fetcher

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Map of fetcher type string to handler function.
REGISTRY: dict[str, Fetcher] = {}


def register_fetcher(fetcher_type: str) -> Callable[[F], F]:
    """
    Decorator to register a fetcher handler function.

    Args:
        fetcher_type: The unique identifier for the fetcher type (e.g., "hackernews").
    """
    def decorator(func: F) -> F:
        """Register the decorated callable under the requested fetcher type key."""
        REGISTRY[fetcher_type] = cast(Fetcher, func)
        return func
    return decorator


def get_fetcher(fetcher_type: str) -> Fetcher:
    """
    Retrieve a fetcher handler by its type identifier.

    Raises:
        ValueError: If no builtin fetcher is registered for ``fetcher_type``.
    """
    if fetcher_type not in REGISTRY:
        known = ", ".join(sorted(REGISTRY)) or "(none)"
        raise ValueError(
            f"Unknown fetcher type: {fetcher_type}. Known types: {known}"
        )

    return REGISTRY[fetcher_type]
