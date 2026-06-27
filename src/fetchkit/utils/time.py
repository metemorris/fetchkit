"""Time utility functions for consistent timezone handling.

Also provides human/agent-friendly relative window parsing so callers can say
"last 6 hours", "yesterday", or "7d" instead of computing absolute timestamps.
Windows resolve to a concrete ``(start, end)`` UTC pair *once*, so downstream
collection stays deterministic for that resolved pair.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure a datetime object is UTC-aware.
    If it's naive, assigns UTC timezone.
    If it's already aware, returns as is (but converts to UTC if it was another timezone).
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


# Shared constants for fallback
UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)


# Unit aliases -> seconds. Months/years are approximate (30/365 days).
_UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "wk": 604800, "wks": 604800, "week": 604800, "weeks": 604800,
    "mo": 2592000, "mon": 2592000, "month": 2592000, "months": 2592000,
    "y": 31536000, "yr": 31536000, "yrs": 31536000, "year": 31536000, "years": 31536000,
}

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]+)\s*$", re.IGNORECASE)


def parse_duration(text: str) -> timedelta:
    """Parse a duration like ``"6h"``, ``"30 minutes"``, ``"2d"`` into a timedelta.

    Accepts a number followed by a unit (s/m/h/d/w/mo/y and common spellings).
    Raises ``ValueError`` on anything it can't parse.
    """
    match = _DURATION_RE.match(text)
    if not match:
        raise ValueError(f"Cannot parse duration: {text!r} (try e.g. '6h', '2 days')")
    amount = float(match.group(1))
    unit = match.group(2).lower()
    if unit not in _UNIT_SECONDS:
        raise ValueError(f"Unknown time unit {unit!r} in duration {text!r}")
    return timedelta(seconds=amount * _UNIT_SECONDS[unit])


def resolve_window(spec: str, now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Resolve a relative time spec into a concrete ``(start, end)`` UTC pair.

    Supported forms (case-insensitive)::

        "last 6 hours" / "past 30 minutes" / "last 7 days" / "last month"
        "today"            # midnight UTC today .. now
        "yesterday"        # midnight..midnight of the previous UTC day
        "6h" / "2d" / "90m"  # bare duration == "last <duration>"

    ``now`` defaults to the current UTC time and is used as the window end (except
    for "yesterday"). Raises ``ValueError`` if the spec can't be understood.
    """
    end = ensure_utc(now) if now is not None else datetime.now(timezone.utc)
    assert end is not None  # ensure_utc only returns None for None input
    normalized = spec.strip().lower()

    if normalized == "today":
        start = end.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, end

    if normalized == "yesterday":
        midnight_today = end.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight_today - timedelta(days=1), midnight_today

    # Strip a leading relative qualifier, then treat the rest as a duration.
    for prefix in ("last ", "past ", "previous ", "in the last ", "in the past "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    duration = parse_duration(normalized)
    return end - duration, end
