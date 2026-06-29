"""Load and validate the shipped RSS feed catalog.

The catalog is package data (``data/catalog.json``) read via
:mod:`importlib.resources`, so it works from a wheel or an editable install. The
parsed catalog is cached per resolved path; tests inject a small fixture catalog
through the ``catalog_path`` argument instead of touching the shipped one.
"""

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Optional

from fetchkit.discovery.schemas import Catalog

_DATA_PACKAGE = "fetchkit.discovery.data"
_CATALOG_FILENAME = "catalog.json"


def _read_shipped_catalog_text() -> str:
    """Return the raw JSON text of the catalog shipped as package data."""
    resource = resources.files(_DATA_PACKAGE).joinpath(_CATALOG_FILENAME)
    return resource.read_text(encoding="utf-8")


@lru_cache(maxsize=8)
def _load_cached(catalog_path: Optional[str]) -> Catalog:
    """Parse and validate a catalog, caching by resolved path (None = shipped)."""
    if catalog_path is None:
        text = _read_shipped_catalog_text()
    else:
        text = Path(catalog_path).read_text(encoding="utf-8")
    data = json.loads(text)
    return Catalog.model_validate(data)


def load_catalog(catalog_path: Optional[str] = None) -> Catalog:
    """Load the feed catalog.

    Args:
        catalog_path: Override path to a catalog JSON file. Defaults to the
            catalog shipped with the package.

    Returns:
        The validated :class:`Catalog`.
    """
    return _load_cached(catalog_path)
