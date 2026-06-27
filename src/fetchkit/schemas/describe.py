"""Self-description: emit JSON Schema for every fetchkit config and output model.

fetchkit is meant to be a deterministic CLI primitive an agent shells out to. For
that to work the agent has to know *what* it can fetch and *how* to spell a config
without being told out of band. This module builds a single JSON document
describing the canonical output model (:class:`Post`), the top-level config, the
shared HTTP settings, and every builtin fetcher's typed config.

It leans entirely on Pydantic v2's ``model_json_schema()``, so the
``Field(description=...)`` text already attached to every model flows through
automatically — there is nothing to keep in sync by hand. New fetchers are picked
up for free because we iterate the same ``_BUILTIN_TYPES`` registry the validator
uses.
"""

from typing import Any

from fetchkit import __version__
from fetchkit.schemas.config import FetchKitConfig, HttpConfig
from fetchkit.schemas.fetcher import _BUILTIN_TYPES
from fetchkit.schemas.post import Post


def build_schema_document() -> dict[str, Any]:
    """Return a JSON-serializable description of every fetchkit schema.

    The document has the shape::

        {
          "version": "0.1.1",
          "config":  {<FetchKitConfig JSON Schema>},
          "http":    {<HttpConfig JSON Schema>},
          "fetchers": {"hackernews": {...}, "rss": {...}, ...},
          "post":    {<Post JSON Schema>}
        }
    """
    return {
        "version": __version__,
        "config": FetchKitConfig.model_json_schema(),
        "http": HttpConfig.model_json_schema(),
        "fetchers": {
            fetcher_type: config_cls.model_json_schema()
            for fetcher_type, config_cls in _BUILTIN_TYPES.items()
        },
        "post": Post.model_json_schema(),
    }
