"""CLI tests for `fetchkit discover` and `fetchkit find-feeds`."""

import json
from unittest.mock import patch

import pytest

from fetchkit.cli import main
from fetchkit.discovery.schemas import FeedCandidate


def test_discover_emits_clean_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["discover", "rust programming language", "--backend", "lexical"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)  # stdout must be valid JSON
    assert set(payload) == {"query", "backend", "catalog_version", "count", "matches"}
    assert payload["query"] == "rust programming language"
    assert payload["count"] >= 1
    assert payload["matches"][0]["url"] == "https://blog.rust-lang.org/feed.xml"
    assert payload["matches"][0]["source"] == "catalog"


def test_discover_top_k_limits(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["discover", "news", "--backend", "lexical", "--top-k", "3"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] <= 3


def test_discover_compact_is_single_line(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["discover", "ai", "--backend", "lexical", "--compact"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert "\n" not in out


def test_discover_as_config_emits_runnable_config(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["discover", "programming", "--backend", "lexical", "--top-k", "2", "--as-config"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    # A full FetchKitConfig with a single rss fetcher, ready for `fetchkit run`.
    assert list(payload) == ["fetchers"]
    fetcher = payload["fetchers"][0]
    assert fetcher["type"] == "rss"
    assert len(fetcher["feeds"]) == 2
    assert fetcher["feeds"][0]["url"].startswith("http")


def test_discover_embedding_without_extra_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    # Force the embedding extra to look absent so the path is deterministic.
    with patch("fetchkit.discovery.embedding.embeddings_available", return_value=False):
        code = main(["discover", "ai", "--backend", "embedding"])
    assert code == 2
    assert "discovery-embeddings" in capsys.readouterr().err


def test_find_feeds_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    candidate = FeedCandidate(
        url="https://example.com/feed.xml", name="Example Feed", description="hi"
    )
    with patch("fetchkit.discovery.find_feeds", return_value=[candidate]):
        code = main(["find-feeds", "https://example.com"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["feeds"][0]["url"] == "https://example.com/feed.xml"
    assert payload["errors"] == []
