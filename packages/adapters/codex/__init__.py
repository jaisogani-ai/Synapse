# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Codex adapter — identity, vault, trust, and A2A signing for OpenAI Codex CLI."""

from synapse.security.zero_trust import ZeroTrustNetwork

from adapters.base import BaseAdapter


class CodexAdapter(BaseAdapter):
    """Adapter for the OpenAI Codex CLI agent tool."""

    tool_type = "codex"

    def __init__(
        self,
        agent_id: str,
        network: ZeroTrustNetwork,
        capabilities: list[str] | None = None,
    ) -> None:
        super().__init__(agent_id, network, capabilities)


__all__ = ["CodexAdapter"]
