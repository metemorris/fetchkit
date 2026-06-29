# Changelog

All notable changes to fetchkit are documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/) and uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-06-29

### Added
- **Three new zero-auth fetchers**, all returning the canonical `Post` model:
  - `stackexchange` — questions (and, with `comments.fetch`, top answers as
    `Comment`s) from the Stack Exchange API; anonymous access within the
    300 requests/day/IP quota. Tags, answer count, and accepted-answer id are kept
    in `post.metadata`.
  - `bluesky` — posts from the public Bluesky AppView (`public.api.bsky.app`),
    via full-text `search` or a single account's `author_feed`. Likes map to
    `score`, replies to `comment_count`; `uri`/`cid`/`langs` go in `metadata`.
  - `mastodon` — public and hashtag timelines on any instance (no auth when public
    preview is enabled). HTML content is reduced to plain text; tags, instance, and
    visibility are kept in `post.metadata`.
- **Per-source discovery (`suggest`)** — a cross-source analog of RSS `discover`
  that answers "which tag / site / instance / feed / category do I put in the
  config?" Each fetcher registers a no-auth suggester returning JSON-ready rows:
  - CLI: `fetchkit suggest <source>` (with `--query`, `--site`, `--instance`,
    `--what`, `--limit`), emitting pure JSON on stdout.
  - Python: `run_suggester(source, **params)`, plus `register_suggester` /
    `get_suggester` / `list_suggesters` for custom sources, exported from
    `fetchkit`.
  - Coverage: Lobsters/Stack Exchange tags, Stack Exchange sites, arXiv categories,
    GitHub popular repos, Mastodon trending hashtags, Bluesky feeds/actors,
    HackerNews sort orders, and RSS (delegating to `discover`).
- `fetchkit schema` gains a `suggest` section so an agent introspecting the tool
  learns the per-source discovery capability, its parameters, and which config
  field each source's suggestions fill.
- Scheduled `live` CI workflow (`.github/workflows/live.yml`) that exercises the
  real no-auth source and discovery endpoints weekly and on demand, skipping
  gracefully when an upstream is unavailable.

### Changed
- Hardened Bluesky pagination against a spin when the AppView echoes a
  non-advancing cursor while window-filtering drops every item.

## [0.2.0] - 2026-06-29

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
- `scripts/validate_catalog.py` — offline maintainer tool to validate the catalog.
- Self-describing `fetchkit schema` command that emits a machine-readable JSON
  description of fetchkit's capabilities (fetchers, config shape, discovery) so
  agents can introspect the tool without reading the docs.

The core stays at its four runtime dependencies; all discovery extras are optional.

### Changed
- Trimmed the canonical model: moved HackerNews-specific converters out of the
  core model and dropped dead code. `Post.score` is documented as
  source-relative, not comparable across sources.

### Fixed
- `RateLimiter` no longer sleeps while holding its lock, so a slow/rate-limited
  host can no longer stall unrelated requests waiting on the limiter.

### Security
- RSS feed URLs are guarded against SSRF to internal/private addresses, hardening
  fetchkit against untrusted or agent-authored configs that could probe the local
  network.

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
