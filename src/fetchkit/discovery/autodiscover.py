"""Discover RSS/Atom feeds from a site URL.

You cannot semantically search the open web's feeds — but given a site you *can*
extract its feeds. This module does exactly that: fetch a page, read the RSS
autodiscovery ``<link rel="alternate">`` tags from its HTML head, probe a handful
of conventional feed paths as a fallback, and validate each candidate with
feedparser. An agent supplies the sites (from its own web search); fetchkit turns
"these sites" into "these real, validated feeds."

The same SSRF guard the RSS fetcher uses (:func:`guard_public_url`) is applied to
every URL fetched here, so an agent-supplied site cannot point fetchkit at an
internal address.
"""

import logging
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse

import feedparser

from fetchkit.discovery.schemas import FeedCandidate
from fetchkit.http import get_default_client, guard_public_url
from fetchkit.http.client import HttpClient

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 10

# MIME types that mark a <link rel="alternate"> as a feed.
_FEED_TYPES = frozenset(
    {"application/rss+xml", "application/atom+xml", "application/feed+json"}
)

# Conventional feed paths probed when a page declares no <link> feeds.
_COMMON_PATHS = (
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/index.xml",
    "/?feed=rss2",
    "/feeds/posts/default",
)

# Cap how many recent entry titles we fold into a feed's description for ranking.
_MAX_SAMPLE_TITLES = 5


class _FeedLinkParser(HTMLParser):
    """Collect ``href``s of feed ``<link rel="alternate">`` tags from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.feed_hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "link":
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        rel = attr.get("rel", "").lower()
        type_ = attr.get("type", "").lower()
        href = attr.get("href", "")
        if "alternate" in rel and type_ in _FEED_TYPES and href:
            self.feed_hrefs.append(href)


def _parse_feed_links(html: str, base_url: str) -> list[str]:
    """Return absolute feed URLs declared via autodiscovery ``<link>`` tags."""
    parser = _FeedLinkParser()
    parser.feed(html)
    return [urljoin(base_url, href) for href in parser.feed_hrefs]


def _common_path_candidates(base_url: str) -> list[str]:
    """Return conventional feed URLs rooted at ``base_url``'s scheme + host."""
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    return [urljoin(root, path) for path in _COMMON_PATHS]


def _build_description(parsed_feed: feedparser.FeedParserDict) -> Optional[str]:
    """Compose a description from the feed's subtitle plus recent entry titles."""
    feed = parsed_feed.feed
    parts: list[str] = []
    base = feed.get("subtitle") or feed.get("description")
    if base:
        parts.append(str(base))
    titles = [
        str(e.get("title")) for e in parsed_feed.entries[:_MAX_SAMPLE_TITLES] if e.get("title")
    ]
    if titles:
        parts.append("Recent: " + " | ".join(titles))
    return " — ".join(parts) if parts else None


def _validate_feed(feed_url: str, client: HttpClient) -> Optional[FeedCandidate]:
    """Fetch and parse ``feed_url``; return a candidate if it is a real feed."""
    try:
        guard_public_url(feed_url)
        response = client.get(feed_url, timeout=DEFAULT_TIMEOUT_S)
        response.raise_for_status()
    except Exception as exc:
        logger.debug("Feed candidate %s rejected: %s", feed_url, exc)
        return None

    parsed = feedparser.parse(response.content)
    title = parsed.feed.get("title")
    # A real feed has either a channel title or at least one entry.
    if not title and not parsed.entries:
        return None

    return FeedCandidate(
        url=feed_url,
        name=str(title) if title else None,
        description=_build_description(parsed),
        language=parsed.feed.get("language"),
        homepage=parsed.feed.get("link"),
    )


def find_feeds(
    url: str,
    *,
    max_feeds: int = 10,
    client: Optional[HttpClient] = None,
) -> list[FeedCandidate]:
    """Discover and validate RSS/Atom feeds reachable from a site ``url``.

    Strategy: fetch the page, prefer feeds declared via ``<link rel="alternate">``
    autodiscovery, then fall back to probing conventional paths. Every candidate
    is validated by actually parsing it as a feed.

    Args:
        url: The site (or page) URL to discover feeds from.
        max_feeds: Stop after this many validated feeds.
        client: HTTP client to use; defaults to the shared client.

    Returns:
        Validated :class:`FeedCandidate` objects (possibly empty).

    Raises:
        BlockedURLError: if ``url`` itself is not a publicly routable http(s) URL.
    """
    guard_public_url(url)
    client = client or get_default_client()

    candidates: list[str] = []
    try:
        response = client.get(url, timeout=DEFAULT_TIMEOUT_S)
        response.raise_for_status()
        candidates.extend(_parse_feed_links(response.text, url))
    except Exception as exc:
        # The page might be unreachable or itself a feed; fall through to probing.
        logger.debug("Could not read page %s for autodiscovery: %s", url, exc)

    candidates.extend(_common_path_candidates(url))
    # The page URL itself may already be a feed.
    candidates.append(url)

    results: list[FeedCandidate] = []
    seen: set[str] = set()
    for candidate_url in candidates:
        if candidate_url in seen:
            continue
        seen.add(candidate_url)
        candidate = _validate_feed(candidate_url, client)
        if candidate is not None:
            results.append(candidate)
        if len(results) >= max_feeds:
            break
    return results


__all__ = ["find_feeds"]
