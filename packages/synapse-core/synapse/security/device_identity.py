# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Device identity — DID-style stable identifiers for Synapse agents.

This is **not** a full W3C DID method implementation. It is a stable,
self-issuable identifier format that follows the DID URI shape
(``did:synapse:<agent_id>``) so agents that already speak DID-flavoured
addressing can interoperate without us shipping a method registry.

The identifier ties an ``agent_id`` to a ``device_id`` (the host on which
the agent's signing key was issued) so a sender's identity carries both
*who* (agent) and *where* (device) in a single string. Verification is
still HMAC-based — DID format is the address, not the proof.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: DID URI prefix for Synapse-issued identifiers.
DID_METHOD = "synapse"
DID_PREFIX = f"did:{DID_METHOD}:"

#: Allowed characters in an agent_id (and the suffix half of a device_id).
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class DeviceIdentityError(ValueError):
    """Raised when a DID string is malformed."""


@dataclass(frozen=True)
class DeviceIdentity:
    """The structured form of ``did:synapse:<agent_id>[#<device_id>]``."""

    agent_id: str
    device_id: str = ""

    def to_did(self) -> str:
        """Render the identity as a DID URI."""
        base = f"{DID_PREFIX}{self.agent_id}"
        if self.device_id:
            return f"{base}#{self.device_id}"
        return base

    def __str__(self) -> str:
        return self.to_did()


def parse_did(did: str) -> DeviceIdentity:
    """Parse a ``did:synapse:<agent>[#<device>]`` string into a :class:`DeviceIdentity`.

    Raises:
        DeviceIdentityError: if the string is not a well-formed Synapse DID.
    """
    if not did.startswith(DID_PREFIX):
        raise DeviceIdentityError(
            f"not a synapse DID (missing {DID_PREFIX!r} prefix): {did!r}"
        )
    body = did[len(DID_PREFIX):]
    if "#" in body:
        agent, device = body.split("#", 1)
    else:
        agent, device = body, ""
    if not _ID_RE.match(agent):
        raise DeviceIdentityError(f"invalid agent_id in DID: {agent!r}")
    if device and not _ID_RE.match(device):
        raise DeviceIdentityError(f"invalid device_id in DID: {device!r}")
    return DeviceIdentity(agent_id=agent, device_id=device)


def make_did(agent_id: str, device_id: str = "") -> str:
    """Build a ``did:synapse:...`` string for ``agent_id`` (+ optional device)."""
    if not _ID_RE.match(agent_id):
        raise DeviceIdentityError(f"invalid agent_id: {agent_id!r}")
    if device_id and not _ID_RE.match(device_id):
        raise DeviceIdentityError(f"invalid device_id: {device_id!r}")
    return DeviceIdentity(agent_id=agent_id, device_id=device_id).to_did()
