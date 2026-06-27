import pytest
import responses

from fetchkit.fetchers.lobsters import fetch_posts, BASE_URL, _endpoint
from fetchkit.fetchers.lobsters import fetch as fetch_via_protocol
from fetchkit.fetchers.base import FetcherResult
from fetchkit.schemas.fetcher import LobstersFetchConfig, RSSFetchConfig, RSSFeedDescriptor

STORY = {
    "short_id": "abc123",
    "title": "A great post",
    "url": "https://example.com/post",
    "score": 42,
    "comment_count": 7,
    "created_at": "2026-06-20T00:00:00Z",
    "comments_url": "https://lobste.rs/s/abc123",
    "submitter_user": {"username": "alice"},
    "tags": ["rust", "programming"],
    "description": "body text",
}


def test_endpoint_selection() -> None:
    assert _endpoint(LobstersFetchConfig(listing="newest")) == f"{BASE_URL}/newest.json"
    assert _endpoint(LobstersFetchConfig(tag="rust")) == f"{BASE_URL}/t/rust.json"


@responses.activate
def test_fetch_posts_hottest() -> None:
    responses.add(responses.GET, f"{BASE_URL}/hottest.json", json=[STORY], status=200)
    posts = fetch_posts(LobstersFetchConfig(listing="hottest", max_items=10))

    assert len(posts) == 1
    post = posts[0]
    assert post.id == "abc123"
    assert post.source == "lobsters"
    assert post.title == "A great post"
    assert post.url == "https://example.com/post"
    assert post.source_url == "https://lobste.rs/s/abc123"
    assert post.author == "alice"
    assert post.score == 42
    assert post.comment_count == 7
    assert post.metadata["tags"] == ["rust", "programming"]


@responses.activate
def test_submitter_user_as_string() -> None:
    story = dict(STORY, submitter_user="bob")
    responses.add(responses.GET, f"{BASE_URL}/hottest.json", json=[story], status=200)
    posts = fetch_posts(LobstersFetchConfig())
    assert posts[0].author == "bob"


@responses.activate
def test_fetch_protocol_wraps_errors() -> None:
    responses.add(responses.GET, f"{BASE_URL}/hottest.json", status=404)
    result = fetch_via_protocol(LobstersFetchConfig())
    assert isinstance(result, FetcherResult)
    assert result.posts == []
    assert len(result.errors) == 1


def test_fetch_protocol_rejects_wrong_config_type() -> None:
    with pytest.raises(ValueError):
        fetch_via_protocol(RSSFetchConfig(feeds=[RSSFeedDescriptor(url="https://x/y.xml")]))
