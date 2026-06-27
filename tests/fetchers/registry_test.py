from typing import Any
from unittest.mock import patch

import pytest

from fetchkit.fetchers.base import FetcherResult
from fetchkit.fetchers.registry import get_fetcher, register_fetcher
import fetchkit.fetchers.registry as registry


def test_builtin_fetchers_registered() -> None:
    for name in ("hackernews", "rss", "arxiv", "github", "lobsters"):
        assert callable(get_fetcher(name))


def test_register_fetcher_decorator_registers_handler() -> None:
    with patch.dict(registry.REGISTRY, {}, clear=True):
        @register_fetcher("custom.test")
        def _handler(config: Any) -> FetcherResult:
            return FetcherResult(posts=[], errors=[])

        assert get_fetcher("custom.test") is _handler


def test_get_fetcher_raises_for_unknown_type() -> None:
    with patch.dict(registry.REGISTRY, {}, clear=True):
        with pytest.raises(ValueError, match="Unknown fetcher type: does-not-exist"):
            get_fetcher("does-not-exist")
