#!/usr/bin/env python3
"""Validate the discovery catalog and (optionally) build its embedding artifact.

This is an offline maintainer tool — it is not shipped in the wheel. It:

  1. validates every catalog entry against the ``CatalogEntry`` schema,
  2. rejects duplicate ``id``/``url`` and non-http(s) URLs,
  3. with ``--embed`` (needs the ``discovery-embeddings`` extra), encodes each
     feed's document and writes ``embeddings.npy`` + ``embeddings_meta.json``
     next to ``catalog.json``.

Usage::

    python scripts/build_discovery_index.py            # validate only
    python scripts/build_discovery_index.py --embed     # validate + build embeddings
"""

import argparse
import json
import sys
from pathlib import Path

# Make ``src`` importable when run from a source checkout.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from fetchkit.discovery.ranking import feed_document  # noqa: E402
from fetchkit.discovery.schemas import Catalog, FeedMatch  # noqa: E402

_DATA_DIR = _REPO_ROOT / "src" / "fetchkit" / "discovery" / "data"
_CATALOG_PATH = _DATA_DIR / "catalog.json"
_EMBEDDINGS_PATH = _DATA_DIR / "embeddings.npy"
_META_PATH = _DATA_DIR / "embeddings_meta.json"


def validate_catalog() -> Catalog:
    """Parse and validate the catalog, raising on any integrity problem."""
    catalog = Catalog.model_validate_json(_CATALOG_PATH.read_text(encoding="utf-8"))

    ids: set[str] = set()
    urls: set[str] = set()
    for entry in catalog.entries:
        if entry.id in ids:
            raise ValueError(f"Duplicate catalog id: {entry.id!r}")
        if entry.url in urls:
            raise ValueError(f"Duplicate catalog url: {entry.url!r}")
        if not entry.url.startswith(("http://", "https://")):
            raise ValueError(f"Entry {entry.id!r} has a non-http(s) url: {entry.url!r}")
        ids.add(entry.id)
        urls.add(entry.url)

    print(f"OK: catalog version {catalog.catalog_version}, {len(catalog.entries)} entries valid.")
    return catalog


def build_embeddings(catalog: Catalog) -> None:
    """Encode each feed's document and write the embedding artifact + meta."""
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - tooling path
        raise SystemExit(
            "--embed needs the embedding extra: "
            "pip install 'fetchkit-agents[discovery-embeddings]'"
        ) from exc

    from fetchkit.discovery.embedding import DEFAULT_MODEL

    model = SentenceTransformer(DEFAULT_MODEL)
    documents = [
        feed_document(
            FeedMatch(
                url=e.url,
                name=e.name,
                description=e.description,
                topics=e.topics,
                category=e.category,
                source="catalog",
                score=0.0,
            )
        )
        for e in catalog.entries
    ]
    matrix = np.asarray(
        model.encode(documents, normalize_embeddings=True), dtype="float32"
    )
    np.save(_EMBEDDINGS_PATH, matrix)
    meta = {
        "model": DEFAULT_MODEL,
        "dimension": int(matrix.shape[1]),
        "normalized": True,
        "catalog_version": catalog.catalog_version,
        "urls": [e.url for e in catalog.entries],
    }
    _META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {_EMBEDDINGS_PATH.name} ({matrix.shape}) and {_META_PATH.name}.")


def main() -> int:
    """Entry point: validate, then optionally build embeddings."""
    parser = argparse.ArgumentParser(description="Validate/build the discovery index.")
    parser.add_argument(
        "--embed", action="store_true", help="Also (re)build the embedding artifact."
    )
    args = parser.parse_args()

    catalog = validate_catalog()
    if args.embed:
        build_embeddings(catalog)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
