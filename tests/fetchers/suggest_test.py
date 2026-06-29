import pytest
import responses

from fetchkit.fetchers import get_suggester, list_suggesters, run_suggester
from fetchkit.fetchers.stackexchange import API_BASE as SE_API
from fetchkit.fetchers.bluesky import XRPC_BASE
from fetchkit.fetchers.lobsters import BASE_URL as LOBSTERS_URL
from fetchkit.fetchers.github import API_BASE as GH_API


def test_all_sources_have_a_suggester() -> None:
    assert set(list_suggesters()) == {
        "hackernews", "rss", "arxiv", "github",
        "lobsters", "stackexchange", "bluesky", "mastodon",
    }


def test_unknown_source_raises() -> None:
    with pytest.raises(ValueError):
        get_suggester("nope")


# --- static / offline suggesters -------------------------------------------

def test_hackernews_suggest_lists_orders() -> None:
    rows = run_suggester("hackernews")
    assert {r["order"] for r in rows} == {"top", "new", "controversial"}


def test_arxiv_suggest_lists_and_filters_categories() -> None:
    all_rows = run_suggester("arxiv")
    assert any(r["category"] == "cs.AI" for r in all_rows)
    filtered = run_suggester("arxiv", query="vision")
    assert filtered and all("vision" in (r["name"] + r["category"]).lower() for r in filtered)


def test_rss_suggest_uses_catalog() -> None:
    # discover() runs fully offline against the shipped catalog.
    rows = run_suggester("rss", query="artificial intelligence research", limit=3)
    assert len(rows) <= 3
    assert all("url" in r for r in rows)


def test_rss_suggest_requires_query() -> None:
    with pytest.raises(ValueError):
        run_suggester("rss")


# --- network suggesters (mocked) -------------------------------------------

@responses.activate
def test_lobsters_suggest_lists_tags() -> None:
    responses.add(
        responses.GET, f"{LOBSTERS_URL}/tags.json",
        json=[
            {"tag": "ai", "description": "Artificial intelligence", "category": "tech"},
            {"tag": "rust", "description": "Rust language", "category": "programming"},
        ],
        status=200,
    )
    rows = run_suggester("lobsters")
    assert {r["tag"] for r in rows} == {"ai", "rust"}
    assert rows[0]["description"] == "Artificial intelligence"


@responses.activate
def test_lobsters_suggest_filters_by_query() -> None:
    responses.add(
        responses.GET, f"{LOBSTERS_URL}/tags.json",
        json=[{"tag": "ai", "description": "x"}, {"tag": "rust", "description": "y"}],
        status=200,
    )
    rows = run_suggester("lobsters", query="rus")
    assert [r["tag"] for r in rows] == ["rust"]


@responses.activate
def test_github_suggest_popular_repos() -> None:
    responses.add(
        responses.GET, f"{GH_API}/search/repositories",
        json={"items": [
            {"full_name": "torvalds/linux", "stargazers_count": 170000, "language": "C", "description": "kernel"},
        ]},
        status=200,
    )
    rows = run_suggester("github", query="kernel", limit=5)
    assert rows[0]["repo"] == "torvalds/linux"
    assert rows[0]["stars"] == 170000


@responses.activate
def test_stackexchange_suggest_tags() -> None:
    responses.add(
        responses.GET, f"{SE_API}/tags",
        json={"items": [{"name": "python", "count": 99}, {"name": "asyncio", "count": 5}]},
        status=200,
    )
    rows = run_suggester("stackexchange", site="stackoverflow")
    assert rows[0] == {"tag": "python", "count": 99}


@responses.activate
def test_stackexchange_suggest_sites() -> None:
    responses.add(
        responses.GET, f"{SE_API}/sites",
        json={"items": [{"api_site_parameter": "serverfault", "name": "Server Fault", "audience": "sysadmins"}]},
        status=200,
    )
    rows = run_suggester("stackexchange", what="sites")
    assert rows[0]["site"] == "serverfault"


@responses.activate
def test_bluesky_suggest_feeds() -> None:
    responses.add(
        responses.GET, f"{XRPC_BASE}/app.bsky.unspecced.getPopularFeedGenerators",
        json={"feeds": [
            {"uri": "at://x/app.bsky.feed.generator/whats-hot", "displayName": "What's Hot",
             "description": "trending", "creator": {"handle": "bsky.app"}, "likeCount": 1000},
        ]},
        status=200,
    )
    rows = run_suggester("bluesky")
    assert rows[0]["displayName"] == "What's Hot"
    assert rows[0]["creator"] == "bsky.app"


@responses.activate
def test_bluesky_suggest_actors() -> None:
    responses.add(
        responses.GET, f"{XRPC_BASE}/app.bsky.actor.searchActors",
        json={"actors": [{"handle": "alice.bsky.social", "displayName": "Alice"}]},
        status=200,
    )
    rows = run_suggester("bluesky", what="actors", query="alice")
    assert rows[0]["handle"] == "alice.bsky.social"


def test_bluesky_suggest_actors_requires_query() -> None:
    with pytest.raises(ValueError):
        run_suggester("bluesky", what="actors")


@responses.activate
def test_mastodon_suggest_trending_tags() -> None:
    responses.add(
        responses.GET, "https://mastodon.social/api/v1/trends/tags",
        json=[
            {"name": "ai", "url": "https://mastodon.social/tags/ai",
             "history": [{"uses": "10"}, {"uses": "5"}]},
        ],
        status=200,
    )
    rows = run_suggester("mastodon")
    assert rows[0]["tag"] == "ai"
    assert rows[0]["uses"] == 15


# --- live smoke (deselect with -m "not live") ------------------------------

@pytest.mark.live
@pytest.mark.parametrize(
    "source,params",
    [
        ("lobsters", {}),
        ("stackexchange", {"site": "stackoverflow"}),
        ("mastodon", {"instance": "mastodon.social"}),
        ("bluesky", {}),
        ("github", {"query": "language:python stars:>50000"}),
    ],
)
def test_suggester_live_smoke(source: str, params: dict) -> None:
    """Hit each real no-auth discovery endpoint. Skips if the network is unavailable."""
    try:
        rows = run_suggester(source, limit=3, **params)
    except Exception as exc:  # network/HTTP failure in a sandbox without egress
        pytest.skip(f"Live {source} suggest unavailable: {exc}")
    if not rows:
        pytest.skip(f"No suggestions returned for {source}")
    assert isinstance(rows[0], dict)
