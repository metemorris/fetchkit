import pytest
from datetime import datetime
from pydantic import ValidationError
from fetchkit.schemas.fetcher import (
    HackerNewsFetchConfig,
    PostFetchConfig,
    CommentFetchConfig,
    RSSFeedDescriptor,
    RSSFetchConfig,
    SortOrder,
)


def test_hackernews_config_validation() -> None:
    config = HackerNewsFetchConfig()
    assert config.start_time is None
    assert config.end_time is None
    assert config.posts.max_items == 10
    assert config.comments.max_depth == 1

    with pytest.raises(ValidationError):
        PostFetchConfig(max_items=600)  # max is 500

    with pytest.raises(ValidationError):
        CommentFetchConfig(max_items=200)  # max is 100


def test_rss_config_validation() -> None:
    feed = RSSFeedDescriptor(url="https://example.com/rss", name="Test Feed")
    config = RSSFetchConfig(
        feeds=[feed],
        start_time=datetime.now(),
        end_time=datetime.now(),
    )
    assert len(config.feeds) == 1
    assert config.max_items_per_feed == 50
    assert config.max_total_items == 200
    assert config.include_content is True

    with pytest.raises(ValidationError):
        RSSFetchConfig(
            feeds=[feed],
            start_time=datetime.now(),
            end_time=datetime.now(),
            max_items_per_feed=600,  # max is 500
        )

    with pytest.raises(ValidationError):
        RSSFetchConfig(
            feeds=[feed],
            max_total_items=3000,  # max is 2000
        )


def test_sort_order_enum() -> None:
    assert SortOrder.ASC.value == "asc"
    assert SortOrder.DESC.value == "desc"
