from datetime import datetime, timezone

import pytest
import responses

from fetchkit.fetchers.bluesky import fetch_posts, _to_post, _post_url, XRPC_BASE
from fetchkit.fetchers.bluesky import fetch as fetch_via_protocol
from fetchkit.fetchers.base import FetcherResult
from fetchkit.schemas.fetcher import BlueskyFetchConfig, RSSFetchConfig, RSSFeedDescriptor

POST_VIEW = {
    "uri": "at://did:plc:abc123/app.bsky.feed.post/3kxyz",
    "cid": "bafycid",
    "author": {"did": "did:plc:abc123", "handle": "alice.bsky.social"},
    "record": {"text": "hello bluesky", "createdAt": "2026-06-20T12:00:00Z", "langs": ["en"]},
    "likeCount": 12,
    "replyCount": 3,
    "repostCount": 4,
}


@responses.activate
def test_search_posts() -> None:
    responses.add(
        responses.GET,
        f"{XRPC_BASE}/app.bsky.feed.searchPosts",
        json={"posts": [POST_VIEW]},
        status=200,
    )
    posts = fetch_posts(BlueskyFetchConfig(resource="search", query="bluesky", max_items=10))

    assert len(posts) == 1
    post = posts[0]
    assert post.id == "at://did:plc:abc123/app.bsky.feed.post/3kxyz"
    assert post.source == "bluesky"
    assert post.text == "hello bluesky"
    assert post.author == "alice.bsky.social"
    assert post.score == 12
    assert post.comment_count == 3
    assert post.source_url == "https://bsky.app/profile/alice.bsky.social/post/3kxyz"
    assert post.metadata["cid"] == "bafycid"
    assert post.metadata["langs"] == ["en"]
    assert post.created_at == datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


@responses.activate
def test_author_feed_unwraps_post() -> None:
    responses.add(
        responses.GET,
        f"{XRPC_BASE}/app.bsky.feed.getAuthorFeed",
        json={"feed": [{"post": POST_VIEW}]},
        status=200,
    )
    posts = fetch_posts(BlueskyFetchConfig(resource="author_feed", actor="alice.bsky.social", max_items=10))
    assert len(posts) == 1
    assert posts[0].author == "alice.bsky.social"


@responses.activate
def test_window_filtering() -> None:
    responses.add(
        responses.GET,
        f"{XRPC_BASE}/app.bsky.feed.searchPosts",
        json={"posts": [POST_VIEW]},
        status=200,
    )
    config = BlueskyFetchConfig(
        resource="search",
        query="x",
        start_time=datetime(2026, 6, 21, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 22, tzinfo=timezone.utc),
    )
    assert fetch_posts(config) == []


@responses.activate
def test_search_terminates_on_repeating_cursor() -> None:
    # Page always returns a post outside the window plus the SAME cursor; the
    # guard must stop rather than spin forever. (responses replays the last
    # registered response, so an unbounded loop would hang this test.)
    responses.add(
        responses.GET,
        f"{XRPC_BASE}/app.bsky.feed.searchPosts",
        json={"posts": [POST_VIEW], "cursor": "stuck"},
        status=200,
    )
    config = BlueskyFetchConfig(
        resource="search",
        query="x",
        start_time=datetime(2099, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2099, 1, 2, tzinfo=timezone.utc),
    )
    assert fetch_posts(config) == []


def test_search_requires_query() -> None:
    with pytest.raises(ValueError):
        fetch_posts(BlueskyFetchConfig(resource="search"))


def test_author_feed_requires_actor() -> None:
    with pytest.raises(ValueError):
        fetch_posts(BlueskyFetchConfig(resource="author_feed"))


def test_post_url_from_uri_without_handle() -> None:
    url = _post_url("at://did:plc:abc123/app.bsky.feed.post/3kxyz", None)
    assert url == "https://bsky.app/profile/did:plc:abc123/post/3kxyz"


def test_to_post_skips_missing_uri() -> None:
    assert _to_post({"record": {"text": "no uri"}}) is None


@responses.activate
def test_fetch_protocol_wraps_errors() -> None:
    responses.add(responses.GET, f"{XRPC_BASE}/app.bsky.feed.searchPosts", status=404)
    result = fetch_via_protocol(BlueskyFetchConfig(resource="search", query="x"))
    assert isinstance(result, FetcherResult)
    assert result.posts == []
    assert len(result.errors) == 1


def test_fetch_protocol_rejects_wrong_config_type() -> None:
    with pytest.raises(ValueError):
        fetch_via_protocol(RSSFetchConfig(feeds=[RSSFeedDescriptor(url="https://x/y.xml")]))


@pytest.mark.live
def test_bluesky_live_smoke() -> None:
    """Hit the real public Bluesky AppView (no auth). Skips if the network is unavailable."""
    config = BlueskyFetchConfig(resource="search", query="python", max_items=3)
    result = fetch_via_protocol(config)
    if result.errors:
        pytest.skip(f"Live Bluesky unavailable: {result.errors[0]}")
    if not result.posts:
        pytest.skip("No posts returned")
    post = result.posts[0]
    assert post.source == "bluesky"
    assert post.source_url.startswith("http")
