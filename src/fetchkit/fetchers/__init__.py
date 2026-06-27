"""Fetcher package exports and builtin fetcher registration side effects."""

from .registry import get_fetcher, register_fetcher
# Import built-in fetchers to ensure they register themselves on import.
from . import hackernews
from . import rss
from . import arxiv
from . import github
from . import lobsters

__all__ = ["get_fetcher", "register_fetcher"]
