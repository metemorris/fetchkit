"""
Configuration schemas for fetching data.

Defines the fetchers-only top-level configuration model controlling how posts
and comments are fetched from sources like Hacker News and RSS.
"""

from datetime import datetime
from typing import ClassVar, Optional
from pydantic import Field, model_validator

from fetchkit.schemas.base import FetchkitBaseModel
from fetchkit.schemas.fetcher import FetcherConfig
from fetchkit.utils.time import resolve_window


class HttpConfig(FetchkitBaseModel):
    """Optional shared HTTP client settings applied to all fetchers.

    All fields have sensible defaults; omit the ``http`` block entirely to use
    defaults. Fetchers that read local files (e.g. ``file://`` RSS fixtures) are
    unaffected by these settings.
    """
    timeout: float = Field(default=10.0, ge=0.1, description="Per-request timeout in seconds")
    max_retries: int = Field(default=3, ge=0, le=10, description="Max retry attempts on transient failures")
    backoff_factor: float = Field(
        default=0.5, ge=0.0,
        description="Exponential backoff base; wait = backoff_factor * (2 ** attempt) seconds",
    )
    rate_limit_per_host: Optional[float] = Field(
        default=None, gt=0.0,
        description="Max requests per second per host (None disables rate limiting)",
    )
    retry_statuses: set[int] = Field(
        default={429, 500, 502, 503, 504},
        description="HTTP status codes that trigger a retry (in addition to connection errors)",
    )


class FetchKitConfig(FetchkitBaseModel):
    """Root configuration for a single fetch run.

    Supplies the global time window (via ``window`` or ``start_time``/``end_time``)
    and the list of fetchers to run. Unknown top-level keys are rejected via
    ``extra="forbid"``.
    """
    start_time: Optional[datetime] = Field(
        default=None, description="Global start of time range (inclusive)"
    )
    end_time: Optional[datetime] = Field(
        default=None, description="Global end of time range (inclusive)"
    )
    window: Optional[str] = Field(
        default=None,
        description=(
            "Relative time window (e.g. 'last 6 hours', 'yesterday', '7d'). Mutually "
            "exclusive with start_time/end_time. If none of the three is set, the "
            "window defaults to the last 24 hours."
        ),
    )
    fetchers: list[FetcherConfig] = Field(default_factory=list, description="List of configured data fetchers")
    http: Optional[HttpConfig] = Field(default=None, description="Shared HTTP client settings")

    # Window used when a config supplies no time bounds at all.
    DEFAULT_WINDOW: ClassVar[str] = "last 24 hours"

    @property
    def has_enabled_fetchers(self) -> bool:
        """Check if any fetchers are enabled."""
        return any(f.enabled for f in self.fetchers)

    @model_validator(mode="after")
    def validate_time_window(self) -> "FetchKitConfig":
        """Resolve and validate the run window.

        Rules:
        - ``window`` is mutually exclusive with ``start_time``/``end_time``.
        - A ``window`` resolves to a concrete ``start_time``/``end_time`` pair.
        - Explicit bounds must be supplied together.
        - If nothing is supplied, default to the last 24 hours.
        - ``start_time <= end_time`` is enforced.
        """
        has_explicit = self.start_time is not None or self.end_time is not None

        if self.window is not None:
            if has_explicit:
                raise ValueError(
                    "Specify either 'window' or start_time/end_time, not both."
                )
            self.start_time, self.end_time = resolve_window(self.window)
        elif not has_explicit:
            # No time bounds given at all: default to the last day.
            self.start_time, self.end_time = resolve_window(self.DEFAULT_WINDOW)
        elif self.start_time is None or self.end_time is None:
            raise ValueError(
                "Provide both start_time and end_time, or a relative 'window' "
                "(e.g. 'last 6 hours')."
            )

        assert self.start_time is not None and self.end_time is not None
        if self.start_time > self.end_time:
            raise ValueError("start_time must be less than or equal to end_time")
        return self
