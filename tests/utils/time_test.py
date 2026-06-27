from datetime import datetime, timedelta, timezone

import pytest

from fetchkit.utils.time import parse_duration, resolve_window


def test_parse_duration_short_and_long_forms() -> None:
    assert parse_duration("6h") == timedelta(hours=6)
    assert parse_duration("30 minutes") == timedelta(minutes=30)
    assert parse_duration("2d") == timedelta(days=2)
    assert parse_duration("1 week") == timedelta(weeks=1)
    assert parse_duration("90s") == timedelta(seconds=90)


def test_parse_duration_invalid() -> None:
    with pytest.raises(ValueError):
        parse_duration("soon")
    with pytest.raises(ValueError):
        parse_duration("5 fortnights")


def test_resolve_window_last_n() -> None:
    now = datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)
    start, end = resolve_window("last 6 hours", now=now)
    assert end == now
    assert start == now - timedelta(hours=6)


def test_resolve_window_bare_duration() -> None:
    now = datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc)
    start, end = resolve_window("7d", now=now)
    assert start == now - timedelta(days=7)
    assert end == now


def test_resolve_window_today() -> None:
    now = datetime(2026, 6, 27, 12, 30, tzinfo=timezone.utc)
    start, end = resolve_window("today", now=now)
    assert start == datetime(2026, 6, 27, 0, 0, tzinfo=timezone.utc)
    assert end == now


def test_resolve_window_yesterday() -> None:
    now = datetime(2026, 6, 27, 12, 30, tzinfo=timezone.utc)
    start, end = resolve_window("yesterday", now=now)
    assert start == datetime(2026, 6, 26, 0, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 6, 27, 0, 0, tzinfo=timezone.utc)


def test_resolve_window_naive_now_is_utc_normalized() -> None:
    start, end = resolve_window("1h", now=datetime(2026, 6, 27, 12, 0))
    assert end.tzinfo == timezone.utc
    assert start.tzinfo == timezone.utc


def test_resolve_window_invalid_raises() -> None:
    with pytest.raises(ValueError):
        resolve_window("whenever")
