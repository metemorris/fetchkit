import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from typing import List, Any

from fetchkit.schemas.config import FetchKitConfig
from fetchkit.schemas.fetcher import HackerNewsFetchConfig, RSSFetchConfig, RSSFeedDescriptor
from fetchkit.schemas.post import Post, Source
from fetchkit.collector import collect_all
from fetchkit.schemas.collector import CollectorResult
from fetchkit.fetchers.base import FetcherResult


@pytest.fixture
def mock_posts() -> List[Post]:
    return [
        Post(
            id="1", source=Source.HACKERNEWS, title="HN 1",
            created_at=datetime(2026, 1, 26, 12, 0, tzinfo=timezone.utc),
            source_url="http://hn/1",
        ),
        Post(
            id="2", source=Source.RSS, title="RSS 1",
            created_at=datetime(2026, 1, 26, 13, 0, tzinfo=timezone.utc),
            source_url="http://rss/1",
        ),
    ]


def test_fetch_all_orchestration(mock_posts: List[Post]) -> None:
    """Test that collect_all delegates and merges correctly."""
    config = FetchKitConfig(
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        fetchers=[
            HackerNewsFetchConfig(),
            RSSFetchConfig(feeds=[RSSFeedDescriptor(url="http://test")]),
        ],
    )

    with patch("fetchkit.collector.get_fetcher") as mock_get_fetcher:
        mock_hn = MagicMock(return_value=FetcherResult(posts=[mock_posts[0]], errors=[]))
        mock_rss = MagicMock(return_value=FetcherResult(posts=[mock_posts[1]], errors=[]))

        def get_fetcher_side_effect(type_name: str) -> Any:
            if type_name == "hackernews":
                return mock_hn
            if type_name == "rss":
                return mock_rss
            raise ValueError(f"Unknown: {type_name}")

        mock_get_fetcher.side_effect = get_fetcher_side_effect

        result = collect_all(config)

        assert isinstance(result, CollectorResult)
        assert not result.has_errors
        assert len(result.posts) == 2
        assert result.posts[0].source == Source.RSS  # newer first
        assert result.posts[1].source == Source.HACKERNEWS

        mock_get_fetcher.assert_any_call("hackernews")
        mock_get_fetcher.assert_any_call("rss")

        mock_hn.assert_called_once()
        call_config = mock_hn.call_args[0][0]
        assert call_config.start_time == config.start_time

        mock_rss.assert_called_once()


def test_fetch_all_partial_failure(mock_posts: List[Post]) -> None:
    """One failing source doesn't prevent others; errors are tracked."""
    config = FetchKitConfig(
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        fetchers=[
            HackerNewsFetchConfig(),
            RSSFetchConfig(feeds=[RSSFeedDescriptor(url="http://test")]),
        ],
    )

    with patch("fetchkit.collector.get_fetcher") as mock_get_fetcher:
        mock_hn = MagicMock(side_effect=Exception("HN Failed"))
        mock_rss = MagicMock(return_value=FetcherResult(posts=[mock_posts[1]], errors=[]))

        def get_fetcher_side_effect(type_name: str) -> Any:
            if type_name == "hackernews":
                return mock_hn
            if type_name == "rss":
                return mock_rss
            return MagicMock()

        mock_get_fetcher.side_effect = get_fetcher_side_effect

        result = collect_all(config)

        assert len(result.posts) == 1
        assert result.posts[0].source == Source.RSS

        assert result.has_errors
        assert len(result.errors) == 1
        source, error = result.errors[0]
        assert isinstance(source, str)
        assert source == Source.HACKERNEWS.value
        assert "HN Failed" in str(error)


def test_collect_all_tracks_rss_per_feed_errors(mock_posts: List[Post]) -> None:
    config = FetchKitConfig(
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        fetchers=[
            RSSFetchConfig(
                feeds=[
                    RSSFeedDescriptor(url="http://good"),
                    RSSFeedDescriptor(url="http://bad-1"),
                    RSSFeedDescriptor(url="http://bad-2"),
                ]
            )
        ],
    )

    with patch("fetchkit.collector.get_fetcher") as mock_get_fetcher:
        mock_rss = MagicMock(return_value=FetcherResult(
            posts=[mock_posts[1]],
            errors=[
                Exception("timeout http://bad-1"),
                Exception("dns http://bad-2"),
            ],
        ))
        mock_get_fetcher.return_value = mock_rss

        result = collect_all(config)

    assert len(result.posts) == 1
    assert result.posts[0].source == Source.RSS
    assert result.has_errors
    assert len(result.errors) == 2
    assert all(isinstance(source, str) for source, _ in result.errors)
    assert all(source == Source.RSS.value for source, _ in result.errors)
    assert "http://bad-1" in str(result.errors[0][1])
    assert "http://bad-2" in str(result.errors[1][1])


def test_collect_all_dedup() -> None:
    """Items are deduped by (source, id)."""
    post1 = Post(id="1", source=Source.HACKERNEWS, title="T1", created_at=datetime.now(timezone.utc), source_url="u1")
    post2 = Post(id="1", source=Source.HACKERNEWS, title="T1 duplicate", created_at=datetime.now(timezone.utc), source_url="u1")

    config = FetchKitConfig(
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        fetchers=[HackerNewsFetchConfig()],
    )

    with patch("fetchkit.collector.get_fetcher") as mock_get_fetcher:
        mock_hn = MagicMock(return_value=FetcherResult(posts=[post1, post2], errors=[]))
        mock_get_fetcher.return_value = mock_hn

        result = collect_all(config)
        assert len(result.posts) == 1


def test_collect_all_restores_preinstalled_http_client() -> None:
    """A run that installs a client from config.http must restore the caller's
    previously-installed default client, not clear it to None."""
    from fetchkit.http import HttpClient, get_default_client, set_default_client
    from fetchkit.schemas.config import HttpConfig

    caller_client = HttpClient()
    set_default_client(caller_client)
    try:
        config = FetchKitConfig(
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
            fetchers=[HackerNewsFetchConfig()],
            http=HttpConfig(timeout=5.0),
        )
        with patch("fetchkit.collector.get_fetcher") as mock_get_fetcher:
            mock_get_fetcher.return_value = MagicMock(
                return_value=FetcherResult(posts=[], errors=[])
            )
            collect_all(config)

        assert get_default_client() is caller_client
    finally:
        set_default_client(None)


def test_collect_all_concurrent_runs_are_isolated() -> None:
    """Two collect_all runs on different threads each see their own HTTP client,
    even while both are mid-flight (no global clobbering)."""
    import threading
    from fetchkit.http import get_default_client
    from fetchkit.schemas.config import HttpConfig

    seen: dict[str, float] = {}
    barrier = threading.Barrier(2)

    def fake_fetcher(cfg: Any) -> FetcherResult:
        barrier.wait()  # ensure both runs are inside a fetcher simultaneously
        seen[cfg.name] = get_default_client().config.timeout
        barrier.wait()
        return FetcherResult(posts=[], errors=[])

    def run(name: str, timeout: float) -> None:
        config = FetchKitConfig(
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
            fetchers=[HackerNewsFetchConfig(name=name)],
            http=HttpConfig(timeout=timeout),
        )
        collect_all(config)

    with patch("fetchkit.collector.get_fetcher", return_value=fake_fetcher):
        t1 = threading.Thread(target=run, args=("a", 5.0))
        t2 = threading.Thread(target=run, args=("b", 9.0))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    assert seen == {"a": 5.0, "b": 9.0}


def test_collect_all_empty_config() -> None:
    """Collector behavior when no fetchers are enabled."""
    config = FetchKitConfig(
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        fetchers=[],
    )
    result = collect_all(config)
    assert len(result.posts) == 0
    assert not result.has_errors


def test_collect_all_verbose_prints_progress(mock_posts: List[Post], capsys: pytest.CaptureFixture[str]) -> None:
    config = FetchKitConfig(
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        fetchers=[HackerNewsFetchConfig()],
    )
    with patch("fetchkit.collector.get_fetcher") as mock_get_fetcher:
        mock_get_fetcher.return_value = MagicMock(
            return_value=FetcherResult(posts=[mock_posts[0]], errors=[])
        )
        collect_all(config, verbose=True)
    out = capsys.readouterr().out
    assert "Fetched 1 posts" in out


def test_collect_all_quiet_by_default(mock_posts: List[Post], capsys: pytest.CaptureFixture[str]) -> None:
    config = FetchKitConfig(
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        fetchers=[HackerNewsFetchConfig()],
    )
    with patch("fetchkit.collector.get_fetcher") as mock_get_fetcher:
        mock_get_fetcher.return_value = MagicMock(
            return_value=FetcherResult(posts=[mock_posts[0]], errors=[])
        )
        collect_all(config)
    out = capsys.readouterr().out
    assert out == ""
