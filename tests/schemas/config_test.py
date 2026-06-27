import pytest
from datetime import datetime
from pydantic import ValidationError
from fetchkit.schemas.config import FetchKitConfig
from fetchkit.schemas.fetcher import HackerNewsFetchConfig, RSSFetchConfig, RSSFeedDescriptor


def test_fetchkit_config() -> None:
    """Test top-level FetchKitConfig validation and behavior."""
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 2)

    config = FetchKitConfig(start_time=start, end_time=end)
    assert not config.has_enabled_fetchers

    config = FetchKitConfig(
        start_time=start,
        end_time=end,
        fetchers=[
            HackerNewsFetchConfig(),
            RSSFetchConfig(feeds=[RSSFeedDescriptor(url="http://x")]),
        ],
    )
    assert config.has_enabled_fetchers
    assert len(config.fetchers) == 2
    assert isinstance(config.fetchers[0], HackerNewsFetchConfig)
    assert isinstance(config.fetchers[1], RSSFetchConfig)


def test_fetchkit_config_invalid_time_window() -> None:
    with pytest.raises(ValidationError):
        FetchKitConfig(
            start_time=datetime(2026, 1, 2),
            end_time=datetime(2026, 1, 1),
        )


def test_fetchkit_config_rejects_unknown_fields() -> None:
    """processors/notifiers are not part of a fetchers-only config."""
    with pytest.raises(ValidationError):
        FetchKitConfig.model_validate({
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-02T00:00:00Z",
            "processors": [{"type": "filter.engagement", "name": "x", "min_score": 1}],
        })


def test_fetchkit_config_window_resolves_times() -> None:
    """A relative window resolves to concrete start/end times."""
    config = FetchKitConfig.model_validate({"window": "last 6 hours", "fetchers": []})
    assert config.start_time is not None
    assert config.end_time is not None
    delta = config.end_time - config.start_time
    assert abs(delta.total_seconds() - 6 * 3600) < 5


def test_fetchkit_config_defaults_to_last_day() -> None:
    """With no window and no explicit bounds, default to the last 24 hours."""
    config = FetchKitConfig.model_validate({"fetchers": []})
    assert config.start_time is not None
    assert config.end_time is not None
    delta = config.end_time - config.start_time
    assert abs(delta.total_seconds() - 24 * 3600) < 5


def test_fetchkit_config_window_and_times_mutually_exclusive() -> None:
    with pytest.raises(ValidationError, match="not both"):
        FetchKitConfig.model_validate({
            "window": "last 6 hours",
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-02T00:00:00Z",
            "fetchers": [],
        })


def test_fetchkit_config_requires_both_bounds() -> None:
    with pytest.raises(ValidationError, match="both start_time and end_time"):
        FetchKitConfig.model_validate({
            "start_time": "2026-01-01T00:00:00Z",
            "fetchers": [],
        })


def test_fetchkit_config_invalid_window() -> None:
    with pytest.raises(ValidationError):
        FetchKitConfig.model_validate({"window": "whenever", "fetchers": []})


def test_fetchkit_config_http_block_optional() -> None:
    config = FetchKitConfig.model_validate({
        "start_time": "2026-01-01T00:00:00Z",
        "end_time": "2026-01-02T00:00:00Z",
        "http": {"timeout": 15.0, "max_retries": 5, "rate_limit_per_host": 2.0},
    })
    assert config.http is not None
    assert config.http.timeout == 15.0
    assert config.http.max_retries == 5
    assert config.http.rate_limit_per_host == 2.0
