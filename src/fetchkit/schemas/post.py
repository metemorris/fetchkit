"""
Post and Comment schemas.

Canonical data models for content fetched from sources.
These are the stable contracts that flow out of fetchkit.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import Field
from fetchkit.schemas.base import FetchkitBaseModel


class Source(str, Enum):
    """Builtin source identifiers.

    Advisory only: ``Post.source`` is a free ``str``, so fetchers may use any
    identifier. These constants name the sources fetchkit ships with.
    """
    HACKERNEWS = "hackernews"
    RSS = "rss"
    ARXIV = "arxiv"
    GITHUB = "github"
    LOBSTERS = "lobsters"


class Comment(FetchkitBaseModel):
    """A comment on a post."""
    id: str = Field(description="Unique comment ID")
    author: Optional[str] = Field(default=None, description="Comment author username")
    text: Optional[str] = Field(default=None, description="Comment text content")
    score: Optional[int] = Field(default=None, description="Comment score/points")
    created_at: Optional[datetime] = Field(default=None, description="When comment was posted")
    parent_id: Optional[str] = Field(default=None, description="Parent comment ID if nested")
    story_id: Optional[str] = Field(default=None, description="Parent story/post ID")
    replies: list["Comment"] = Field(default_factory=list, description="Direct replies to this comment")


class Post(FetchkitBaseModel):
    """Canonical post model for content from any source."""
    id: str = Field(description="Unique post ID")
    source: str = Field(description="Source identifier (e.g., 'hackernews', 'rss')")
    title: Optional[str] = Field(default=None, description="Post title")
    text: Optional[str] = Field(default=None, description="Post text/body content")
    url: Optional[str] = Field(default=None, description="Link URL if external")
    author: Optional[str] = Field(default=None, description="Post author username")
    score: Optional[int] = Field(
        default=None,
        description=(
            "Source-relative score/points (e.g. HN points, Lobsters score, GitHub "
            "stars; None for arXiv/RSS). NOT comparable across sources — compare "
            "only within the same 'source'."
        ),
    )
    comment_count: Optional[int] = Field(default=None, description="Number of comments")
    created_at: Optional[datetime] = Field(default=None, description="When post was created")
    source_url: str = Field(description="Direct link to post on source platform")
    comments: list[Comment] = Field(default_factory=list, description="Fetched comments")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Source-specific extra fields that don't map to a canonical column "
            "(e.g. arxiv categories/DOI, GitHub repo/language, tickers). Keeps the "
            "core model stable while letting fetchers carry domain detail."
        ),
    )
