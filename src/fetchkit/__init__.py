"""
fetchkit — a YAML-configured data fetching library for agentic applications.

Fetch posts and comments from sources (Hacker News, RSS/Atom, arXiv, GitHub,
Lobsters) into a single canonical ``Post`` model, with deduplication, sorting,
and a typed config. Designed as a data-collection layer for agentic / LLM
applications.

Quick start::

    from fetchkit import load_config, collect_all

    config = load_config("config.yaml")
    result = collect_all(config)
    for post in result.posts:
        print(post.title, post.url)

See the README for the full configuration reference and the guide to adding
fetchers.
"""

__version__ = "0.1.1"

from fetchkit.collector import collect_all
from fetchkit.config_loader import load_config, ConfigError
from fetchkit.fetchers.base import Fetcher, FetcherResult
from fetchkit.fetchers.registry import register_fetcher, get_fetcher
from fetchkit.http import (
    HttpClient,
    RateLimiter,
    get_default_client,
    set_default_client,
    use_client,
)
from fetchkit.schemas.post import Post, Comment, Source
from fetchkit.schemas.fetcher import (
    SortOrder,
    PostFetchConfig,
    CommentFetchConfig,
    FetcherBase,
    HackerNewsFetchConfig,
    RSSFeedDescriptor,
    RSSFetchConfig,
    ArxivFetchConfig,
    GitHubFetchConfig,
    LobstersFetchConfig,
    FetcherConfig,
)
from fetchkit.schemas.collector import CollectorResult
from fetchkit.schemas.config import FetchKitConfig, HttpConfig
from fetchkit.utils.time import resolve_window, parse_duration

__all__ = [
    "__version__",
    # Orchestration
    "collect_all",
    "load_config",
    "ConfigError",
    # Fetcher protocol & registry
    "Fetcher",
    "FetcherResult",
    "register_fetcher",
    "get_fetcher",
    # HTTP
    "HttpClient",
    "RateLimiter",
    "get_default_client",
    "set_default_client",
    "use_client",
    # Schemas
    "Post",
    "Comment",
    "Source",
    "SortOrder",
    "PostFetchConfig",
    "CommentFetchConfig",
    "FetcherBase",
    "HackerNewsFetchConfig",
    "RSSFeedDescriptor",
    "RSSFetchConfig",
    "ArxivFetchConfig",
    "GitHubFetchConfig",
    "LobstersFetchConfig",
    "FetcherConfig",
    "CollectorResult",
    "FetchKitConfig",
    "HttpConfig",
    # Time helpers
    "resolve_window",
    "parse_duration",
]
