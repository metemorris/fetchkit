"""Deterministic tests for the pure-Python lexical ranker."""

from pathlib import Path

from fetchkit.discovery.catalog import load_catalog
from fetchkit.discovery.ranking import LexicalRanker, feed_document, tokenize
from fetchkit.discovery.schemas import FeedMatch

FIXTURE = str(Path(__file__).parent.parent / "testdata" / "discovery" / "catalog_fixture.json")


def _matches() -> list[FeedMatch]:
    """Build unscored FeedMatch candidates from the fixture catalog."""
    return [
        FeedMatch(
            url=e.url,
            name=e.name,
            description=e.description,
            topics=e.topics,
            category=e.category,
            language=e.language,
            homepage=e.homepage,
            source="catalog",
            score=0.0,
        )
        for e in load_catalog(FIXTURE).entries
    ]


def test_tokenize_drops_stopwords_and_short_tokens() -> None:
    tokens = tokenize("I need news about the Rust language")
    assert "rust" in tokens
    assert "language" in tokens
    assert "the" not in tokens  # stopword
    assert "i" not in tokens  # short + stopword


def test_feed_document_includes_key_fields() -> None:
    match = _matches()[0]  # rust-blog
    doc = feed_document(match)
    assert "Rust Blog" in doc
    assert "Topics:" in doc
    assert "Category:" in doc


def test_rust_query_ranks_rust_feed_first() -> None:
    ranked = LexicalRanker().rank("rust programming language", _matches())
    assert ranked[0].url == "https://blog.rust-lang.org/feed.xml"
    assert ranked[0].score > 0


def test_python_query_ranks_python_feed_first() -> None:
    ranked = LexicalRanker().rank("python tutorials for beginners", _matches())
    assert ranked[0].url == "https://realpython.com/atom.xml"


def test_ai_query_ranks_ai_research_first() -> None:
    ranked = LexicalRanker().rank("machine learning and AI research", _matches())
    assert ranked[0].name == "arXiv cs.AI"


def test_returns_all_candidates_sorted() -> None:
    matches = _matches()
    ranked = LexicalRanker().rank("rust", matches)
    assert len(ranked) == len(matches)
    scores = [m.score for m in ranked]
    assert scores == sorted(scores, reverse=True)


def test_empty_query_is_deterministic_and_url_ordered() -> None:
    # No query terms: all score 0, but order is stable (by url).
    ranked = LexicalRanker().rank("", _matches())
    assert all(m.score == 0.0 for m in ranked)
    urls = [m.url for m in ranked]
    assert urls == sorted(urls)
