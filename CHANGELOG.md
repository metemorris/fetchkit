# Changelog

All notable changes to fetchkit are documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/) and uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **RSS feed discovery** (`fetchkit.discovery`, optional subpackage). Maps a
  natural-language use case onto real RSS feeds an agent can fetch, closing the
  gap where the `rss` fetcher requires a feed URL the agent must already know.
  - `discover(query, ...)` ranks candidate feeds and returns `FeedMatch` objects;
    `to_rss_config(matches)` turns them into a ready-to-run `RSSFetchConfig`.
  - Candidates come from three sources: a curated, versioned catalog shipped as
    package data (`discovery/data/catalog.json`); `find_feeds(url)` autodiscovery
    that reads `<link rel="alternate">` tags and probes common feed paths (the
    open-web tail — callers supply sites from their own web search); and an opt-in
    external feed index.
  - Two ranking backends behind one interface: a pure-Python BM25 ranker (default,
    no extra dependencies, deterministic) and a local sentence-transformers
    embedding ranker behind the `discovery-embeddings` extra (`--backend auto`
    uses it when installed, else falls back to lexical).
  - CLI: `fetchkit discover "<query>"` (with `--top-k`, `--backend`, `--from-urls`,
    `--external`, `--min-score`, `--as-config`) and `fetchkit find-feeds <url>`,
    both emitting pure JSON on stdout. `--as-config` emits a runnable
    `FetchKitConfig` for `fetchkit run`.
  - `fetchkit schema` gains a `discovery` section so agents learn the capability,
    its candidate sources, ranker backends, and catalog version.
  - Top-level lazy exports: `from fetchkit import discover, find_feeds, to_rss_config, FeedMatch`.
- `scripts/build_discovery_index.py` — offline maintainer tool to validate the
  catalog and (with `--embed`) build the embedding artifact.

The core stays at its four runtime dependencies; all discovery extras are optional.

## [0.1.1] - 2026-06-27

Packaging and tooling release; no library code changes.

### Added
- README badges (PyPI version, supported Python versions, license, CI).
- GitHub Actions CI running the test suite, mypy, and ruff across Python 3.10–3.13.
- GitHub Actions release workflow that publishes to PyPI via Trusted Publishing (OIDC).

## [0.1.0] - 2026-06-27

Initial public release of fetchkit — a standalone, independent library.

### Added
- Builtin fetchers, all zero-auth: `hackernews` (Algolia API), `rss` (RSS/Atom via
  feedparser), `arxiv` (export.arxiv.org Atom API), `github` (public REST API —
  releases and repository search), and `lobsters` (lobste.rs JSON).
- Canonical `Post` and `Comment` Pydantic v2 models with UTC datetime normalization,
  plus an open `Post.metadata` dict for source-specific detail (arXiv
  authors/categories/DOI/PDF, GitHub language/stars/topics, Lobsters tags) that keeps
  the core model stable.
- `FetchKitConfig` top-level config with strict validation (`extra="forbid"`,
  polymorphic typed fetcher parsing). Time window is set with **either** a relative
  `window` (e.g. `"last 6 hours"`, `"yesterday"`, `"7d"`) **or** explicit
  `start_time`/`end_time`.
- `fetchkit.resolve_window()` / `fetchkit.parse_duration()` helpers for relative
  time parsing.
- `collect_all` orchestrator preserving three invariants: per-fetcher time-window
  inheritance, `(source, id)` deduplication, and descending `(created_at, id)` sort.
  Partial failures are aggregated, not fatal.
- `HttpConfig`-driven shared HTTP client (`HttpClient`): session pooling, retries
  with exponential backoff, `Retry-After` handling, and optional per-host rate
  limiting (`RateLimiter`). The run-specific client is installed **thread-locally**
  (`use_client`), so concurrent `collect_all()` calls on different threads are fully
  isolated and never clobber each other or a caller's `set_default_client()`.
- `fetchkit` command-line interface (`fetchkit run` / `fetchkit validate`, also
  available as `python -m fetchkit`). `run` emits a JSON `{count, posts, errors}`
  document on stdout — diagnostics go to stderr — so agents and shell scripts can
  consume results without writing Python. Supports `-o/--output`, `--window`,
  `--compact`, `--indent`, and `--fail-on-error`.
- `load_config` YAML loader with `ConfigError` wrapping.
- Full test suite including HTTP retry/rate-limit coverage and a live RSS smoke test
  gated by the `live` pytest marker; strict mypy configuration (pydantic plugin,
  Python 3.10 target); MIT license.

### Security
- RSS feeds are restricted to HTTP(S) URLs by default. Local file paths and `file://`
  URLs are refused unless `RSSFetchConfig.allow_local_files` is set, hardening
  fetchkit against untrusted/agent-authored configs that could read arbitrary local
  files.
