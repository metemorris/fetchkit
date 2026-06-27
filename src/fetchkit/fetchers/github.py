"""
GitHub fetcher.

Fetches from the public GitHub REST API (no auth required for public data, though
rate limits are tighter without a token). Two resources are supported:

- ``releases``: latest releases for one or more ``owner/name`` repos.
- ``search_repos``: repositories matching a search ``query``.

Repo/language/topic detail is preserved in ``Post.metadata``.
"""

import logging
from typing import Any

from fetchkit.http import get_default_client
from fetchkit.schemas.post import Post, Source
from fetchkit.schemas.fetcher import GitHubFetchConfig, FetcherConfig
from fetchkit.fetchers.base import FetcherResult
from fetchkit.fetchers.registry import register_fetcher

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
SOURCE_NAME = Source.GITHUB
DEFAULT_TIMEOUT_S = 15
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "fetchkit",  # GitHub rejects requests without a User-Agent.
}


def _in_window(post: Post, config: GitHubFetchConfig) -> bool:
    """True if the post falls within the configured time window (or no window)."""
    if config.start_time is None or config.end_time is None:
        return True
    if post.created_at is None:
        return False
    return config.start_time <= post.created_at <= config.end_time


def _release_to_post(repo: str, rel: dict[str, Any]) -> Post:
    """Convert a GitHub release payload into a canonical Post."""
    author = (rel.get("author") or {}).get("login")
    return Post(
        id=f"{repo}@{rel.get('id')}",
        source=SOURCE_NAME,
        title=rel.get("name") or rel.get("tag_name"),
        text=rel.get("body"),
        url=rel.get("html_url"),
        author=author,
        created_at=rel.get("published_at") or rel.get("created_at"),
        source_url=rel.get("html_url") or f"https://github.com/{repo}/releases",
        metadata={
            "repo": repo,
            "tag": rel.get("tag_name"),
            "prerelease": rel.get("prerelease"),
            "draft": rel.get("draft"),
        },
    )


def _repo_to_post(item: dict[str, Any]) -> Post:
    """Convert a GitHub repository search payload into a canonical Post."""
    return Post(
        id=str(item.get("id")),
        source=SOURCE_NAME,
        title=item.get("full_name"),
        text=item.get("description"),
        url=item.get("html_url"),
        author=(item.get("owner") or {}).get("login"),
        score=item.get("stargazers_count"),
        created_at=item.get("created_at"),
        source_url=item.get("html_url") or "https://github.com",
        metadata={
            "language": item.get("language"),
            "stars": item.get("stargazers_count"),
            "forks": item.get("forks_count"),
            "topics": item.get("topics") or [],
            "pushed_at": item.get("pushed_at"),
        },
    )


def fetch_posts(config: GitHubFetchConfig) -> list[Post]:
    """Fetch releases or repositories from GitHub per the config."""
    client = get_default_client()
    posts: list[Post] = []

    if config.resource == "search_repos":
        if not config.query:
            raise ValueError("github resource 'search_repos' requires a 'query'")
        params = {"q": config.query, "sort": "stars", "order": "desc",
                  "per_page": min(100, config.max_items)}
        resp = client.get(f"{API_BASE}/search/repositories", params=params,
                          headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
        resp.raise_for_status()
        for item in resp.json().get("items", [])[: config.max_items]:
            posts.append(_repo_to_post(item))
    else:  # releases
        if not config.repos:
            raise ValueError("github resource 'releases' requires at least one repo")
        per_repo = max(1, config.max_items // max(1, len(config.repos)))
        for repo in config.repos:
            params = {"per_page": min(100, per_repo)}
            resp = client.get(f"{API_BASE}/repos/{repo}/releases", params=params,
                              headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
            resp.raise_for_status()
            for rel in resp.json():
                posts.append(_release_to_post(repo, rel))

    posts = [p for p in posts if _in_window(p, config)]
    return posts[: config.max_items]


@register_fetcher("github")
def fetch(config: FetcherConfig) -> FetcherResult:
    """Fetcher protocol implementation for GitHub."""
    if not isinstance(config, GitHubFetchConfig):
        raise ValueError(f"Invalid config type for github fetcher: {type(config)}")
    try:
        return FetcherResult(posts=fetch_posts(config), errors=[])
    except Exception as e:
        return FetcherResult(posts=[], errors=[e])
