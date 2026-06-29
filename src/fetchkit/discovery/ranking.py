"""Rank feed candidates against a natural-language query.

The ranker is the only place "semantic matching" happens, and it scores an
arbitrary list of :class:`~fetchkit.discovery.schemas.FeedMatch` candidates —
whether they came from the curated catalog, runtime autodiscovery, or an external
index. Embeddings are therefore a *ranking* layer over candidates you already
hold, not a way to search the open web.

Two backends share one :class:`Ranker` protocol:

- :class:`LexicalRanker` — pure-Python BM25 over each feed's text. Zero extra
  dependencies, fully deterministic, always available (the default).
- the embedding ranker (in :mod:`fetchkit.discovery.embedding`) — higher quality,
  but behind the ``discovery-embeddings`` extra and imported lazily so the default
  path never pulls numpy/torch.

Ranking is deterministic: ties are broken by feed ``url`` and scores are rounded.
"""

import math
import re
from collections import Counter
from typing import Protocol, runtime_checkable

from fetchkit.discovery.schemas import FeedMatch

# BM25 parameters (standard defaults).
_BM25_K1 = 1.5
_BM25_B = 0.75

# Score precision for deterministic, stable output.
_SCORE_DECIMALS = 6

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A small, generic stopword set. Kept short on purpose — feed metadata is terse,
# so over-aggressive stopping hurts more than it helps.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with",
        "from", "by", "about", "is", "are", "be", "this", "that", "it", "as",
        "at", "i", "we", "you", "need", "want", "looking", "regarding",
    }
)


def feed_document(match: FeedMatch) -> str:
    """Assemble the text that represents a feed for retrieval.

    This is exactly what gets tokenized (lexical) or embedded (embedding backend):
    the feed's name, its description, its topics, and its category. The quality of
    discovery is bounded by the quality of this text.
    """
    parts: list[str] = []
    if match.name:
        parts.append(match.name)
    if match.description:
        parts.append(match.description)
    if match.topics:
        parts.append("Topics: " + ", ".join(match.topics))
    if match.category:
        parts.append("Category: " + match.category)
    return ". ".join(parts)


def tokenize(text: str) -> list[str]:
    """Lowercase, split into alphanumeric tokens, and drop stopwords."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


@runtime_checkable
class Ranker(Protocol):
    """Scores feed candidates against a query and returns them sorted, best first."""

    def rank(self, query: str, candidates: list[FeedMatch]) -> list[FeedMatch]:
        """Return ``candidates`` with ``score`` set, sorted by descending relevance.

        The full list is returned (not truncated); the caller applies ``top_k`` and
        any ``min_score`` filtering so those concerns stay in one place.
        """
        ...


class LexicalRanker:
    """Pure-Python BM25 ranker over feed metadata. Deterministic, no extra deps."""

    def rank(self, query: str, candidates: list[FeedMatch]) -> list[FeedMatch]:
        """Score ``candidates`` with BM25 using the candidate set as the corpus."""
        query_terms = tokenize(query)
        docs = [tokenize(feed_document(c)) for c in candidates]

        scored: list[tuple[float, str, FeedMatch]] = []
        if not query_terms or not candidates:
            # No query signal: everything scores 0, but stay deterministic.
            for cand in candidates:
                scored.append((0.0, cand.url, cand.model_copy(update={"score": 0.0})))
        else:
            n_docs = len(docs)
            avgdl = sum(len(d) for d in docs) / n_docs if n_docs else 0.0
            doc_freq = self._document_frequencies(docs)
            for cand, doc in zip(candidates, docs):
                raw = self._bm25(query_terms, doc, doc_freq, n_docs, avgdl)
                score = round(raw, _SCORE_DECIMALS)
                scored.append((score, cand.url, cand.model_copy(update={"score": score})))

        # Sort by score desc, then url asc for a stable, deterministic order.
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [match for _, _, match in scored]

    @staticmethod
    def _document_frequencies(docs: list[list[str]]) -> Counter[str]:
        """Count, per term, how many documents contain it."""
        df: Counter[str] = Counter()
        for doc in docs:
            df.update(set(doc))
        return df

    @staticmethod
    def _bm25(
        query_terms: list[str],
        doc: list[str],
        doc_freq: Counter[str],
        n_docs: int,
        avgdl: float,
    ) -> float:
        """BM25 score of one document for the query terms."""
        if not doc:
            return 0.0
        term_freq = Counter(doc)
        dl = len(doc)
        score = 0.0
        for term in query_terms:
            tf = term_freq.get(term, 0)
            if tf == 0:
                continue
            df = doc_freq.get(term, 0)
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            denom = tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl) if avgdl else tf
            score += idf * (tf * (_BM25_K1 + 1)) / denom
        return score


def get_ranker(backend: str = "auto") -> Ranker:
    """Return a ranker for ``backend``.

    - ``"lexical"`` — always the pure-Python BM25 ranker.
    - ``"embedding"`` — the local-model ranker; raises
      :class:`DiscoveryBackendUnavailable` if the ``discovery-embeddings`` extra
      is not installed.
    - ``"auto"`` (default) — the embedding ranker if its extra is available, else
      lexical. Never raises for a missing extra.
    """
    if backend == "lexical":
        return LexicalRanker()

    if backend in ("embedding", "auto"):
        # Imported lazily so the default path never imports numpy/sentence-transformers.
        from fetchkit.discovery.embedding import (
            LocalEmbeddingRanker,
            embeddings_available,
        )

        if backend == "embedding":
            return LocalEmbeddingRanker.from_default()
        if embeddings_available():
            return LocalEmbeddingRanker.from_default()
        return LexicalRanker()

    raise ValueError(
        f"Unknown ranker backend: {backend!r}. Choose 'auto', 'lexical', or 'embedding'."
    )


__all__ = [
    "Ranker",
    "LexicalRanker",
    "get_ranker",
    "feed_document",
    "tokenize",
]
