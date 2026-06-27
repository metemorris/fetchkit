"""SSRF guard: reject URLs whose host resolves to a non-public address.

fetchkit may run untrusted configs (e.g. agent-produced), and the RSS fetcher
accepts arbitrary feed URLs. Without a guard an attacker could point a feed at
internal services — cloud metadata (``169.254.169.254``), ``localhost``, or
RFC-1918 hosts — and exfiltrate the response. :func:`guard_public_url` resolves a
URL's host and rejects it if any resolved address is loopback, private,
link-local, reserved, multicast, or unspecified.

This is a *reasonable* guard, not a perfect one. It does **not** defend against
DNS rebinding (a host that resolves to a public IP at check time and a private IP
at connect time) or HTTP redirects to a private host. Callers needing stronger
guarantees should also disable redirects and/or pin the resolved IP for the
actual connection.
"""

import ipaddress
import socket
from typing import Union
from urllib.parse import urlparse

_IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


class BlockedURLError(ValueError):
    """Raised when a URL is rejected by the SSRF guard."""


def _is_blocked(ip: _IPAddress) -> bool:
    """True if ``ip`` is not a routable public address."""
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _normalize(ip: _IPAddress) -> _IPAddress:
    """Unwrap IPv4-mapped IPv6 addresses so their real range is checked."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def guard_public_url(url: str) -> None:
    """Raise :class:`BlockedURLError` if ``url``'s host is not publicly routable.

    Only ``http``/``https`` URLs are permitted; every address the host resolves to
    must be public. A literal IP host is checked directly; a name is resolved via
    DNS and *all* returned addresses must pass.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedURLError(
            f"Refusing to fetch '{url}': only http(s) URLs are allowed"
        )
    host = parsed.hostname
    if not host:
        raise BlockedURLError(f"Refusing to fetch '{url}': URL has no host")

    try:
        addresses: list[_IPAddress] = [ipaddress.ip_address(host)]
    except ValueError:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise BlockedURLError(
                f"Refusing to fetch '{url}': cannot resolve host '{host}' ({exc})"
            ) from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]

    for addr in addresses:
        normalized = _normalize(addr)
        if _is_blocked(normalized):
            raise BlockedURLError(
                f"Refusing to fetch '{url}': host '{host}' resolves to "
                f"non-public address {normalized}"
            )
