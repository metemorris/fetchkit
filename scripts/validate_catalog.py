#!/usr/bin/env python3
"""Validate the shipped discovery catalog.

An offline maintainer tool (not shipped in the wheel). It checks that every
catalog entry parses against the ``CatalogEntry`` schema, that ``id``/``url`` are
unique, and that every ``url`` is http(s). The same invariants are enforced in CI
by ``tests/discovery/catalog_test.py``; this script is a fast local pre-commit
check after editing ``catalog.json``.

Usage::

    python scripts/validate_catalog.py
"""

import sys
from pathlib import Path

# Make ``src`` importable when run from a source checkout.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from fetchkit.discovery.schemas import Catalog  # noqa: E402

_CATALOG_PATH = _REPO_ROOT / "src" / "fetchkit" / "discovery" / "data" / "catalog.json"


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


if __name__ == "__main__":
    validate_catalog()
