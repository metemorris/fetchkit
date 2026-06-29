# Discovery catalog

`catalog.json` is the curated set of RSS/Atom feeds that `fetchkit discover`
ranks against. It is the *head* of feed discovery: high-quality, long-lived feeds
across common categories. The open-web *tail* is reached separately, via
`find_feeds()` autodiscovery over sites a caller supplies, and (opt-in) an
external feed index — see `fetchkit/discovery/`.

## Why a curated catalog

RSS feeds are effectively infinite, and embeddings can only *rank* a set you
already hold — they cannot *enumerate* the web. So this catalog is deliberately
hand-curated rather than scraped: every entry is a feed worth recommending, with a
human-written `description` and `topics` that drive retrieval quality. A weak
description produces a weak match, so descriptions should read like *what the feed
is about*, not marketing copy.

## Schema

Each entry validates against `CatalogEntry` (`fetchkit/discovery/schemas.py`):

| field | required | notes |
|-------|----------|-------|
| `id` | yes | stable slug, unique within the catalog |
| `url` | yes | the feed URL (http(s) only) |
| `name` | yes | human-readable title |
| `description` | yes | 1–3 sentences; the primary retrieval text |
| `topics` | no | normalized tags, e.g. `["ai", "machine-learning"]` |
| `category` | no | coarse bucket: `news`, `research`, `programming`, `finance`, … |
| `language` | no | language code (default `en`) |
| `homepage` | no | the site the feed belongs to |

The top-level document carries `catalog_version` (an int). **Bump it on any
content change** so a precomputed embedding artifact built from an older version
is rejected at load time.

## Maintaining

- Add or edit entries directly in `catalog.json`, then bump `catalog_version`.
- Run the validator:

  ```bash
  python scripts/validate_catalog.py
  ```

  It checks the schema and rejects duplicate `id`/`url` and non-http(s) URLs.
- `tests/discovery/catalog_test.py` enforces these invariants in CI.

The embedding ranker encodes each feed's document at query time (cached
in-process); shipping precomputed catalog vectors in the wheel is a deferred
optimization.

This is intentionally a seed set. Expanding coverage (more publishers, languages,
and niches) is the main way to improve discovery quality over time.
