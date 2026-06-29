"""Local-model embedding ranker (optional ``discovery-embeddings`` extra).

This module is imported lazily from :func:`fetchkit.discovery.ranking.get_ranker`,
so the default install never imports ``numpy`` or ``sentence_transformers``. The
ranker embeds the query and each candidate's :func:`feed_document` text with the
same local model, then ranks by cosine similarity.

A precomputed catalog embedding artifact (``data/embeddings.npy`` +
``data/embeddings_meta.json``, produced offline by
``scripts/build_discovery_index.py``) is used opportunistically when present,
keyed by feed URL, so shipped catalog feeds don't have to be re-encoded. Candidate
feeds without a precomputed vector are encoded on the fly and cached in-process.
"""

import json
from importlib import resources
from typing import TYPE_CHECKING, Any, Optional

from fetchkit.discovery.errors import DiscoveryBackendUnavailable
from fetchkit.discovery.ranking import feed_document
from fetchkit.discovery.schemas import FeedMatch

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np

_DATA_PACKAGE = "fetchkit.discovery.data"
_EMBEDDINGS_FILENAME = "embeddings.npy"
_META_FILENAME = "embeddings_meta.json"

# Small, fast, widely-used default model. Recorded in the artifact meta so the
# same model is used to embed queries at runtime.
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


def _load_precomputed() -> tuple[Optional[dict[str, "np.ndarray"]], Optional[str]]:
    """Load the shipped embedding artifact, if any.

    Returns a ``(vectors_by_url, model_name)`` pair. Both are ``None`` when no
    artifact is shipped (the common case — the artifact is opt-in/built on demand).
    """
    import numpy as np

    meta_res = resources.files(_DATA_PACKAGE).joinpath(_META_FILENAME)
    emb_res = resources.files(_DATA_PACKAGE).joinpath(_EMBEDDINGS_FILENAME)
    if not (meta_res.is_file() and emb_res.is_file()):
        return None, None

    meta = json.loads(meta_res.read_text(encoding="utf-8"))
    urls: list[str] = meta["urls"]
    model_name: str = meta.get("model", DEFAULT_MODEL)
    with resources.as_file(emb_res) as path:
        matrix = np.load(path)
    vectors = {url: matrix[i] for i, url in enumerate(urls)}
    return vectors, model_name


class LocalEmbeddingRanker:
    """Ranks feeds by cosine similarity of local-model embeddings."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        vectors_by_url: Optional[dict[str, "np.ndarray"]] = None,
    ) -> None:
        """Build a ranker. Dependencies are checked eagerly so failures are clear."""
        _require_deps()
        self._model_name = model_name
        self._vectors_by_url = vectors_by_url or {}
        self._cache: dict[str, Any] = {}
        self._model: Any = None

    @classmethod
    def from_default(cls) -> "LocalEmbeddingRanker":
        """Build a ranker, loading the shipped embedding artifact if present."""
        _require_deps()
        vectors, model_name = _load_precomputed()
        return cls(model_name=model_name or DEFAULT_MODEL, vectors_by_url=vectors)

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
            vec = self._vectors_by_url.get(cand.url)
            if vec is None:
                vec = self._encode(feed_document(cand))
            # Vectors are L2-normalized, so the dot product is cosine similarity.
            similarity = float(np.dot(query_vec, vec))
            score = round(similarity, _SCORE_DECIMALS)
            scored.append((score, cand.url, cand.model_copy(update={"score": score})))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [match for _, _, match in scored]


__all__ = [
    "LocalEmbeddingRanker",
    "embeddings_available",
    "DEFAULT_MODEL",
    "DiscoveryBackendUnavailable",
]
