"""Fetcher package exports and builtin fetcher registration side effects."""

from .registry import get_fetcher, register_fetcher
from .suggest_registry import (
    get_suggester,
    list_suggesters,
    register_suggester,
    run_suggester,
)
# Import built-in fetchers to ensure they register themselves (fetchers and
# suggesters) on import.
from . import hackernews
from . import rss
from . import arxiv
from . import github
from . import lobsters
from . import stackexchange
from . import bluesky
from . import mastodon

__all__ = [
    "get_fetcher",
    "register_fetcher",
    "get_suggester",
    "list_suggesters",
    "register_suggester",
    "run_suggester",
]
