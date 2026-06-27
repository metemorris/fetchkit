# Changelog

All notable changes to fetchkit are documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/) and uses
[Semantic Versioning](https://semver.org/).

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
