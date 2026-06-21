# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Tests for the Codex adapter."""

import pytest

from synapse.security.zero_trust import ZeroTrustNetwork

from adapters.codex import CodexAdapter
from adapters.base import VaultRequest, SignedMessage


@pytest.fixture
def network() -> ZeroTrustNetwork:
    return ZeroTrustNetwork()


@pytest.fixture
def adapter(network: ZeroTrustNetwork) -> CodexAdapter:
    return CodexAdapter(
        agent_id="codex-agent-01",
        network=network,
        capabilities=["vault.request_credential", "trust.read"],
    )


class TestCodexIdentityRegistration:
    def test_registers_identity(self, adapter: CodexAdapter, network: ZeroTrustNetwork) -> None:
        identity = adapter.register()
        assert identity.agent_id == "codex-agent-01"
        assert network.has_identity("codex-agent-01")

    def test_is_registered_after_register(self, adapter: CodexAdapter) -> None:
        assert not adapter.is_registered
        adapter.register()
        assert adapter.is_registered

    def test_tool_type(self, adapter: CodexAdapter) -> None:
        assert adapter.tool_type == "codex"

    def test_audit_log_records_registration(self, adapter: CodexAdapter) -> None:
        adapter.register()
        log = adapter.audit_log()
        assert len(log) == 1
        assert log[0].action == "register"
        assert log[0].tool_type == "codex"


class TestCodexSignedMessageRoundTrip:
    def test_sign_and_verify(self, adapter: CodexAdapter) -> None:
        adapter.register()
        payload = b'{"method": "trust.query", "target": "agent-77"}'

        signed = adapter.sign_message(payload)

        assert signed.payload == payload
        assert signed.headers.agent_id == "codex-agent-01"
        assert signed.headers.tool_type == "codex"
        assert adapter.verify_message(signed)

    def test_tampered_payload_fails_verification(self, adapter: CodexAdapter) -> None:
        adapter.register()
        signed = adapter.sign_message(b"original")
        tampered = SignedMessage(payload=b"tampered", headers=signed.headers)
        assert not adapter.verify_message(tampered)

    def test_sign_before_register_raises(self, adapter: CodexAdapter) -> None:
        with pytest.raises(RuntimeError, match="not registered"):
            adapter.sign_message(b"test")


class TestCodexVaultIntegration:
    def test_vault_request_routes(self, adapter: CodexAdapter) -> None:
        adapter.register()
        response = adapter.request_vault_credential(
            VaultRequest(service="openai", purpose="codex completion")
        )
        assert response.service == "openai"
        assert "proxy" in response.proxy_url
