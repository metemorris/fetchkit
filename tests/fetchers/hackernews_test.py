import responses
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from fetchkit.fetchers.hackernews import (
    fetch_posts,
    fetch_comments,
    _build_comment_tree,
    _hit_to_post,
    _hit_to_comment,
    ALGOLIA_API_BASE,
)
from fetchkit.fetchers.hackernews import fetch as fetch_via_protocol
from fetchkit.fetchers.base import FetcherResult
from fetchkit.schemas.fetcher import HackerNewsFetchConfig, PostFetchConfig, CommentFetchConfig, SortOrder
from fetchkit.schemas.fetcher import RSSFetchConfig, RSSFeedDescriptor
from fetchkit.schemas.post import Post, Comment, Source


@responses.activate
def test_fetch_posts_basic() -> None:
    start_time = datetime.now() - timedelta(hours=1)
    end_time = datetime.now()
    config = HackerNewsFetchConfig(
        start_time=start_time,
        end_time=end_time,
        posts=PostFetchConfig(max_items=2, order=SortOrder.TOP),
    )

    # Mock the Algolia /search endpoint
    responses.add(
        responses.GET,
        f"{ALGOLIA_API_BASE}/search",
        json={
            "hits": [
                {"objectID": "1", "title": "Post 1", "points": 100, "created_at": "2024-01-01T00:00:00Z"},
                {"objectID": "2", "title": "Post 2", "points": 50, "created_at": "2024-01-01T00:00:00Z"},
            ],
            "nbPages": 1,
        },
        status=200,
    )

    posts = fetch_posts(config)
    assert len(posts) == 2
    assert posts[0].id == "1"
    assert posts[1].id == "2"


def test_build_comment_tree_logical() -> None:
    c1 = Comment(id="1", author="a1", text="root", created_at=datetime.now(), replies=[])
    c2 = Comment(id="2", author="a2", text="child", parent_id="1", created_at=datetime.now(), replies=[])
    c3 = Comment(id="3", author="a3", text="grandchild", parent_id="2", created_at=datetime.now(), replies=[])

    comments = [c1, c2, c3]

    # Test depth 0 (roots only)
    roots_d0 = _build_comment_tree([c.model_copy(deep=True) for c in comments], max_depth=0)
    assert len(roots_d0) == 1
    assert len(roots_d0[0].replies) == 0

    # Test depth 1 (roots + children)
    roots_d1 = _build_comment_tree([c.model_copy(deep=True) for c in comments], max_depth=1)
    assert len(roots_d1) == 1
    assert len(roots_d1[0].replies) == 1
    assert len(roots_d1[0].replies[0].replies) == 0

    # Test depth 2
    roots_d2 = _build_comment_tree([c.model_copy(deep=True) for c in comments], max_depth=2)
    assert len(roots_d2) == 1
    assert len(roots_d2[0].replies[0].replies) == 1


@responses.activate
def test_fetch_comments_with_pagination() -> None:
    post_id = "123"
    config = CommentFetchConfig(fetch=True, max_items=2, max_depth=1, order=SortOrder.TOP)

    # Mock first page
    responses.add(
        responses.GET,
        f"{ALGOLIA_API_BASE}/search",
        json={
            "hits": [
                {"objectID": "c1", "comment_text": "text1", "points": 10, "parent_id": None},
                {"objectID": "c2", "comment_text": "text2", "points": 5, "parent_id": "c1"},
            ],
            "nbPages": 1,
        },
        status=200,
    )

    comments = fetch_comments(post_id, config)
    assert len(comments) > 0
    assert comments[0].id == "c1"
    assert len(comments[0].replies) == 1


def test_fetch_protocol_rejects_wrong_config_type() -> None:
    with pytest.raises(ValueError):
        fetch_via_protocol(RSSFetchConfig(feeds=[RSSFeedDescriptor(url="https://example.com/rss.xml")]))


def test_fetch_protocol_wraps_success() -> None:
    config = HackerNewsFetchConfig(
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
    )
    post = Post(
        id="1",
        source=Source.HACKERNEWS,
        title="ok",
        source_url="https://news.ycombinator.com/item?id=1",
    )
    with patch("fetchkit.fetchers.hackernews.fetch_posts", return_value=[post]):
        result = fetch_via_protocol(config)

    assert isinstance(result, FetcherResult)
    assert len(result.posts) == 1
    assert result.errors == []


def test_fetch_protocol_wraps_exception() -> None:
    config = HackerNewsFetchConfig(
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
    )
    with patch("fetchkit.fetchers.hackernews.fetch_posts", side_effect=RuntimeError("boom")):
        result = fetch_via_protocol(config)

    assert result.posts == []
    assert len(result.errors) == 1
    assert "boom" in str(result.errors[0])


def test_fetch_posts_comment_failure_is_isolated_per_post() -> None:
    config = HackerNewsFetchConfig(
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        posts=PostFetchConfig(max_items=2, order=SortOrder.TOP),
        comments=CommentFetchConfig(fetch=True, max_items=2, max_depth=1, order=SortOrder.TOP),
    )
    post1 = Post(id="1", source=Source.HACKERNEWS, title="p1", score=10, source_url="https://news.ycombinator.com/item?id=1")
    post2 = Post(id="2", source=Source.HACKERNEWS, title="p2", score=9, source_url="https://news.ycombinator.com/item?id=2")

    with patch("fetchkit.fetchers.hackernews._fetch_raw_posts", return_value=[post1, post2]):
        with patch(
            "fetchkit.fetchers.hackernews.fetch_comments",
            side_effect=[[Comment(id="c1", text="ok")], RuntimeError("comment API down")],
        ):
            result = fetch_posts(config)

    assert len(result) == 2
    assert [p.id for p in result] == ["1", "2"]
    assert len(result[0].comments) == 1
    assert result[1].comments == []


# ---------------------------------------------------------------------------
# Algolia hit -> canonical model converters
# ---------------------------------------------------------------------------

def test_hit_to_comment() -> None:
    hit = {
        "objectID": "123",
        "author": "user1",
        "comment_text": "Hello world",
        "points": 10,
        "created_at": "2024-01-01T00:00:00Z",
        "parent_id": 456,  # coerced from int
        "story_id": 789,  # coerced from int
    }
    comment = _hit_to_comment(hit)
    assert comment.id == "123"
    assert comment.author == "user1"
    assert comment.text == "Hello world"
    assert comment.score == 10
    assert comment.parent_id == "456"
    assert comment.story_id == "789"
    assert isinstance(comment.created_at, datetime)


def test_hit_to_comment_malformed() -> None:
    """Missing objectID falls back to a sentinel id."""
    comment = _hit_to_comment({"author": "bot", "comment_text": "spam"})
    assert comment.id == "unknown"
    assert comment.author == "bot"


def test_hit_to_post() -> None:
    hit = {
        "objectID": "111",
        "title": "Post Title",
        "story_text": "Post body",
        "url": "https://example.com",
        "author": "author1",
        "points": 100,
        "num_comments": 20,
        "created_at": "2024-01-01T00:00:00Z",
    }
    post = _hit_to_post(hit)
    assert post.id == "111"
    assert post.source == Source.HACKERNEWS
    assert post.title == "Post Title"
    assert post.text == "Post body"
    assert post.url == "https://example.com"
    assert post.score == 100
    assert post.comment_count == 20
    assert post.source_url == "https://news.ycombinator.com/item?id=111"


def test_hit_to_post_normalizes_datetime_to_utc() -> None:
    """Both aware and naive timestamps come out UTC-aware."""
    aware = _hit_to_post({"objectID": "1", "created_at": "2024-01-01T12:00:00Z"})
    assert aware.created_at is not None
    assert aware.created_at.tzinfo == timezone.utc

    naive = _hit_to_post({"objectID": "2", "created_at": "2024-01-01T12:00:00"})
    assert naive.created_at is not None
    assert naive.created_at.tzinfo == timezone.utc
