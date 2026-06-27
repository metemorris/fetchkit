from datetime import datetime
from fetchkit.schemas.post import Post, Comment, Source


def test_comment_from_api() -> None:
    hit = {
        "objectID": "123",
        "author": "user1",
        "comment_text": "Hello world",
        "points": 10,
        "created_at": "2024-01-01T00:00:00Z",
        "parent_id": 456,  # Test coercion from int
        "story_id": 789,  # Test coercion from int
    }
    comment = Comment.from_api(hit)
    assert comment.id == "123"
    assert comment.author == "user1"
    assert comment.text == "Hello world"
    assert comment.score == 10
    assert comment.parent_id == "456"
    assert comment.story_id == "789"
    assert isinstance(comment.created_at, datetime)


def test_post_from_api() -> None:
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
    source = Source.HACKERNEWS
    url_template = "https://news.ycombinator.com/item?id={item_id}"

    post = Post.from_api(hit, source, url_template)
    assert post.id == "111"
    assert post.source == source
    assert post.title == "Post Title"
    assert post.text == "Post body"
    assert post.url == "https://example.com"
    assert post.score == 100
    assert post.comment_count == 20
    assert post.source_url == "https://news.ycombinator.com/item?id=111"


def test_comment_from_api_malformed() -> None:
    """Test handling of malformed/missing API data."""
    hit = {"author": "bot", "comment_text": "spam"}
    comment = Comment.from_api(hit)
    assert comment.id == "unknown"
    assert comment.author == "bot"
