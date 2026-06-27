"""Load and validate YAML fetcher configuration into typed fetchkit models."""

import yaml
from pathlib import Path
from pydantic import ValidationError
from fetchkit.schemas.config import FetchKitConfig


class ConfigError(Exception):
    """Base exception for configuration loading errors."""
    pass


def load_config(path: str) -> FetchKitConfig:
    """
    Load a FetchKitConfig from a YAML file.

    The YAML schema is fetchers-only::

        start_time: "2026-01-31T00:00:00Z"
        end_time:   "2026-02-01T00:00:00Z"
        fetchers:
          - type: hackernews
            posts: { max_items: 50, order: new }
          - type: rss
            feeds:
              - url: "https://example.com/rss"
        http:  # optional
          timeout: 15
          max_retries: 5

    Raises:
        ConfigError: If the file is missing, malformed YAML, or fails validation.
    """
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"Error parsing YAML in {path}: {e}")
    except Exception as e:
        raise ConfigError(f"Error reading config file {path}: {e}")

    if raw_config is None:
        raw_config = {}

    try:
        return FetchKitConfig.model_validate(raw_config)
    except ValidationError as e:
        # Format Pydantic errors for better CLI readability
        error_messages = []
        for error in e.errors():
            loc = ".".join(str(part) for part in error["loc"])
            msg = error["msg"]
            error_messages.append(f"  - {loc}: {msg}")
        detail = "\n".join(error_messages)
        raise ConfigError(f"Config validation failed for {path}:\n{detail}") from e
