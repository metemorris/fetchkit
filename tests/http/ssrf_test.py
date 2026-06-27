import socket
from unittest.mock import patch

import pytest

from fetchkit.http.ssrf import BlockedURLError, guard_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/feed",
        "http://localhost/feed",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.1/feed",
        "http://192.168.1.1/feed",
        "http://172.16.0.1/feed",
        "http://[::1]/feed",
        "http://0.0.0.0/feed",
    ],
)
def test_literal_private_addresses_blocked(url: str) -> None:
    with pytest.raises(BlockedURLError):
        guard_public_url(url)


@pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd", "gopher://x/"])
def test_non_http_schemes_blocked(url: str) -> None:
    with pytest.raises(BlockedURLError):
        guard_public_url(url)


def test_literal_public_ip_allowed() -> None:
    guard_public_url("https://8.8.8.8/feed")  # does not raise


def test_ipv4_mapped_ipv6_loopback_blocked() -> None:
    # ::ffff:127.0.0.1 must be unwrapped to its IPv4 form and rejected.
    with pytest.raises(BlockedURLError):
        guard_public_url("http://[::ffff:127.0.0.1]/feed")


def test_url_without_host_blocked() -> None:
    with pytest.raises(BlockedURLError):
        guard_public_url("http:///feed")


def test_public_hostname_allowed_via_resolution() -> None:
    with patch(
        "fetchkit.http.ssrf.socket.getaddrinfo",
        return_value=[(socket.AF_INET, None, None, "", ("93.184.216.34", 443))],
    ):
        guard_public_url("https://example.com/feed")  # does not raise


def test_hostname_resolving_to_private_blocked() -> None:
    with patch(
        "fetchkit.http.ssrf.socket.getaddrinfo",
        return_value=[(socket.AF_INET, None, None, "", ("127.0.0.1", 80))],
    ):
        with pytest.raises(BlockedURLError):
            guard_public_url("http://sneaky.example.com/feed")


def test_unresolvable_host_blocked() -> None:
    with patch(
        "fetchkit.http.ssrf.socket.getaddrinfo",
        side_effect=socket.gaierror("name resolution failed"),
    ):
        with pytest.raises(BlockedURLError):
            guard_public_url("http://does-not-exist.invalid/feed")
