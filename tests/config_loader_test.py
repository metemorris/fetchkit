import pytest
import os
from fetchkit.config_loader import load_config, ConfigError
from fetchkit.schemas.config import FetchKitConfig


def get_config_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "testdata", "configs", filename)


def test_load_minimal_config() -> None:
    path = get_config_path("valid_minimal.yaml")
    cfg = load_config(path)
    assert isinstance(cfg, FetchKitConfig)

    hn_fetchers = [f for f in cfg.fetchers if f.type == "hackernews"]
    assert len(hn_fetchers) == 1
    hn_config = hn_fetchers[0]
    assert hasattr(hn_config, "posts")
    assert hn_config.posts.max_items == 5


def test_load_config_missing_file() -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config("/non/existent/path.yaml")


def test_load_config_invalid_yaml() -> None:
    path = get_config_path("invalid_yaml.yaml")
    with pytest.raises(ConfigError, match="Error parsing YAML"):
        load_config(path)


def test_load_config_unknown_field() -> None:
    path = get_config_path("invalid_unknown_field.yaml")
    with pytest.raises(ConfigError, match="Config validation failed"):
        load_config(path)


def test_load_config_rejects_processors_key() -> None:
    """A fetchers-only config rejects processor/notifier keys."""
    import tempfile

    content = """
start_time: "2026-01-01T00:00:00Z"
end_time: "2026-01-02T00:00:00Z"
processors:
  - type: "filter.engagement"
    name: "x"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(content)
        path = f.name
    try:
        with pytest.raises(ConfigError, match="Config validation failed"):
            load_config(path)
    finally:
        os.unlink(path)
