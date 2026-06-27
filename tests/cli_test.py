import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from fetchkit.cli import main
from fetchkit.fetchers.base import FetcherResult
from fetchkit.schemas.post import Post, Source

RSS_FIXTURE = Path(__file__).parent / "testdata" / "sample_rss.xml"


def _write_config(tmp_path: Path, body: str) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return str(path)


def _hn_config(tmp_path: Path) -> str:
    return _write_config(
        tmp_path,
        """
start_time: "2026-01-01T00:00:00Z"
end_time: "2026-01-02T00:00:00Z"
fetchers:
  - type: hackernews
    posts: { max_items: 1 }
""",
    )


def test_run_emits_clean_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _hn_config(tmp_path)
    post = Post(
        id="1", source=Source.HACKERNEWS, title="Hello",
        created_at=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
        source_url="https://news.ycombinator.com/item?id=1",
    )
    with patch("fetchkit.collector.get_fetcher") as mock_get:
        mock_get.return_value = lambda cfg: FetcherResult(posts=[post], errors=[])
        code = main(["run", config])

    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)  # stdout must be valid JSON
    assert payload["count"] == 1
    assert payload["posts"][0]["title"] == "Hello"
    assert payload["posts"][0]["source"] == "hackernews"
    assert payload["errors"] == []


def test_run_fail_on_error_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _hn_config(tmp_path)
    with patch("fetchkit.collector.get_fetcher") as mock_get:
        mock_get.return_value = lambda cfg: FetcherResult(
            posts=[], errors=[RuntimeError("boom")]
        )
        code = main(["run", config, "--fail-on-error"])

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"][0]["source"] == "hackernews"
    assert "boom" in payload["errors"][0]["error"]


def test_run_errors_without_fail_flag_exit_zero(tmp_path: Path) -> None:
    config = _hn_config(tmp_path)
    with patch("fetchkit.collector.get_fetcher") as mock_get:
        mock_get.return_value = lambda cfg: FetcherResult(
            posts=[], errors=[RuntimeError("boom")]
        )
        code = main(["run", config])
    assert code == 0


def test_run_compact_is_single_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _hn_config(tmp_path)
    with patch("fetchkit.collector.get_fetcher") as mock_get:
        mock_get.return_value = lambda cfg: FetcherResult(posts=[], errors=[])
        main(["run", config, "--compact"])
    out = capsys.readouterr().out.strip()
    assert "\n" not in out
    assert json.loads(out)["count"] == 0


def test_run_output_to_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _hn_config(tmp_path)
    out_file = tmp_path / "result.json"
    post = Post(
        id="1", source=Source.HACKERNEWS, title="Saved",
        source_url="https://news.ycombinator.com/item?id=1",
    )
    with patch("fetchkit.collector.get_fetcher") as mock_get:
        mock_get.return_value = lambda cfg: FetcherResult(posts=[post], errors=[])
        code = main(["run", config, "-o", str(out_file)])

    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == ""  # nothing on stdout when writing to a file
    assert "Wrote 1 post(s)" in captured.err
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["posts"][0]["title"] == "Saved"


def test_run_window_override(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--window overrides the config's time bounds and is passed to fetchers."""
    config = _hn_config(tmp_path)
    captured_window = {}

    def fake_fetcher(cfg: object) -> FetcherResult:
        captured_window["start"] = cfg.start_time  # type: ignore[attr-defined]
        captured_window["end"] = cfg.end_time  # type: ignore[attr-defined]
        return FetcherResult(posts=[], errors=[])

    with patch("fetchkit.collector.get_fetcher", return_value=fake_fetcher):
        code = main(["run", config, "--window", "last 2 hours"])

    assert code == 0
    delta = captured_window["end"] - captured_window["start"]
    assert abs(delta.total_seconds() - 2 * 3600) < 5


def test_run_invalid_window_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _hn_config(tmp_path)
    code = main(["run", config, "--window", "whenever"])
    assert code == 2
    assert "Invalid --window" in capsys.readouterr().err


def test_run_missing_config_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["run", str(tmp_path / "nope.yaml")])
    assert code == 2
    err = capsys.readouterr().err
    assert "not found" in err


def test_validate_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _hn_config(tmp_path)
    code = main(["validate", config])
    assert code == 0
    assert capsys.readouterr().out == ""  # validate writes to stderr only


def test_validate_invalid_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _write_config(
        tmp_path,
        """
start_time: "2026-01-02T00:00:00Z"
end_time: "2026-01-01T00:00:00Z"
""",
    )
    code = main(["validate", config])
    assert code == 2
    assert "validation failed" in capsys.readouterr().err
