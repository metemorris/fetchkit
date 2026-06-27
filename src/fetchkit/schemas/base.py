"""Shared Pydantic base model with strict fields and UTC datetime normalization."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator
from fetchkit.utils.time import ensure_utc


class FetchkitBaseModel(BaseModel):
    """Base model for all fetchkit schemas enforcing strict fields and UTC datetimes."""
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def ensure_datetimes_utc_before(cls, v: Any) -> Any:
        """Ensure all datetime fields are UTC-aware before parsing."""
        if isinstance(v, datetime):
            return ensure_utc(v)
        return v

    @field_validator("*", mode="after")
    @classmethod
    def ensure_datetimes_utc_after(cls, v: Any) -> Any:
        """Ensure all datetime fields are UTC-aware after parsing."""
        if isinstance(v, datetime):
            return ensure_utc(v)
        return v
