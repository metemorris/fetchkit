import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from requests import RequestException

from fetchkit.fetchers.rss import fetch_posts, fetch_posts_with_errors, RSSFetchResult
from fetchkit.fetchers.rss import fetch as fetch_via_protocol
from fetchkit.fetchers.base import FetcherResult
from fetchkit.schemas.fetcher import RSSFetchConfig, RSSFeedDescriptor
from fetchkit.schemas.fetcher import HackerNewsFetchConfig
from fetchkit.schemas.post import Post, Source

# Fixture paths
FIXTURE_DIR = Path(__file__).parent.parent / "testdata"
RSS_FIXTURE = FIXTURE_DIR / "sample_rss.xml"
ATOM_FIXTURE = FIXTURE_DIR / "sample_atom.xml"


def test_fetch_posts_local_file(tmp_path: Path) -> None:
    """Test fetching from local RSS and Atom fixtures."""
    assert RSS_FIXTURE.exists()
    assert ATOM_FIXTURE.exists()

    config = RSSFetchConfig(
        feeds=[
            RSSFeedDescriptor(url=str(RSS_FIXTURE.absolute())),
            RSSFeedDescriptor(url=str(ATOM_FIXTURE.absolute())),
        ],
        start_time=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 27, 0, 0, 0, tzinfo=timezone.utc),
        max_items_per_feed=10,
        max_total_items=20,
        allow_local_files=True,
    )

    posts = fetch_posts(config)

    # Expected:
    # RSS: Item 1, 2, 3 (Item 4 skipped because of missing date)
    # Atom: Atom Entry 1, Duplicate Item (Now included because of namespacing)
    # Total: 5 posts
    assert len(posts) == 5

    for post in posts:
        assert post.source == Source.RSS
        assert post.created_at is not None
        assert config.start_time is not None
        assert config.end_time is not None
        assert config.start_time <= post.created_at <= config.end_time

    ids = [post.id for post in posts]
    assert len(ids) == len(set(ids))
    assert any(id.endswith(":guid-1") for id in ids)
    assert any(id.endswith(":atom-id-1") for id in ids)

    # Verify ordering (created_at desc)
    for i in range(len(posts) - 1):
        pa = posts[i].created_at
        pb = posts[i + 1].created_at
        assert pa is not None
        assert pb is not None
        assert pa >= pb


def test_rss_time_window_filtering() -> None:
    """Test that items outside the time window are filtered out."""
    config = RSSFetchConfig(
        feeds=[RSSFeedDescriptor(url=str(RSS_FIXTURE.absolute()))],
        start_time=datetime(2026, 1, 26, 13, 30, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 26, 14, 30, 0, tzinfo=timezone.utc),
        allow_local_files=True,
    )

    posts = fetch_posts(config)

    # Should only include Item 3 (14:00)
    assert len(posts) == 1
    assert posts[0].title == "Item 3: Updated only"
    assert posts[0].url is not None
    assert posts[0].url.startswith("http")


def test_rss_limits() -> None:
    """Test max_items_per_feed and max_total_items."""
    config = RSSFetchConfig(
        feeds=[
            RSSFeedDescriptor(url=str(RSS_FIXTURE.absolute())),
            RSSFeedDescriptor(url=str(ATOM_FIXTURE.absolute())),
        ],
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        max_items_per_feed=2,
        max_total_items=3,
        allow_local_files=True,
    )

    posts = fetch_posts(config)

    # RSS has 3 valid items (1, 2, 3), but limited to 2
    # Atom has 1 new item (Entry 1) + 1 duplicate (guid-1)
    # Total should be capped at 3
    assert len(posts) == 3


def test_local_file_feed_rejected_by_default() -> None:
    """Local/file feeds are refused unless allow_local_files is set."""
    config = RSSFetchConfig(
        feeds=[
            RSSFeedDescriptor(url=str(RSS_FIXTURE.absolute())),
            RSSFeedDescriptor(url="file:///etc/passwd"),
        ],
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )

    result = fetch_posts_with_errors(config)

    # No posts read from local files; both local feeds are reported as errors.
    assert result.posts == []
    assert len(result.errors) == 2
    assert all("allow_local_files" in str(e) for e in result.errors)


def test_fetch_posts_with_errors_reports_per_feed_failures() -> None:
    config = RSSFetchConfig(
        feeds=[
            RSSFeedDescriptor(url=str(RSS_FIXTURE.absolute())),
            RSSFeedDescriptor(url="https://example.com/bad-feed.xml"),
        ],
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
        allow_local_files=True,
    )

    # The local fixture bypasses the HTTP client; only the bad URL hits it.
    mock_client = MagicMock()
    mock_client.get.side_effect = RequestException("boom for bad-feed")
    with patch("fetchkit.fetchers.rss.get_default_client", return_value=mock_client):
        result = fetch_posts_with_errors(config)

    assert len(result.posts) == 3
    assert len(result.errors) == 1
    assert result.errors[0].feed_url == "https://example.com/bad-feed.xml"
    assert "bad-feed.xml" in str(result.errors[0])


@pytest.mark.live
def test_rss_live_smoke() -> None:
    """Live smoke test to fetch from a real feed (BBC News)."""
    bbc_rss = "https://feeds.bbci.co.uk/news/rss.xml"
    config = RSSFetchConfig(
        feeds=[RSSFeedDescriptor(url=bbc_rss, name="BBC News")],
        start_time=datetime.now(timezone.utc) - timedelta(days=1),
        end_time=datetime.now(timezone.utc),
        max_items_per_feed=5,
    )

    result = fetch_posts_with_errors(config)
    if result.errors:
        pytest.skip(f"Live feed unavailable: {result.errors[0]}")
    posts = result.posts

    assert len(posts) > 0
    assert posts[0].title is not None
    url = posts[0].url
    assert url is not None
    assert url.startswith("http")


def test_fetch_protocol_rejects_wrong_config_type() -> None:
    with pytest.raises(ValueError):
        fetch_via_protocol(
            HackerNewsFetchConfig(
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            )
        )


def test_fetch_protocol_wraps_success() -> None:
    config = RSSFetchConfig(feeds=[RSSFeedDescriptor(url=str(RSS_FIXTURE.absolute()))])
    with patch("fetchkit.fetchers.rss.fetch_posts_with_errors") as mock_fetch:
        mock_fetch.return_value = RSSFetchResult(
            posts=[Post(id="1", source=Source.RSS, title="ok", source_url="https://example.com")],
            errors=[],
        )
        result = fetch_via_protocol(config)

    assert isinstance(result, FetcherResult)
    assert len(result.posts) == 1
    assert result.errors == []


def test_fetch_protocol_wraps_exception() -> None:
    config = RSSFetchConfig(feeds=[RSSFeedDescriptor(url=str(RSS_FIXTURE.absolute()))])
    with patch("fetchkit.fetchers.rss.fetch_posts_with_errors", side_effect=RuntimeError("boom")):
        result = fetch_via_protocol(config)

    assert result.posts == []
    assert len(result.errors) == 1
    assert "boom" in str(result.errors[0])
