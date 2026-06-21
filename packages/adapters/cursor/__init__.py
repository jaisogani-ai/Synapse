# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Cursor adapter — identity, vault, trust, and A2A signing for Cursor IDE."""

from synapse.security.zero_trust import ZeroTrustNetwork

from adapters.base import BaseAdapter


class CursorAdapter(BaseAdapter):
    """Adapter for the Cursor IDE agent tool."""

    tool_type = "cursor"

    def __init__(
        self,
        agent_id: str,
        network: ZeroTrustNetwork,
        capabilities: list[str] | None = None,
    ) -> None:
        super().__init__(agent_id, network, capabilities)


__all__ = ["CursorAdapter"]
