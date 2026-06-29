# fetchkit

[![CI](https://github.com/metemorris/fetchkit/actions/workflows/ci.yml/badge.svg)](https://github.com/metemorris/fetchkit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/fetchkit-agents.svg)](https://pypi.org/project/fetchkit-agents/)
[![Python versions](https://img.shields.io/pypi/pyversions/fetchkit-agents.svg)](https://pypi.org/project/fetchkit-agents/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A YAML-configured data-fetching library for agentic applications.

`fetchkit` collects posts and comments from sources (Hacker News, RSS/Atom, arXiv,
GitHub, Lobsters) into a single canonical `Post` model, with de-duplication,
deterministic sorting, and a shared HTTP client with retries and rate limiting. It is
designed as the data-collection layer for LLM/agent pipelines — feed it configs, get
back clean typed data.

- **YAML-first** configuration with strict validation: unknown or misspelled keys
  are rejected up front, so a bad config fails loudly instead of silently.
- **Builtin fetchers**: Hacker News, RSS/Atom, arXiv, GitHub, and Lobsters — all
  zero-auth.
- **Relative time windows**: say `window: "last 6 hours"` instead of computing
  timestamps.
- **Open `metadata`**: each `Post` carries a `metadata` dict for source-specific
  detail (arXiv categories/DOI, GitHub language/stars, tags) without bloating the
  core model.
- **Robust HTTP**: shared session pooling, exponential backoff + retries, `Retry-After`
  handling, and optional per-host rate limiting.
- **Typed end-to-end**: Pydantic v2 models throughout.
- **Deterministic output**: dedup by `(source, id)`, sorted descending by
  `(created_at, id)`.
- **Agent-friendly CLI**: `fetchkit run config.yaml` emits clean JSON on stdout —
  no Python required.
- **RSS feed discovery**: `fetchkit discover "<use case>"` maps a natural-language
  query onto real RSS feeds an agent can fetch — closing the "which feed URL?" gap.

## Install

```bash
pip install fetchkit-agents     # PyPI distribution name

# or install the latest from source:
pip install "git+https://github.com/metemorris/fetchkit.git"
```

The PyPI package is `fetchkit-agents` (the `fetchkit` name was taken), but you still
`import fetchkit` and the CLI command is `fetchkit`. Requires Python ≥ 3.10.

## Quick start

### 1. YAML config

`config.yaml`:

```yaml
window: "last 24 hours"   # or set explicit start_time / end_time
fetchers:
  - type: hackernews
    posts:
      max_items: 50
      order: new
  - type: arxiv
    categories: ["cs.AI", "cs.LG"]
    max_items: 40
  - type: github
    resource: releases
    repos: ["python/cpython", "pydantic/pydantic"]
  - type: lobsters
    listing: hottest
  - type: rss
    feeds:
      - url: "https://feeds.bbci.co.uk/news/rss.xml"
        name: "BBC News"
    max_items_per_feed: 40
    max_total_items: 200
http:           # optional
  timeout: 15
  max_retries: 5
  rate_limit_per_host: 2.0
```

### 2. Run

```python
from fetchkit import load_config, collect_all

config = load_config("config.yaml")
result = collect_all(config)

print(f"Collected {len(result.posts)} posts")
for post in result.posts:
    print(post.created_at, post.source, post.title, post.url)

if result.has_errors:
    for source, err in result.errors:
        print(f"  {source}: {err}")
```

### 3. Command line (for agents & scripts)

`fetchkit` installs a CLI so an agent can shell out and parse JSON without writing
Python. `run` prints **only** JSON to stdout (diagnostics go to stderr), so it pipes
cleanly into `jq`:

```bash
fetchkit run config.yaml                    # pretty JSON: {"count", "posts", "errors"}
fetchkit run config.yaml -o out.json        # write JSON to a file (stdout stays empty)
fetchkit run config.yaml --window "6h"      # override the time window at runtime
fetchkit run config.yaml --compact          # single-line JSON
fetchkit run config.yaml --fail-on-error    # exit 1 if any source failed
fetchkit validate config.yaml               # validate a config without fetching
fetchkit schema                             # JSON Schema for every config/output model
python -m fetchkit run config.yaml          # module form, identical behavior
```

`fetchkit schema` lets an agent discover what it can fetch — it prints the JSON
Schema (with field descriptions) for the top-level config, the shared HTTP
settings, every builtin fetcher's typed config, and the canonical `Post` output —
so a config can be written without knowing the YAML format out of band:

```bash
fetchkit schema | jq '.fetchers | keys'     # ["arxiv","github","hackernews","lobsters","rss"]
fetchkit schema -o schema.json              # write to a file; supports --compact too
```

Output shape:

```json
{
  "count": 2,
  "posts": [ { "id": "...", "source": "rss", "title": "...", "url": "...", "created_at": "..." } ],
  "errors": [ { "source": "hackernews", "error": "..." } ]
}
```

Exit codes: `0` success · `1` a source failed (only with `--fail-on-error`) ·
`2` configuration error.

### 4. Programmatic (no YAML)

```python
from datetime import datetime, timezone, timedelta
from fetchkit import FetchKitConfig, HackerNewsFetchConfig, PostFetchConfig, SortOrder, collect_all

config = FetchKitConfig(
    start_time=datetime.now(timezone.utc) - timedelta(days=1),
    end_time=datetime.now(timezone.utc),
    fetchers=[
        HackerNewsFetchConfig(posts=PostFetchConfig(max_items=30, order=SortOrder.NEW)),
    ],
)
result = collect_all(config)
```

## Discovering RSS feeds

Every other source has a finite, nameable set of options (`fetchkit schema`
enumerates them). RSS is the exception: a feed is an *arbitrary URL*, so an agent
that wants "central-bank policy" or "rust programming" has no way to know which
feeds exist. The optional `discovery` module closes that gap — give it a
use case, get back ranked feeds you can drop straight into an `rss` fetcher.

```python
from fetchkit.discovery import discover, to_rss_config

matches = discover("news and topics regarding AI safety research", top_k=5)
for m in matches:
    print(m.score, m.name, m.url)

config = to_rss_config(matches)   # an RSSFetchConfig, ready for collect_all
```

```bash
fetchkit discover "AI safety research news" --top-k 5            # ranked feeds as JSON
fetchkit discover "central bank policy" --as-config -o rss.json  # emit a runnable config…
fetchkit run rss.json                                            # …then fetch (discover → config → run)
fetchkit find-feeds https://example.com                          # autodiscover a site's feeds
```

### How it works (and what it can't do)

Feeds are **matched, not searched**. You can't embed feeds you've never seen, so
embeddings only ever *rank* a set of candidates you already hold. Discovery
assembles that candidate set from three sources, then ranks it against your query:

1. **Curated catalog** — a shipped, versioned directory of ~50 high-quality,
   long-lived feeds across news, research, programming, finance, and more. The
   offline, deterministic floor.
2. **Autodiscovery** (`find_feeds(url)` / `--from-urls`) — given a site, it reads
   the `<link rel="alternate">` RSS-autodiscovery tags, probes common feed paths,
   and validates each candidate. This reaches the open-web long tail. The
   *topic → which sites* step is left to **your** web search: an agent already has
   one, so it finds the sites and hands them to fetchkit, which extracts the feeds.
   fetchkit never bundles a search engine.
3. **External index** (`--external`, opt-in) — queries a third-party feed-search
   service for recall over millions of feeds. Off by default (network + ToS).

Ranking has two backends behind one interface:

- **lexical** (default) — pure-Python BM25 over each feed's metadata. Zero extra
  dependencies, fully deterministic, works offline and in CI.
- **embedding** — a local sentence-transformers model for stronger semantic
  matching. Opt in with the extra:

  ```bash
  pip install "fetchkit-agents[discovery-embeddings]"
  fetchkit discover "papers on diffusion models" --backend embedding
  ```

  `--backend auto` (the default) uses the embedding ranker when the extra is
  installed and falls back to lexical otherwise.

Discovery matches a feed's **description/metadata** (what the feed is *about*),
not the live article stream — for the latter, fetch the feed with the `rss`
fetcher and match individual posts. Catalog quality is the main lever on result
quality; see `src/fetchkit/discovery/data/CATALOG.md` to extend it.

## Configuration reference

### Top-level (`FetchKitConfig`)

| Field         | Type                | Required | Description                                |
|---------------|---------------------|----------|--------------------------------------------|
| `window`      | str                 | no       | Relative window (resolves to start/end).   |
| `start_time`  | datetime            | no       | Global window start (inclusive).           |
| `end_time`    | datetime            | no       | Global window end (inclusive).             |
| `fetchers`    | list[FetcherConfig] | no       | Fetcher instances to run.                  |
| `http`        | HttpConfig          | no       | Shared HTTP client settings.               |

Set the time window with **either** a relative `window` **or** both
`start_time`/`end_time` — the two are mutually exclusive. **If you specify none of
them, the window defaults to the last 24 hours.** `start_time <= end_time` is
enforced, and unknown top-level keys are rejected. Per-fetcher
`start_time`/`end_time` default to `None` and **inherit** the global window at runtime.

#### Relative windows

`window` accepts (case-insensitive): `"last 6 hours"`, `"past 30 minutes"`,
`"last 7 days"`, `"last week"`, `"last month"`, `"today"`, `"yesterday"`, or a bare
duration like `"6h"`, `"2d"`, `"90m"`. It resolves **once** to a concrete
`(start_time, end_time)` pair (end = now), so collection stays deterministic for that
resolved pair. The same parsing is available programmatically via
`fetchkit.resolve_window(spec)` and `fetchkit.parse_duration(text)`.

### Hacker News (`type: hackernews`)

| Field                | Default | Notes                                  |
|----------------------|---------|----------------------------------------|
| `posts.max_items`    | 10      | 1–500                                  |
| `posts.order`        | top     | top / new / controversial / asc / desc |
| `comments.fetch`     | false   | Fetch comment threads for each post    |
| `comments.max_items` | 10      | 1–100 roots per post                   |
| `comments.max_depth` | 1       | 0 = roots only                         |
| `comments.order`     | top     | Sort order for comment roots           |

### RSS / Atom (`type: rss`)

| Field                  | Default | Notes                          |
|------------------------|---------|--------------------------------|
| `feeds`                | —       | List of `{url, name?}`         |
| `max_items_per_feed`   | 50      | 1–500                          |
| `max_total_items`      | 200     | 1–2000                         |
| `include_content`      | true    | Include full entry content     |
| `allow_local_files`    | false   | Permit local-path / `file://` feeds |

`feeds[].url` is restricted to HTTP(S) URLs by default, and each URL's host must
resolve to a **public** address — feeds pointing at loopback, private (RFC-1918),
link-local, or cloud-metadata (`169.254.169.254`) hosts are refused to prevent
SSRF. Setting `allow_local_files: true` additionally permits local file paths and
`file://` URLs *and* opts out of the SSRF guard (it declares the config trusted) —
see the security note below before enabling it.

> **⚠️ Security — untrusted configs.** fetchkit is built to run YAML that may be
> produced by an LLM/agent. By default it blocks two abuse vectors in RSS feed
> URLs: local file reads (e.g. `file:///etc/passwd`) and SSRF to internal
> addresses (e.g. `http://169.254.169.254/...` or `http://127.0.0.1`). Both
> protections are **on by default**. `allow_local_files: true` turns *both* off, so
> enable it only for configs and fixtures you trust. The SSRF guard is reasonable,
> not perfect — it checks the host at request time and does not defend against DNS
> rebinding or redirects to private hosts.

### arXiv (`type: arxiv`)

Uses the arXiv export API (Atom, parsed with feedparser). Authors, categories, DOI,
PDF link, and primary category are preserved in `post.metadata`.

| Field        | Default | Notes                                            |
|--------------|---------|--------------------------------------------------|
| `categories` | `[]`    | arXiv categories, e.g. `["cs.AI", "cs.LG"]` (empty = all) |
| `query`      | null    | Free-text query (combined with categories via AND) |
| `max_items`  | 50      | 1–500                                            |

### GitHub (`type: github`)

Public GitHub REST API (no auth; tighter rate limits without a token). Repo,
language, stars, forks, and topics are preserved in `post.metadata`.

| Field      | Default  | Notes                                                        |
|------------|----------|--------------------------------------------------------------|
| `resource` | releases | `releases` (per-repo) or `search_repos`                      |
| `repos`    | `[]`     | `owner/name` list — required for `resource: releases`        |
| `query`    | null     | Search query — required for `resource: search_repos`         |
| `max_items`| 50       | 1–300                                                        |

### Lobsters (`type: lobsters`)

The lobste.rs public JSON endpoints (no auth). Tags are preserved in `post.metadata`.

| Field      | Default | Notes                                           |
|------------|---------|-------------------------------------------------|
| `listing`  | hottest | `hottest` or `newest`                           |
| `tag`      | null    | Restrict to a single tag (uses `/t/<tag>.json`) |
| `max_items`| 50      | 1–200                                           |

### HTTP (`http:`)

| Field                 | Default                  | Notes                                              |
|-----------------------|--------------------------|----------------------------------------------------|
| `timeout`             | 10.0                     | Per-request timeout in seconds                     |
| `max_retries`         | 3                        | Retries on transient errors (0–10)                 |
| `backoff_factor`      | 0.5                      | `wait = backoff_factor * 2^attempt` seconds        |
| `rate_limit_per_host` | null                     | Max requests/sec per host (null = disabled)        |
| `retry_statuses`      | 429,500,502,503,504      | Status codes that trigger a retry                  |

## Adding a fetcher

Fetchers live in the library itself, so each one ships with a typed config,
validation, and tests. Add a new source via a PR or a local fork in four steps:

1. Add a typed config to `src/fetchkit/schemas/fetcher.py` (subclass `FetcherBase`,
   give it a `Literal` `type`), and register it in `_BUILTIN_TYPES` + `FetcherConfig`.
2. Write the fetcher module in `src/fetchkit/fetchers/`, returning a `FetcherResult`:

   ```python
   from fetchkit.fetchers.base import FetcherResult
   from fetchkit.fetchers.registry import register_fetcher
   from fetchkit.schemas.post import Post

   @register_fetcher("mysource")
   def fetch(config) -> FetcherResult:
       posts = [Post(id="1", source="mysource", title="…", source_url="https://…")]
       return FetcherResult(posts=posts, errors=[])
   ```

3. Import the module in `src/fetchkit/fetchers/__init__.py` so it registers on import.
4. Add tests (mock HTTP with the `responses` library — see `tests/fetchers/`).

Use `Post.metadata` for any source-specific fields that don't map to the canonical
columns.

## The `Post` model

```python
class Post(BaseModel):
    id: str                       # unique within source
    source: str                   # "hackernews" | "rss" | "arxiv" | "github" | "lobsters"
    title: str | None
    text: str | None              # body / content
    url: str | None               # external link
    author: str | None
    score: int | None             # source-relative; NOT comparable across sources
    comment_count: int | None
    created_at: datetime | None   # UTC-aware
    source_url: str               # direct link on the source platform
    comments: list[Comment]       # nested threads (HN)
    metadata: dict[str, Any]      # source-specific extras (categories, stars, tags, …)
```

All datetimes are normalized to UTC. Posts are deduplicated by `(source, id)` and
sorted descending by `(created_at, id)` for deterministic output.

> **`score` is source-relative.** Each source defines it differently — Hacker News
> points, Lobsters score, GitHub stars (for `search_repos`), and `None` for arXiv
> and RSS. The values are **not comparable across sources**, so don't rank a mixed
> feed by `score` directly. Compare within a single `source`, or use a source-aware
> ranking of your own. Output is ordered by recency (`created_at`), not by `score`.

## Collector invariants

`collect_all` preserves three guarantees:

1. **Window inheritance** — per-fetcher `start_time`/`end_time` fall back to the
   global window when omitted.
2. **Dedup** — by `(source, id)`; first occurrence wins.
3. **Sort** — descending by `(created_at or UTC_MIN, id)`.

Partial failures are aggregated, not fatal: a failing source yields an entry in
`result.errors` while other sources still collect. Check `result.has_errors`.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# tests (skip live/networked)
pytest -m "not live"

# live network smoke (opt-in)
pytest -m live

# strict typecheck
mypy src
```

## License

MIT — see [LICENSE](LICENSE). MIT is intentional: as a small, dependency-light
utility meant to be embedded freely in agent pipelines (including commercial and
closed-source ones), a permissive license maximizes adoption with no copyleft
obligations. A weak-copyleft license (e.g. MPL-2.0) or strong copyleft (GPL/AGPL)
would force redistribution terms on downstream users and discourage exactly the
embedded use fetchkit is built for.
