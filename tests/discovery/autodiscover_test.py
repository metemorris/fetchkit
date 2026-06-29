"""Tests for site -> feed autodiscovery (the open-web tail)."""

from pathlib import Path
from unittest.mock import patch

import pytest
import responses

from fetchkit.discovery.autodiscover import find_feeds
from fetchkit.http.client import HttpClient
from fetchkit.http.ssrf import BlockedURLError
from fetchkit.schemas.config import HttpConfig

FIXTURE_DIR = Path(__file__).parent.parent / "testdata" / "discovery"
PAGE_HTML = (FIXTURE_DIR / "sample_page.html").read_text(encoding="utf-8")
FEED_XML = (FIXTURE_DIR / "sample_feed.xml").read_text(encoding="utf-8")


def _no_retry_client() -> HttpClient:
    # max_retries=0 so unregistered common-path probes fail instantly (no backoff sleeps).
    return HttpClient(HttpConfig(max_retries=0, backoff_factor=0.0))


@responses.activate
def test_find_feeds_via_autodiscovery_link() -> None:
    responses.add(
        responses.GET, "https://example.com/", body=PAGE_HTML, status=200,
        content_type="text/html",
    )
    responses.add(
        responses.GET, "https://example.com/feed.xml", body=FEED_XML, status=200,
        content_type="application/rss+xml",
    )

    with patch("fetchkit.discovery.autodiscover.guard_public_url"):
        feeds = find_feeds("https://example.com/", client=_no_retry_client())

    urls = [f.url for f in feeds]
    assert "https://example.com/feed.xml" in urls
    feed = next(f for f in feeds if f.url.endswith("/feed.xml"))
    assert feed.name == "Example Feed"
    # Recent entry titles are folded into the description for ranking.
    assert feed.description is not None
    assert "Recent:" in feed.description


@responses.activate
def test_find_feeds_via_common_path_probe() -> None:
    # Page declares no feed links; the feed is found by probing /feed.
    responses.add(
        responses.GET, "https://example.org/", body="<html><head></head></html>",
        status=200, content_type="text/html",
    )
    responses.add(
        responses.GET, "https://example.org/feed", body=FEED_XML, status=200,
        content_type="application/rss+xml",
    )

    with patch("fetchkit.discovery.autodiscover.guard_public_url"):
        feeds = find_feeds("https://example.org/", client=_no_retry_client())

    assert any(f.url == "https://example.org/feed" for f in feeds)


def test_find_feeds_blocks_private_address() -> None:
    # The SSRF guard rejects an internal target before any request is made.
    with pytest.raises(BlockedURLError):
        find_feeds("http://127.0.0.1/", client=_no_retry_client())


@responses.activate
def test_find_feeds_respects_max_feeds() -> None:
    responses.add(
        responses.GET, "https://example.com/", body=PAGE_HTML, status=200,
        content_type="text/html",
    )
    responses.add(
        responses.GET, "https://example.com/feed.xml", body=FEED_XML, status=200,
        content_type="application/rss+xml",
    )
    with patch("fetchkit.discovery.autodiscover.guard_public_url"):
        feeds = find_feeds("https://example.com/", max_feeds=1, client=_no_retry_client())
    assert len(feeds) <= 1
