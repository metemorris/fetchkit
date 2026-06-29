"""Command-line interface for fetchkit.

Designed so an agent (or a shell script) can fetch news deterministically from a
YAML spec and parse structured JSON from stdout::

    fetchkit run config.yaml                 # JSON: {"posts": [...], "errors": [...]}
    fetchkit run config.yaml -o out.json     # write JSON to a file instead of stdout
    fetchkit run config.yaml --fail-on-error # exit 1 if any source failed
    fetchkit validate config.yaml            # check a config without fetching
    fetchkit schema                          # JSON Schema for every config/output model
    fetchkit discover "AI safety news"       # find RSS feeds for a use case
    fetchkit find-feeds https://example.com  # autodiscover feeds from a site

stdout carries only JSON (for ``run``, ``schema``, ``discover``, and
``find-feeds``) so it is safe to pipe into ``jq`` or parse programmatically.
Diagnostics and ``--verbose`` logging go to stderr. ``schema`` lets an agent
discover the available fetchers and their options without being told the YAML
format out of band; ``discover`` closes the same gap for RSS by mapping a
natural-language query onto real feeds (use ``--as-config`` to pipe the result
straight into ``run``).

Exit codes::

    0  success
    1  fetch completed but a source failed (only with --fail-on-error)
    2  configuration error (missing file, invalid YAML, validation failure)
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from fetchkit import __version__
from fetchkit.collector import collect_all
from fetchkit.config_loader import ConfigError, load_config
from fetchkit.schemas.describe import build_schema_document
from fetchkit.utils.time import resolve_window


def _emit_json(payload: Any, indent: Optional[int], output: Optional[str]) -> None:
    """Write a JSON document to ``output`` (a file path) or stdout.

    When writing to a file, stdout stays empty so the file is the sole result
    artifact; a one-line confirmation is logged to stderr.
    """
    text = json.dumps(payload, indent=indent, ensure_ascii=False)
    if output is None:
        sys.stdout.write(text + "\n")
        return
    Path(output).expanduser().write_text(text + "\n", encoding="utf-8")
    # Confirmation goes to stderr so stdout stays empty when writing to a file.
    # Include the post count when the payload carries one (the `run` result).
    if "count" in payload:
        print(f"Wrote {payload['count']} post(s) to {output}", file=sys.stderr)
    else:
        print(f"Wrote JSON to {output}", file=sys.stderr)


def _cmd_run(args: argparse.Namespace) -> int:
    """Load a config, collect posts, and emit a JSON result document on stdout."""
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # The window can be set two ways: in the YAML config itself (a `window:` key,
    # mutually exclusive with start_time/end_time), or here on the command line.
    # --window is a runtime override: it replaces whatever bounds the config
    # resolved to, so you can reuse one config across different time ranges.
    if args.window:
        try:
            config.start_time, config.end_time = resolve_window(args.window)
        except ValueError as exc:
            print(f"Invalid --window: {exc}", file=sys.stderr)
            return 2

    # Keep stdout pure JSON: progress/verbosity is logged to stderr, never printed.
    result = collect_all(config)

    payload = {
        "count": len(result.posts),
        "posts": [post.model_dump(mode="json") for post in result.posts],
        "errors": [
            {"source": source, "error": str(err)} for source, err in result.errors
        ],
    }
    indent = None if args.compact else args.indent
    _emit_json(payload, indent, args.output)

    if args.fail_on_error and result.has_errors:
        return 1
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    """Load and validate a config without fetching; report the result."""
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    enabled = sum(1 for f in config.fetchers if f.enabled)
    print(
        f"OK: {args.config} is valid "
        f"({len(config.fetchers)} fetcher(s), {enabled} enabled).",
        file=sys.stderr,
    )
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    """Emit JSON Schema for every config and output model on stdout."""
    payload = build_schema_document()
    indent = None if args.compact else args.indent
    _emit_json(payload, indent, args.output)
    return 0


def _cmd_discover(args: argparse.Namespace) -> int:
    """Find RSS feeds for a query and emit JSON (or a ready-to-run RSS config)."""
    # Imported lazily so the rest of the CLI is unaffected by discovery internals.
    from fetchkit.discovery import discover, to_rss_config
    from fetchkit.discovery.catalog import load_catalog
    from fetchkit.discovery.errors import DiscoveryError

    from_urls: Optional[list[str]] = None
    if args.from_urls:
        from_urls = [u.strip() for u in args.from_urls.split(",") if u.strip()]

    try:
        matches = discover(
            args.query,
            top_k=args.top_k,
            backend=args.backend,
            from_urls=from_urls,
            use_external=args.external,
            min_score=args.min_score,
        )
    except DiscoveryError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    indent = None if args.compact else args.indent
    if args.as_config:
        # Emit a full FetchKitConfig (a single rss fetcher) that pipes straight
        # into `run`. Left as just `fetchers` so the time window stays relative
        # (run resolves the default 24h window at execution time).
        payload: Any = {"fetchers": [to_rss_config(matches).model_dump(mode="json")]}
    else:
        payload = {
            "query": args.query,
            "backend": args.backend,
            "catalog_version": load_catalog().catalog_version,
            "count": len(matches),
            "matches": [m.model_dump(mode="json") for m in matches],
        }
    _emit_json(payload, indent, args.output)
    return 0


def _cmd_find_feeds(args: argparse.Namespace) -> int:
    """Autodiscover RSS/Atom feeds from one or more site URLs; emit JSON."""
    from fetchkit.discovery import find_feeds

    feeds: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in args.urls:
        try:
            for candidate in find_feeds(url, max_feeds=args.max_feeds):
                if candidate.url in seen:
                    continue
                seen.add(candidate.url)
                feeds.append(candidate.model_dump(mode="json"))
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)})

    indent = None if args.compact else args.indent
    payload = {"count": len(feeds), "feeds": feeds, "errors": errors}
    _emit_json(payload, indent, args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser with ``run`` and ``validate``."""
    parser = argparse.ArgumentParser(
        prog="fetchkit",
        description="Fetch news/posts deterministically from a YAML spec.",
    )
    parser.add_argument(
        "--version", action="version", version=f"fetchkit {__version__}"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable INFO-level logging to stderr.",
    )

    # Define the two subcommands (`fetchkit run ...` / `fetchkit validate ...`).
    # `dest="command"` records which one was chosen; `required=True` makes picking
    # a subcommand mandatory (running bare `fetchkit` errors with usage help).
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Fetch posts and print JSON to stdout.")
    run.add_argument("config", help="Path to the YAML config file.")
    run.add_argument(
        "-o", "--output", default=None, metavar="PATH",
        help="Write JSON to this file instead of stdout.",
    )
    run.add_argument(
        "--window", default=None, metavar="SPEC",
        help="Override the config time window, e.g. 'last 6 hours', 'yesterday', '7d'.",
    )
    run.add_argument(
        "--indent", type=int, default=2,
        help="JSON indentation for pretty output (default: 2).",
    )
    run.add_argument(
        "--compact", action="store_true",
        help="Emit single-line JSON (overrides --indent).",
    )
    run.add_argument(
        "--fail-on-error", action="store_true",
        help="Exit 1 if any source reported an error.",
    )
    run.set_defaults(func=_cmd_run)

    validate = sub.add_parser("validate", help="Validate a config without fetching.")
    validate.add_argument("config", help="Path to the YAML config file.")
    validate.set_defaults(func=_cmd_validate)

    schema = sub.add_parser(
        "schema", help="Print JSON Schema for configs and output to stdout."
    )
    schema.add_argument(
        "-o", "--output", default=None, metavar="PATH",
        help="Write JSON to this file instead of stdout.",
    )
    schema.add_argument(
        "--indent", type=int, default=2,
        help="JSON indentation for pretty output (default: 2).",
    )
    schema.add_argument(
        "--compact", action="store_true",
        help="Emit single-line JSON (overrides --indent).",
    )
    schema.set_defaults(func=_cmd_schema)

    discover = sub.add_parser(
        "discover",
        help="Find RSS feeds for a natural-language query (JSON to stdout).",
    )
    discover.add_argument(
        "query", help="Natural-language use case, e.g. 'AI safety research news'.",
    )
    discover.add_argument(
        "--top-k", type=int, default=5, help="Max matches to return (default: 5).",
    )
    discover.add_argument(
        "--backend", choices=["auto", "lexical", "embedding"], default="auto",
        help="Ranker backend (default: auto; 'embedding' needs the discovery-embeddings extra).",
    )
    discover.add_argument(
        "--from-urls", default=None, metavar="URLS",
        help="Comma-separated sites to also autodiscover feeds from (e.g. from your web search).",
    )
    discover.add_argument(
        "--external", action="store_true",
        help="Also query the external feed index (network; opt-in).",
    )
    discover.add_argument(
        "--min-score", type=float, default=None,
        help="Drop matches scoring below this threshold.",
    )
    discover.add_argument(
        "--as-config", action="store_true",
        help="Emit a ready-to-run RSSFetchConfig instead of the match list.",
    )
    discover.add_argument(
        "-o", "--output", default=None, metavar="PATH",
        help="Write JSON to this file instead of stdout.",
    )
    discover.add_argument(
        "--indent", type=int, default=2,
        help="JSON indentation for pretty output (default: 2).",
    )
    discover.add_argument(
        "--compact", action="store_true",
        help="Emit single-line JSON (overrides --indent).",
    )
    discover.set_defaults(func=_cmd_discover)

    find_feeds = sub.add_parser(
        "find-feeds",
        help="Autodiscover RSS/Atom feeds from one or more site URLs.",
    )
    find_feeds.add_argument("urls", nargs="+", help="Site URL(s) to discover feeds from.")
    find_feeds.add_argument(
        "--max-feeds", type=int, default=10, help="Max feeds per site (default: 10).",
    )
    find_feeds.add_argument(
        "-o", "--output", default=None, metavar="PATH",
        help="Write JSON to this file instead of stdout.",
    )
    find_feeds.add_argument(
        "--indent", type=int, default=2,
        help="JSON indentation for pretty output (default: 2).",
    )
    find_feeds.add_argument(
        "--compact", action="store_true",
        help="Emit single-line JSON (overrides --indent).",
    )
    find_feeds.set_defaults(func=_cmd_find_feeds)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            stream=sys.stderr,
            format="%(levelname)s %(name)s: %(message)s",
        )

    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
