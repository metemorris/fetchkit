"""
Configuration schemas for fetchers.
"""

from enum import Enum
from datetime import datetime
from typing import Optional, Union, Literal, Annotated, Any
from pydantic import Field, BeforeValidator

from fetchkit.schemas.base import FetchkitBaseModel


class SortOrder(Enum):
    """Ordering options for posts and comments."""
    TOP = "top"                       # Highest score first
    NEW = "new"                       # Most recent first
    CONTROVERSIAL = "controversial"   # Most engagement first
    ASC = "asc"                       # Ascending order
    DESC = "desc"                     # Descending order


class PostFetchConfig(FetchkitBaseModel):
    """Configuration for fetching posts."""
    max_items: int = Field(default=10, ge=1, le=500, description="Maximum posts to fetch")
    order: SortOrder = Field(default=SortOrder.TOP, description="Sort order for posts")


class CommentFetchConfig(FetchkitBaseModel):
    """Configuration for fetching comments with posts."""
    fetch: bool = Field(default=False, description="Whether to fetch comments")
    max_items: int = Field(default=10, ge=1, le=100, description="Max comments per post")
    max_depth: int = Field(default=1, ge=0, description="Max thread depth (0 = roots only, 1 = roots + children)")
    order: SortOrder = Field(default=SortOrder.TOP, description="Sort order for comments")


class FetcherBase(FetchkitBaseModel):
    """Base configuration for all fetchers."""
    type: str = Field(description="Type identifier for the fetcher (e.g. 'hackernews', 'rss')")
    name: Optional[str] = Field(default=None, description="Unique name for this fetcher instance")
    enabled: bool = Field(default=True, description="Whether this fetcher is enabled")
    start_time: Optional[datetime] = Field(default=None, description="Start of time range (inclusive), inherits from global if None")
    end_time: Optional[datetime] = Field(default=None, description="End of time range (inclusive), inherits from global if None")


class HackerNewsFetchConfig(FetcherBase):
    """Configuration for a Hacker News fetcher."""
    type: Literal["hackernews"] = Field(default="hackernews", description="Built-in fetcher type identifier.")
    posts: PostFetchConfig = Field(default_factory=PostFetchConfig, description="Post retrieval settings for this Hacker News fetcher.")
    comments: CommentFetchConfig = Field(default_factory=CommentFetchConfig, description="Comment retrieval settings for fetched posts.")


class RSSFeedDescriptor(FetchkitBaseModel):
    """Descriptor for an RSS/Atom feed."""
    url: str = Field(description="URL of the RSS/Atom feed")
    name: Optional[str] = Field(default=None, description="Optional friendly name for the feed")


class RSSFetchConfig(FetcherBase):
    """Configuration for an RSS fetcher."""
    type: Literal["rss"] = Field(default="rss", description="Built-in fetcher type identifier.")
    feeds: list[RSSFeedDescriptor] = Field(description="List of feeds to fetch from")
    max_items_per_feed: int = Field(default=50, ge=1, le=500, description="Max items per individual feed")
    max_total_items: int = Field(default=200, ge=1, le=2000, description="Max total items across all feeds")
    include_content: bool = Field(default=True, description="Whether to include full content if available")
    allow_local_files: bool = Field(
        default=False,
        description=(
            "Allow reading feeds from local file paths and file:// URLs. Disabled "
            "by default for safety: when fetchkit runs untrusted configs (e.g. ones "
            "produced by an agent), a local path could exfiltrate arbitrary files. "
            "Enable only for trusted configs/fixtures."
        ),
    )


class ArxivFetchConfig(FetcherBase):
    """Configuration for an arXiv fetcher (export.arxiv.org Atom API)."""
    type: Literal["arxiv"] = Field(default="arxiv", description="Built-in fetcher type identifier.")
    categories: list[str] = Field(
        default_factory=list,
        description="arXiv categories to include (e.g. ['cs.AI', 'cs.LG']). Empty = all.",
    )
    query: Optional[str] = Field(
        default=None,
        description="Free-text search query (search_query=all:...). Combined with categories.",
    )
    max_items: int = Field(default=50, ge=1, le=500, description="Max results to fetch")


class GitHubFetchConfig(FetcherBase):
    """Configuration for a GitHub fetcher (public REST API, no auth)."""
    type: Literal["github"] = Field(default="github", description="Built-in fetcher type identifier.")
    repos: list[str] = Field(
        default_factory=list,
        description="Repositories as 'owner/name' to fetch releases from.",
    )
    resource: Literal["releases", "search_repos"] = Field(
        default="releases",
        description="What to fetch: per-repo 'releases', or repository 'search_repos'.",
    )
    query: Optional[str] = Field(
        default=None,
        description="Search query when resource='search_repos' (e.g. 'language:python stars:>1000').",
    )
    max_items: int = Field(default=50, ge=1, le=300, description="Max items to fetch")


class LobstersFetchConfig(FetcherBase):
    """Configuration for a Lobsters fetcher (lobste.rs JSON, no auth)."""
    type: Literal["lobsters"] = Field(default="lobsters", description="Built-in fetcher type identifier.")
    listing: Literal["hottest", "newest"] = Field(
        default="hottest", description="Which Lobsters listing to fetch."
    )
    tag: Optional[str] = Field(
        default=None, description="Restrict to a single tag (e.g. 'rust', 'ai')."
    )
    max_items: int = Field(default=50, ge=1, le=200, description="Max stories to fetch")


# Known builtin fetcher types, keyed by their `type` discriminator.
_BUILTIN_TYPES: dict[str, type[FetcherBase]] = {
    "hackernews": HackerNewsFetchConfig,
    "rss": RSSFetchConfig,
    "arxiv": ArxivFetchConfig,
    "github": GitHubFetchConfig,
    "lobsters": LobstersFetchConfig,
}


def _parse_fetcher_config(value: Any) -> Any:
    """Polymorphic discriminator: build the typed config for a fetcher ``type``."""
    if isinstance(value, FetcherBase):
        return value

    if isinstance(value, dict):
        fetcher_type = value.get("type")
        config_cls = _BUILTIN_TYPES.get(fetcher_type) if fetcher_type is not None else None
        if config_cls is None:
            known = ", ".join(sorted(_BUILTIN_TYPES))
            raise ValueError(
                f"Unknown fetcher type: {fetcher_type!r}. Known types: {known}"
            )
        return config_cls(**value)

    return value


FetcherConfig = Annotated[
    Union[
        HackerNewsFetchConfig,
        RSSFetchConfig,
        ArxivFetchConfig,
        GitHubFetchConfig,
        LobstersFetchConfig,
    ],
    BeforeValidator(_parse_fetcher_config),
]
