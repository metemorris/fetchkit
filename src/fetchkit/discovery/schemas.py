"""Pydantic models for RSS feed discovery.

Three models cover the pipeline:

- :class:`CatalogEntry` / :class:`Catalog` — the curated, shipped feed directory.
- :class:`FeedCandidate` — a feed found at runtime (autodiscovery or an external
  index), before ranking.
- :class:`FeedMatch` — a ranked result returned to the caller, carrying a
  relevance ``score`` and the ``source`` it came from. Its fields map directly
  onto an :class:`~fetchkit.schemas.fetcher.RSSFeedDescriptor`.

All field descriptions flow into ``fetchkit schema`` via Pydantic's
``model_json_schema()``, so an agent can learn the shape without out-of-band docs.
"""

from typing import Literal, Optional

from pydantic import Field

from fetchkit.schemas.base import FetchkitBaseModel

# Where a matched feed came from. Kept as a Literal so it appears as an enum in
# the emitted JSON Schema.
CandidateSource = Literal["catalog", "autodiscovery", "external"]


class CatalogEntry(FetchkitBaseModel):
    """One curated feed in the shipped discovery catalog."""

    id: str = Field(description="Stable slug, unique within the catalog (e.g. 'arxiv-cs-ai').")
    url: str = Field(description="The RSS/Atom feed URL (http(s) only).")
    name: str = Field(description="Human-readable feed title, e.g. 'arXiv cs.AI'.")
    description: str = Field(
        description="One to three sentences describing the feed. This is the primary "
        "text used for retrieval/ranking, so it should read like what the feed is about."
    )
    topics: list[str] = Field(
        default_factory=list,
        description="Normalized tags for the feed, e.g. ['ai', 'machine-learning', 'research'].",
    )
    category: str = Field(
        default="uncategorized",
        description="Coarse bucket, e.g. 'news', 'research', 'programming', 'finance'.",
    )
    language: str = Field(default="en", description="Primary language code, e.g. 'en'.")
    homepage: Optional[str] = Field(
        default=None, description="Homepage of the site the feed belongs to."
    )


class Catalog(FetchkitBaseModel):
    """The shipped catalog document: a version plus the list of feed entries."""

    catalog_version: int = Field(
        description="Monotonic version, bumped on any content change. Used to validate "
        "that a precomputed embedding artifact matches the catalog it was built from."
    )
    entries: list[CatalogEntry] = Field(description="The curated feed entries.")


class FeedCandidate(FetchkitBaseModel):
    """A feed discovered at runtime (autodiscovery or external index), pre-ranking."""

    url: str = Field(description="The RSS/Atom feed URL.")
    name: Optional[str] = Field(default=None, description="Feed title, if known.")
    description: Optional[str] = Field(
        default=None,
        description="Feed description. For autodiscovered feeds this is the feed's own "
        "subtitle/description, optionally followed by a few recent entry titles.",
    )
    topics: list[str] = Field(default_factory=list, description="Tags, if available.")
    category: Optional[str] = Field(default=None, description="Coarse bucket, if known.")
    language: Optional[str] = Field(default=None, description="Language code, if declared.")
    homepage: Optional[str] = Field(default=None, description="Site homepage, if known.")


class FeedMatch(FetchkitBaseModel):
    """A ranked discovery result. Its ``url``/``name`` drop into an RSS feed config."""

    url: str = Field(description="The RSS/Atom feed URL — use this in an rss fetcher's feeds.")
    name: Optional[str] = Field(default=None, description="Feed title.")
    description: Optional[str] = Field(default=None, description="What the feed is about.")
    topics: list[str] = Field(default_factory=list, description="Tags for the feed.")
    category: Optional[str] = Field(default=None, description="Coarse bucket.")
    language: Optional[str] = Field(default=None, description="Language code.")
    homepage: Optional[str] = Field(default=None, description="Site homepage.")
    source: CandidateSource = Field(
        description="Where this feed came from: 'catalog', 'autodiscovery', or 'external'."
    )
    score: float = Field(
        description="Relevance score for the query (higher is better). Comparable only "
        "within a single discover() call."
    )
