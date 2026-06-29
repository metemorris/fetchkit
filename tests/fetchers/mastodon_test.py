from datetime import datetime, timezone

import pytest
import responses

from fetchkit.fetchers.mastodon import fetch_posts, _strip_html, _endpoint, _to_post
from fetchkit.fetchers.mastodon import fetch as fetch_via_protocol
from fetchkit.fetchers.base import FetcherResult
from fetchkit.schemas.fetcher import MastodonFetchConfig, RSSFetchConfig, RSSFeedDescriptor

STATUS = {
    "id": "111222333",
    "created_at": "2026-06-20T08:30:00Z",
    "content": "<p>Hello <a href='#'>#ai</a> world</p>",
    "url": "https://mastodon.social/@alice/111222333",
    "account": {"acct": "alice", "username": "alice", "display_name": "Alice"},
    "favourites_count": 9,
    "reblogs_count": 2,
    "replies_count": 4,
    "tags": [{"name": "ai", "url": "https://mastodon.social/tags/ai"}],
    "visibility": "public",
    "language": "en",
}


@responses.activate
def test_fetch_tag_timeline() -> None:
    responses.add(
        responses.GET,
        "https://mastodon.social/api/v1/timelines/tag/ai",
        json=[STATUS],
        status=200,
    )
    posts = fetch_posts(MastodonFetchConfig(resource="tag", tag="ai", max_items=10))

    assert len(posts) == 1
    post = posts[0]
    assert post.id == "111222333"
    assert post.source == "mastodon"
    assert post.text == "Hello #ai world"
    assert post.author == "alice"
    assert post.score == 9
    assert post.comment_count == 4
    assert post.url == "https://mastodon.social/@alice/111222333"
    assert post.source_url == "https://mastodon.social/@alice/111222333"
    assert post.metadata["tags"] == ["ai"]
    assert post.metadata["instance"] == "mastodon.social"
    assert post.metadata["reblogs_count"] == 2
    assert post.created_at == datetime(2026, 6, 20, 8, 30, tzinfo=timezone.utc)


@responses.activate
def test_fetch_public_timeline() -> None:
    responses.add(
        responses.GET,
        "https://fosstodon.org/api/v1/timelines/public",
        json=[STATUS],
        status=200,
    )
    posts = fetch_posts(MastodonFetchConfig(instance="fosstodon.org", resource="public", max_items=10))
    assert len(posts) == 1


@responses.activate
def test_window_filtering() -> None:
    responses.add(
        responses.GET,
        "https://mastodon.social/api/v1/timelines/tag/ai",
        json=[STATUS],
        status=200,
    )
    config = MastodonFetchConfig(
        resource="tag",
        tag="ai",
        start_time=datetime(2026, 6, 21, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 22, tzinfo=timezone.utc),
    )
    assert fetch_posts(config) == []


def test_strip_html() -> None:
    assert _strip_html("<p>line one</p><p>line two</p>") == "line one\nline two"
    assert _strip_html("a<br>b") == "a\nb"
    assert _strip_html("&amp; &lt;tag&gt;") == "& <tag>"
    assert _strip_html(None) is None
    assert _strip_html("") is None


def test_endpoint_selection() -> None:
    assert _endpoint(MastodonFetchConfig(resource="tag", tag="rust")).endswith("/timelines/tag/rust")
    assert _endpoint(MastodonFetchConfig(resource="public")).endswith("/timelines/public")


def test_tag_requires_tag() -> None:
    with pytest.raises(ValueError):
        _endpoint(MastodonFetchConfig(resource="tag"))


def test_to_post_uses_uri_when_url_missing() -> None:
    status = dict(STATUS)
    del status["url"]
    status["uri"] = "https://mastodon.social/users/alice/statuses/111222333"
    post = _to_post(status, "mastodon.social")
    assert post.source_url == "https://mastodon.social/users/alice/statuses/111222333"


@responses.activate
def test_fetch_protocol_wraps_errors() -> None:
    responses.add(
        responses.GET,
        "https://mastodon.social/api/v1/timelines/tag/ai",
        status=401,
    )
    result = fetch_via_protocol(MastodonFetchConfig(resource="tag", tag="ai"))
    assert isinstance(result, FetcherResult)
    assert result.posts == []
    assert len(result.errors) == 1


def test_fetch_protocol_rejects_wrong_config_type() -> None:
    with pytest.raises(ValueError):
        fetch_via_protocol(RSSFetchConfig(feeds=[RSSFeedDescriptor(url="https://x/y.xml")]))
