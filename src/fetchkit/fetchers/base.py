"""
Base protocol for data fetchers.
"""
from typing import Protocol, runtime_checkable
from dataclasses import dataclass, field
from fetchkit.schemas.post import Post
from fetchkit.schemas.fetcher import FetcherConfig


@dataclass
class FetcherResult:
    """Result from a fetch operation."""
    posts: list[Post] = field(default_factory=list)
    errors: list[Exception] = field(default_factory=list)


@runtime_checkable
class Fetcher(Protocol):
    """Protocol that all fetchers must implement."""

    def __call__(self, config: FetcherConfig) -> FetcherResult:
        """
        Execute the fetch operation.

        Args:
            config: The configuration for this specific fetcher instance.

        Returns:
            FetcherResult containing fetched posts and any errors.
        """
        ...
