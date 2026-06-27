import time
import responses
import pytest
from requests import ConnectionError as RequestsConnectionError

from fetchkit.http.client import HttpClient, get_default_client, set_default_client
from fetchkit.schemas.config import HttpConfig


@responses.activate
def test_get_success_passthrough() -> None:
    responses.add(responses.GET, "https://example.com/x", json={"ok": True}, status=200)
    client = HttpClient(HttpConfig(max_retries=0))
    resp = client.get("https://example.com/x")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    client.close()


@responses.activate
def test_retries_on_500_then_succeeds() -> None:
    responses.add(responses.GET, "https://example.com/x", status=500)
    responses.add(responses.GET, "https://example.com/x", status=500)
    responses.add(responses.GET, "https://example.com/x", json={"ok": True}, status=200)

    client = HttpClient(HttpConfig(max_retries=2, backoff_factor=0.0))
    resp = client.get("https://example.com/x")
    assert resp.status_code == 200
    assert len(responses.calls) == 3
    client.close()


@responses.activate
def test_retries_exhausted_returns_last_status() -> None:
    responses.add(responses.GET, "https://example.com/x", status=503)
    responses.add(responses.GET, "https://example.com/x", status=503)

    client = HttpClient(HttpConfig(max_retries=1, backoff_factor=0.0))
    resp = client.get("https://example.com/x")
    assert resp.status_code == 503
    assert len(responses.calls) == 2
    client.close()


@responses.activate
def test_retries_on_connection_error_then_succeeds() -> None:
    responses.add(responses.GET, "https://example.com/x", body=RequestsConnectionError("boom"))
    responses.add(responses.GET, "https://example.com/x", json={"ok": True}, status=200)

    client = HttpClient(HttpConfig(max_retries=2, backoff_factor=0.0))
    resp = client.get("https://example.com/x")
    assert resp.status_code == 200
    assert len(responses.calls) == 2
    client.close()


@responses.activate
def test_connection_error_raised_after_exhaustion() -> None:
    responses.add(responses.GET, "https://example.com/x", body=RequestsConnectionError("boom"))
    responses.add(responses.GET, "https://example.com/x", body=RequestsConnectionError("boom"))

    client = HttpClient(HttpConfig(max_retries=1, backoff_factor=0.0))
    with pytest.raises(RequestsConnectionError):
        client.get("https://example.com/x")
    assert len(responses.calls) == 2
    client.close()


@responses.activate
def test_non_retry_status_returned_immediately() -> None:
    responses.add(responses.GET, "https://example.com/x", status=404)

    client = HttpClient(HttpConfig(max_retries=3, backoff_factor=0.0))
    resp = client.get("https://example.com/x")
    assert resp.status_code == 404
    assert len(responses.calls) == 1
    client.close()


@responses.activate
def test_honors_retry_after_header_on_429() -> None:
    responses.add(responses.GET, "https://example.com/x", status=429, headers={"Retry-After": "0"})
    responses.add(responses.GET, "https://example.com/x", json={"ok": True}, status=200)

    client = HttpClient(HttpConfig(max_retries=1, backoff_factor=10.0))
    start = time.monotonic()
    resp = client.get("https://example.com/x")
    elapsed = time.monotonic() - start
    assert resp.status_code == 200
    # Retry-After: 0 should be used instead of the large backoff_factor.
    assert elapsed < 1.0
    client.close()


def test_default_client_singleton() -> None:
    set_default_client(None)
    c1 = get_default_client()
    c2 = get_default_client()
    assert c1 is c2
    set_default_client(None)


def test_set_default_client_overrides() -> None:
    custom = HttpClient(HttpConfig(timeout=99.0))
    set_default_client(custom)
    assert get_default_client() is custom
    set_default_client(None)
    custom.close()
