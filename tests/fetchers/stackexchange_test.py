from datetime import datetime, timezone

import pytest
import responses

from fetchkit.fetchers.stackexchange import (
    fetch_posts,
    _question_to_post,
    _answer_to_comment,
    API_BASE,
)
from fetchkit.fetchers.stackexchange import fetch as fetch_via_protocol
from fetchkit.fetchers.base import FetcherResult
from fetchkit.schemas.fetcher import (
    StackExchangeFetchConfig,
    PostFetchConfig,
    CommentFetchConfig,
    SortOrder,
    RSSFetchConfig,
    RSSFeedDescriptor,
)

# 2026-06-20T00:00:00Z and 2026-06-21T00:00:00Z as unix epochs.
TS1 = 1781000000
TS2 = 1781100000

QUESTION = {
    "question_id": 42,
    "title": "How do I async in Python?",
    "body": "<p>Question body</p>",
    "link": "https://stackoverflow.com/q/42",
    "score": 99,
    "answer_count": 3,
    "creation_date": TS1,
    "tags": ["python", "asyncio"],
    "owner": {"display_name": "alice"},
    "is_answered": True,
    "accepted_answer_id": 100,
}

ANSWER = {
    "answer_id": 100,
    "question_id": 42,
    "body": "<p>Use asyncio.run</p>",
    "score": 50,
    "creation_date": TS1,
    "owner": {"display_name": "bob"},
    "is_accepted": True,
}


@responses.activate
def test_fetch_posts_basic() -> None:
    responses.add(
        responses.GET,
        f"{API_BASE}/questions",
        json={"items": [QUESTION], "has_more": False},
        status=200,
    )
    posts = fetch_posts(StackExchangeFetchConfig(posts=PostFetchConfig(max_items=10)))

    assert len(posts) == 1
    post = posts[0]
    assert post.id == "42"
    assert post.source == "stackexchange"
    assert post.title == "How do I async in Python?"
    assert post.text == "<p>Question body</p>"
    assert post.author == "alice"
    assert post.score == 99
    assert post.comment_count == 3
    assert post.source_url == "https://stackoverflow.com/q/42"
    assert post.metadata["tags"] == ["python", "asyncio"]
    assert post.metadata["accepted_answer_id"] == 100
    assert post.created_at == datetime.fromtimestamp(TS1, tz=timezone.utc)


@responses.activate
def test_search_uses_advanced_endpoint() -> None:
    responses.add(
        responses.GET,
        f"{API_BASE}/search/advanced",
        json={"items": [QUESTION], "has_more": False},
        status=200,
    )
    posts = fetch_posts(StackExchangeFetchConfig(query="async python"))
    assert len(posts) == 1
    # The advanced endpoint must have received the q parameter.
    assert "q=async" in responses.calls[0].request.url


@responses.activate
def test_fetch_posts_with_answers() -> None:
    responses.add(
        responses.GET,
        f"{API_BASE}/questions",
        json={"items": [QUESTION], "has_more": False},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/questions/42/answers",
        json={"items": [ANSWER], "has_more": False},
        status=200,
    )
    config = StackExchangeFetchConfig(
        comments=CommentFetchConfig(fetch=True, max_items=5),
    )
    posts = fetch_posts(config)
    assert len(posts[0].comments) == 1
    comment = posts[0].comments[0]
    assert comment.id == "100"
    assert comment.author == "bob"
    assert comment.score == 50
    assert comment.story_id == "42"


@responses.activate
def test_window_filtering_excludes_out_of_range() -> None:
    responses.add(
        responses.GET,
        f"{API_BASE}/questions",
        json={"items": [QUESTION], "has_more": False},
        status=200,
    )
    # Window starts after the question's creation date -> excluded.
    config = StackExchangeFetchConfig(
        start_time=datetime.fromtimestamp(TS2, tz=timezone.utc),
        end_time=datetime.fromtimestamp(TS2 + 1000, tz=timezone.utc),
    )
    assert fetch_posts(config) == []


def test_sort_mapping_in_params() -> None:
    cfg = StackExchangeFetchConfig(posts=PostFetchConfig(order=SortOrder.NEW))
    from fetchkit.fetchers.stackexchange import _base_params

    assert _base_params(cfg)["sort"] == "creation"


def test_answer_to_comment() -> None:
    comment = _answer_to_comment(ANSWER)
    assert comment.id == "100"
    assert comment.text == "<p>Use asyncio.run</p>"
    assert comment.story_id == "42"


def test_question_to_post_fallback_link() -> None:
    post = _question_to_post({"question_id": 7})
    assert post.source_url == "https://stackoverflow.com/q/7"


@responses.activate
def test_fetch_protocol_wraps_errors() -> None:
    responses.add(responses.GET, f"{API_BASE}/questions", status=404)
    result = fetch_via_protocol(StackExchangeFetchConfig())
    assert isinstance(result, FetcherResult)
    assert result.posts == []
    assert len(result.errors) == 1


def test_fetch_protocol_rejects_wrong_config_type() -> None:
    with pytest.raises(ValueError):
        fetch_via_protocol(RSSFetchConfig(feeds=[RSSFeedDescriptor(url="https://x/y.xml")]))
