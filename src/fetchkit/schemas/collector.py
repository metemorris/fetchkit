"""Collector result data structure for aggregated posts and per-source failures."""

from dataclasses import dataclass, field
from fetchkit.schemas.post import Post


@dataclass
class CollectorResult:
    """Result of a collect_all operation with error tracking."""
    posts: list[Post]
    errors: list[tuple[str, Exception]] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Returns True if any source failed during collection."""
        return len(self.errors) > 0

    @property
    def failed_sources(self) -> list[str]:
        """Returns list of sources that failed."""
        return [source for source, _ in self.errors]
