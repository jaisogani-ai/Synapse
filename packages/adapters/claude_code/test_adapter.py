# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Tests for the Claude Code adapter."""

import pytest

from synapse.security.zero_trust import ZeroTrustNetwork

from adapters.claude_code import ClaudeCodeAdapter
from adapters.base import VaultRequest


@pytest.fixture
def network() -> ZeroTrustNetwork:
    return ZeroTrustNetwork()


@pytest.fixture
def adapter(network: ZeroTrustNetwork) -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter(
        agent_id="claude-code-agent-01",
        network=network,
        capabilities=["vault.request_credential", "trust.read"],
    )


class TestClaudeCodeIdentityRegistration:
    def test_registers_identity(self, adapter: ClaudeCodeAdapter, network: ZeroTrustNetwork) -> None:
        identity = adapter.register()
        assert identity.agent_id == "claude-code-agent-01"
        assert network.has_identity("claude-code-agent-01")

    def test_is_registered_after_register(self, adapter: ClaudeCodeAdapter) -> None:
        assert not adapter.is_registered
        adapter.register()
        assert adapter.is_registered

    def test_tool_type(self, adapter: ClaudeCodeAdapter) -> None:
        assert adapter.tool_type == "claude-code"

    def test_audit_log_records_registration(self, adapter: ClaudeCodeAdapter) -> None:
        adapter.register()
        log = adapter.audit_log()
        assert len(log) == 1
        assert log[0].action == "register"
        assert log[0].tool_type == "claude-code"


class TestClaudeCodeSignedMessageRoundTrip:
    def test_sign_and_verify(self, adapter: ClaudeCodeAdapter) -> None:
        adapter.register()
        payload = b'{"method": "trust.query", "target": "agent-42"}'

        signed = adapter.sign_message(payload)

        assert signed.payload == payload
        assert signed.headers.agent_id == "claude-code-agent-01"
        assert signed.headers.tool_type == "claude-code"
        assert signed.headers.signature != ""
        assert adapter.verify_message(signed)

    def test_tampered_payload_fails_verification(self, adapter: ClaudeCodeAdapter) -> None:
        adapter.register()
        signed = adapter.sign_message(b"original payload")

        from adapters.base import SignedMessage
        tampered = SignedMessage(payload=b"tampered payload", headers=signed.headers)
        assert not adapter.verify_message(tampered)

    def test_sign_before_register_raises(self, adapter: ClaudeCodeAdapter) -> None:
        with pytest.raises(RuntimeError, match="not registered"):
            adapter.sign_message(b"test")


class TestClaudeCodeTrustHeaders:
    def test_trust_headers_contain_identity(self, adapter: ClaudeCodeAdapter) -> None:
        adapter.register()
        headers = adapter.build_trust_headers(b"test payload")
        header_dict = headers.to_dict()

        assert header_dict["X-Synapse-Agent"] == "claude-code-agent-01"
        assert header_dict["X-Synapse-Tool"] == "claude-code"
        assert header_dict["X-Synapse-Signature"] != ""
        assert "X-Synapse-Token" in header_dict
        assert "X-Synapse-Timestamp" in header_dict


class TestClaudeCodeVaultIntegration:
    def test_vault_request_routes(self, adapter: ClaudeCodeAdapter) -> None:
        adapter.register()
        response = adapter.request_vault_credential(
            VaultRequest(service="openai", purpose="code completion")
        )
        assert response.service == "openai"
        assert "proxy" in response.proxy_url

    def test_vault_request_before_register_raises(self, adapter: ClaudeCodeAdapter) -> None:
        with pytest.raises(RuntimeError, match="not registered"):
            adapter.request_vault_credential(
                VaultRequest(service="openai", purpose="test")
            )
