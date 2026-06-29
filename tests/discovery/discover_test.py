"""Tests for the discover() orchestration and to_rss_config()."""

from pathlib import Path
from unittest.mock import patch

from fetchkit.discovery import discover, to_rss_config
from fetchkit.discovery.schemas import FeedCandidate
from fetchkit.schemas.fetcher import RSSFetchConfig

FIXTURE = str(Path(__file__).parent.parent / "testdata" / "discovery" / "catalog_fixture.json")


def test_discover_ranks_catalog_for_query() -> None:
    matches = discover("rust programming", backend="lexical", catalog_path=FIXTURE)
    assert matches[0].url == "https://blog.rust-lang.org/feed.xml"
    assert matches[0].source == "catalog"


def test_discover_respects_top_k() -> None:
    matches = discover("programming", backend="lexical", top_k=2, catalog_path=FIXTURE)
    assert len(matches) == 2


def test_discover_min_score_filters() -> None:
    # A wildly off-topic query should score everything ~0 and be filtered out.
    matches = discover(
        "zzzqqq nonsense", backend="lexical", min_score=0.01, catalog_path=FIXTURE
    )
    assert matches == []


def test_discover_includes_autodiscovered_feeds() -> None:
    candidate = FeedCandidate(
        url="https://newlab.example/feed.xml",
        name="New AI Lab",
        description="Cutting-edge artificial intelligence and machine learning research.",
    )
    with patch("fetchkit.discovery.core.find_feeds", return_value=[candidate]):
        matches = discover(
            "artificial intelligence research",
            backend="lexical",
            from_urls=["https://newlab.example"],
            catalog_path=FIXTURE,
        )

    by_url = {m.url: m for m in matches}
    assert "https://newlab.example/feed.xml" in by_url
    assert by_url["https://newlab.example/feed.xml"].source == "autodiscovery"


def test_discover_dedups_catalog_over_autodiscovery() -> None:
    # Autodiscovery returns a feed already in the catalog: catalog wins (added first).
    dup = FeedCandidate(url="https://blog.rust-lang.org/feed.xml", name="dup")
    with patch("fetchkit.discovery.core.find_feeds", return_value=[dup]):
        matches = discover(
            "rust",
            backend="lexical",
            from_urls=["https://blog.rust-lang.org"],
            top_k=10,
            catalog_path=FIXTURE,
        )
    rust = [m for m in matches if m.url == "https://blog.rust-lang.org/feed.xml"]
    assert len(rust) == 1
    assert rust[0].source == "catalog"


def test_discover_includes_external_when_enabled() -> None:
    candidate = FeedCandidate(
        url="https://external.example/feed",
        name="External Hit",
        description="finance and markets news",
    )
    with patch(
        "fetchkit.discovery.core.search_feeds_external", return_value=[candidate]
    ):
        matches = discover(
            "finance markets",
            backend="lexical",
            use_external=True,
            top_k=10,
            catalog_path=FIXTURE,
        )
    sources = {m.url: m.source for m in matches}
    assert sources.get("https://external.example/feed") == "external"


def test_to_rss_config_round_trips() -> None:
    matches = discover("programming", backend="lexical", top_k=3, catalog_path=FIXTURE)
    config = to_rss_config(matches, max_items_per_feed=10)
    assert isinstance(config, RSSFetchConfig)
    assert config.type == "rss"
    assert len(config.feeds) == 3
    assert config.max_items_per_feed == 10
    # URLs and names carry over.
    assert config.feeds[0].url == matches[0].url
    assert config.feeds[0].name == matches[0].name
