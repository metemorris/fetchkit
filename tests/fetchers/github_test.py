import pytest
import responses

from fetchkit.fetchers.github import fetch_posts, API_BASE
from fetchkit.fetchers.github import fetch as fetch_via_protocol
from fetchkit.fetchers.base import FetcherResult
from fetchkit.schemas.fetcher import GitHubFetchConfig, RSSFetchConfig, RSSFeedDescriptor


@responses.activate
def test_fetch_releases() -> None:
    responses.add(
        responses.GET, f"{API_BASE}/repos/python/cpython/releases",
        json=[
            {
                "id": 42, "name": "v3.13.0", "tag_name": "v3.13.0",
                "body": "release notes", "html_url": "https://github.com/python/cpython/releases/v3.13.0",
                "published_at": "2026-06-20T00:00:00Z", "prerelease": False, "draft": False,
                "author": {"login": "octocat"},
            }
        ],
        status=200,
    )
    cfg = GitHubFetchConfig(repos=["python/cpython"], resource="releases", max_items=10)
    posts = fetch_posts(cfg)

    assert len(posts) == 1
    post = posts[0]
    assert post.id == "python/cpython@42"
    assert post.source == "github"
    assert post.title == "v3.13.0"
    assert post.author == "octocat"
    assert post.metadata["repo"] == "python/cpython"
    assert post.metadata["tag"] == "v3.13.0"


@responses.activate
def test_fetch_search_repos() -> None:
    responses.add(
        responses.GET, f"{API_BASE}/search/repositories",
        json={"items": [
            {
                "id": 7, "full_name": "pallets/flask", "description": "web framework",
                "html_url": "https://github.com/pallets/flask", "owner": {"login": "pallets"},
                "stargazers_count": 60000, "forks_count": 15000, "language": "Python",
                "topics": ["web"], "created_at": "2026-06-01T00:00:00Z", "pushed_at": "2026-06-25T00:00:00Z",
            }
        ]},
        status=200,
    )
    cfg = GitHubFetchConfig(resource="search_repos", query="language:python", max_items=10)
    posts = fetch_posts(cfg)

    assert len(posts) == 1
    assert posts[0].title == "pallets/flask"
    assert posts[0].score == 60000
    assert posts[0].metadata["language"] == "Python"


def test_search_repos_requires_query() -> None:
    with pytest.raises(ValueError, match="requires a 'query'"):
        fetch_posts(GitHubFetchConfig(resource="search_repos"))


def test_releases_requires_repos() -> None:
    with pytest.raises(ValueError, match="requires at least one repo"):
        fetch_posts(GitHubFetchConfig(resource="releases"))


@responses.activate
def test_fetch_protocol_wraps_errors() -> None:
    responses.add(responses.GET, f"{API_BASE}/repos/x/y/releases", status=404)
    result = fetch_via_protocol(GitHubFetchConfig(repos=["x/y"]))
    assert isinstance(result, FetcherResult)
    assert result.posts == []
    assert len(result.errors) == 1


def test_fetch_protocol_rejects_wrong_config_type() -> None:
    with pytest.raises(ValueError):
        fetch_via_protocol(RSSFetchConfig(feeds=[RSSFeedDescriptor(url="https://x/y.xml")]))
