"""Local-model embedding ranker (optional ``discovery-embeddings`` extra).

This module is imported lazily from :func:`fetchkit.discovery.ranking.get_ranker`,
so the default install never imports ``numpy`` or ``sentence_transformers``. The
ranker embeds the query and each candidate's :func:`feed_document` text with the
same local model, then ranks by cosine similarity. Encoded document vectors are
cached in-process, so a catalog feed is embedded at most once per process.

Shipping precomputed catalog vectors in the wheel is a deferred optimization; at
this catalog size encoding on first use is cheap.
"""

from typing import TYPE_CHECKING, Any

from fetchkit.discovery.errors import DiscoveryBackendUnavailable
from fetchkit.discovery.ranking import feed_document
from fetchkit.discovery.schemas import FeedMatch

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np

# Small, fast, widely-used default model.
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_SCORE_DECIMALS = 6

_INSTALL_HINT = (
    "The 'embedding' backend needs the optional extra. Install it with:\n"
    "    pip install 'fetchkit-agents[discovery-embeddings]'"
)


def embeddings_available() -> bool:
    """True if the optional embedding dependencies can be imported."""
    try:
        import numpy  # noqa: F401
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def _require_deps() -> None:
    """Raise a helpful error if the embedding extra is not installed."""
    if not embeddings_available():
        raise DiscoveryBackendUnavailable(_INSTALL_HINT)


class LocalEmbeddingRanker:
    """Ranks feeds by cosine similarity of local-model embeddings."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        """Build a ranker. Dependencies are checked eagerly so failures are clear."""
        _require_deps()
        self._model_name = model_name
        self._cache: dict[str, Any] = {}
        self._model: Any = None

    @classmethod
    def from_default(cls) -> "LocalEmbeddingRanker":
        """Build a ranker using the default model."""
        return cls()

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _encode(self, text: str) -> "np.ndarray":
        import numpy as np

        cached = self._cache.get(text)
        if cached is not None:
            return cached
        model = self._load_model()
        vector = np.asarray(model.encode(text, normalize_embeddings=True), dtype="float32")
        self._cache[text] = vector
        return vector

    def rank(self, query: str, candidates: list[FeedMatch]) -> list[FeedMatch]:
        """Score ``candidates`` by cosine similarity to ``query``, best first."""
        import numpy as np

        if not candidates:
            return []

        query_vec = self._encode(query)
        scored: list[tuple[float, str, FeedMatch]] = []
        for cand in candidates:
            # Vectors are L2-normalized, so the dot product is cosine similarity.
            similarity = float(np.dot(query_vec, self._encode(feed_document(cand))))
            score = round(similarity, _SCORE_DECIMALS)
            scored.append((score, cand.url, cand.model_copy(update={"score": score})))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [match for _, _, match in scored]


__all__ = ["LocalEmbeddingRanker", "embeddings_available", "DEFAULT_MODEL"]
