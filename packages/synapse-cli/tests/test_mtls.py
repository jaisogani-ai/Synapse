# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""mTLS — opt-in mutual TLS for A2A.

These tests exercise the real ``ssl`` module + ``urllib`` against a real
``ThreadingHTTPServer``. They are slower than the pure-Python unit tests
but they're the only honest way to verify that the handshake actually
requires + verifies a client cert.
"""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from synapse_cli.mtls import (
    CertBundle,
    extract_peer_common_name,
    generate_self_signed_cert,
    is_mtls_enabled,
    load_trust_dir,
    make_client_ssl_context,
    make_server_ssl_context,
)
from synapse_cli.transport import A2AServer


def _free_port() -> int:
    """Grab a free TCP port for the test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# ── cert generation ────────────────────────────────────────────────────────


def test_generate_self_signed_cert_writes_files(tmp_path: Path) -> None:
    bundle = generate_self_signed_cert("alice", tmp_path / "certs")
    assert isinstance(bundle, CertBundle)
    assert bundle.cert_path.exists()
    assert bundle.key_path.exists()
    assert bundle.cert_path.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    assert bundle.key_path.read_bytes().startswith(b"-----BEGIN RSA PRIVATE KEY-----")


def test_generate_self_signed_cert_rejects_empty_agent_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        generate_self_signed_cert("", tmp_path / "certs")


def test_load_trust_dir_returns_sorted_pems(tmp_path: Path) -> None:
    certs_dir = tmp_path / "certs"
    generate_self_signed_cert("bob", certs_dir)
    generate_self_signed_cert("alice", certs_dir)
    paths = load_trust_dir(certs_dir)
    assert [p.name for p in paths] == ["alice.crt", "bob.crt"]


def test_load_trust_dir_handles_missing(tmp_path: Path) -> None:
    assert load_trust_dir(tmp_path / "does-not-exist") == []


# ── env var helper ────────────────────────────────────────────────────────


def test_is_mtls_enabled_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYNAPSE_MTLS", raising=False)
    assert not is_mtls_enabled()
    monkeypatch.setenv("SYNAPSE_MTLS", "1")
    assert is_mtls_enabled()
    monkeypatch.setenv("SYNAPSE_MTLS", "true")
    assert is_mtls_enabled()
    monkeypatch.setenv("SYNAPSE_MTLS", "0")
    assert not is_mtls_enabled()


# ── integration: real TLS handshake ───────────────────────────────────────


def _smaller_cert(agent_id: str, out: Path) -> CertBundle:
    """Issue a 2048-bit key cert for tests — faster than the production 3072."""
    return generate_self_signed_cert(
        agent_id,
        out,
        key_bits=2048,
        validity_days=1,
    )


def test_mtls_server_accepts_valid_client_cert(tmp_path: Path) -> None:
    server_certs = tmp_path / "server-certs"
    client_trust = tmp_path / "client-trust"
    server_bundle = _smaller_cert("server", server_certs)
    client_bundle = _smaller_cert("client", server_certs)

    # Server trusts the client by having client's cert in its trust dir
    client_trust.mkdir()
    (client_trust / "client.crt").write_bytes(client_bundle.cert_path.read_bytes())
    server_ctx = make_server_ssl_context(
        server_bundle.cert_path, server_bundle.key_path, client_trust
    )

    # Client trusts the server by having server's cert in its trust dir
    server_trust = tmp_path / "server-trust"
    server_trust.mkdir()
    (server_trust / "server.crt").write_bytes(server_bundle.cert_path.read_bytes())
    client_ctx = make_client_ssl_context(
        client_bundle.cert_path, client_bundle.key_path, server_trust
    )

    def handler(*_args, **_kwargs):
        return {"jsonrpc": "2.0", "result": {"ok": True}, "id": ""}

    port = _free_port()
    server = A2AServer(port=port, handler=handler, ssl_context=server_ctx)
    server.start()
    try:
        time.sleep(0.2)
        # liveness GET over HTTPS with the matching client cert
        req = urllib.request.Request(f"https://127.0.0.1:{port}/", method="GET")
        with urllib.request.urlopen(req, timeout=2.0, context=client_ctx) as resp:
            assert resp.status == 200
            assert resp.read() == b"synapse-a2a-receiver"
    finally:
        server.stop()


def test_mtls_server_rejects_missing_client_cert(tmp_path: Path) -> None:
    """A client connecting with no cert at all must fail the handshake."""
    server_certs = tmp_path / "server-certs"
    client_trust = tmp_path / "client-trust"
    server_bundle = _smaller_cert("server", server_certs)
    # Even an empty trust dir requires a cert (verify_mode = CERT_REQUIRED)
    client_trust.mkdir()
    only_client = _smaller_cert("only-known-client", server_certs)
    (client_trust / "only.crt").write_bytes(only_client.cert_path.read_bytes())

    server_ctx = make_server_ssl_context(
        server_bundle.cert_path, server_bundle.key_path, client_trust
    )

    def handler(*_args, **_kwargs):
        return {"jsonrpc": "2.0", "result": {}, "id": ""}

    port = _free_port()
    server = A2AServer(port=port, handler=handler, ssl_context=server_ctx)
    server.start()
    try:
        time.sleep(0.2)
        # Client uses a default context with NO client cert — handshake must fail.
        import ssl as _ssl
        bare_ctx = _ssl.create_default_context()
        bare_ctx.check_hostname = False
        bare_ctx.verify_mode = _ssl.CERT_NONE
        req = urllib.request.Request(f"https://127.0.0.1:{port}/", method="GET")
        with pytest.raises((urllib.error.URLError, OSError)):
            urllib.request.urlopen(req, timeout=2.0, context=bare_ctx)
    finally:
        server.stop()


def test_mtls_server_rejects_untrusted_client_cert(tmp_path: Path) -> None:
    """A client presenting a cert NOT in the server's trust dir is rejected."""
    server_certs = tmp_path / "server-certs"
    client_trust = tmp_path / "client-trust"
    server_bundle = _smaller_cert("server", server_certs)
    trusted_client = _smaller_cert("trusted-client", server_certs)
    untrusted_client = _smaller_cert("untrusted-client", server_certs)

    client_trust.mkdir()
    (client_trust / "trusted.crt").write_bytes(trusted_client.cert_path.read_bytes())
    server_ctx = make_server_ssl_context(
        server_bundle.cert_path, server_bundle.key_path, client_trust
    )

    # Client uses the untrusted cert
    server_trust = tmp_path / "server-trust"
    server_trust.mkdir()
    (server_trust / "server.crt").write_bytes(server_bundle.cert_path.read_bytes())
    client_ctx = make_client_ssl_context(
        untrusted_client.cert_path, untrusted_client.key_path, server_trust
    )

    def handler(*_args, **_kwargs):
        return {"jsonrpc": "2.0", "result": {}, "id": ""}

    port = _free_port()
    server = A2AServer(port=port, handler=handler, ssl_context=server_ctx)
    server.start()
    try:
        time.sleep(0.2)
        req = urllib.request.Request(f"https://127.0.0.1:{port}/", method="GET")
        with pytest.raises((urllib.error.URLError, OSError)):
            urllib.request.urlopen(req, timeout=2.0, context=client_ctx)
    finally:
        server.stop()


def test_extract_peer_common_name_returns_empty_when_unset() -> None:
    """Safety: helper must not blow up when the SSL object has no peer cert."""

    class _Stub:
        def getpeercert(self) -> dict:
            return {}

    assert extract_peer_common_name(_Stub()) == ""
