"""Schema subpackage: Pydantic models for fetchkit."""

from fetchkit.schemas.base import FetchkitBaseModel
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

__all__ = [
    "FetchkitBaseModel",
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
]
