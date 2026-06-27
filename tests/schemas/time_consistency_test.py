from datetime import datetime, timezone
from fetchkit.schemas.config import FetchKitConfig
from fetchkit.schemas.post import Post, Source


def test_config_time_consistency_naive() -> None:
    """Test that naive datetimes in config are converted to UTC."""
    config_dict = {
        "start_time": "2024-01-01T00:00:00",
        "end_time": "2024-01-01T23:59:59",
        "fetchers": [],
    }
    config = FetchKitConfig.model_validate(config_dict)

    assert config.start_time is not None
    assert config.start_time.tzinfo == timezone.utc
    assert config.end_time is not None
    assert config.end_time.tzinfo == timezone.utc
    assert config.start_time.hour == 0
    assert config.end_time.hour == 23


def test_config_time_consistency_aware() -> None:
    """Test that aware datetimes in config stay aware and are normalized to UTC."""
    config_dict = {
        "start_time": "2024-01-01T00:00:00+05:00",
        "end_time": "2024-01-01T23:59:59-05:00",
        "fetchers": [],
    }
    config = FetchKitConfig.model_validate(config_dict)

    assert config.start_time is not None
    assert config.start_time.tzinfo == timezone.utc
    # 00:00 +05:00 is 19:00 previous day UTC
    assert config.start_time.hour == 19
    assert config.start_time.day == 31

    assert config.end_time is not None
    assert config.end_time.tzinfo == timezone.utc
    # 23:59 -05:00 is 04:59 next day UTC
    assert config.end_time.hour == 4


def test_post_time_consistency() -> None:
    """Test that Post objects enforce UTC on created_at."""
    post = Post(
        id="test",
        source=Source.RSS,
        title="Test",
        created_at=datetime(2024, 1, 1, 12, 0, 0),  # naive
        source_url="http://example.com",
    )
    assert post.created_at is not None
    assert post.created_at.tzinfo == timezone.utc
