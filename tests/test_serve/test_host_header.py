"""The local viewer must answer only to its own loopback Host (DNS rebinding).

The server binds 127.0.0.1, so nothing off-box connects directly. A web page
the user has open can still reach it by DNS rebinding: ``evil.example`` first
resolves to the attacker, then to 127.0.0.1, and the page's script fetches
``/api/graph`` and ``/note/...`` same-origin. The browser keeps sending
``Host: evil.example`` the whole time, so checking Host closes that path.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from http.client import HTTPConnection

import pytest

from hyperresearch.core.vault import Vault
from hyperresearch.serve.server import HyperresearchHandler, HyperresearchServer


@contextmanager
def _server(vault: Vault):
    HyperresearchHandler.vault = vault
    server = HyperresearchServer(("127.0.0.1", 0), HyperresearchHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def _get(port: int, path: str, host: str | None):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.putrequest("GET", path, skip_host=True)
        if host is not None:
            conn.putheader("Host", host)
        conn.endheaders()
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        conn.close()


@pytest.mark.parametrize(
    "host_fmt",
    ["127.0.0.1:{port}", "localhost:{port}", "LOCALHOST:{port}", "[::1]:{port}", "127.0.0.1"],
)
def test_loopback_hosts_are_served(seeded_vault, host_fmt):
    with _server(seeded_vault) as port:
        status, headers, body = _get(port, "/", host_fmt.format(port=port))
    assert status == 200
    assert b"Python Async Patterns" in body
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize(
    "host_fmt",
    [
        "evil.example:{port}",
        "evil.example",
        "127.0.0.1.evil.example:{port}",
        "localhost.evil.example:{port}",
        "127.0.0.1:1",  # right name, another port
        "",
    ],
)
@pytest.mark.parametrize("path", ["/", "/api/graph", "/note/python-async-patterns"])
def test_foreign_hosts_get_no_vault_content(seeded_vault, host_fmt, path):
    with _server(seeded_vault) as port:
        status, _headers, body = _get(port, path, host_fmt.format(port=port))
    assert status == 421
    assert b"Python Async Patterns" not in body
    assert b"python-async-patterns" not in body


def test_missing_host_header_is_refused(seeded_vault):
    with _server(seeded_vault) as port:
        status, _headers, _body = _get(port, "/api/graph", None)
    assert status == 421

