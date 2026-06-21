# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Capability system — the authorization primitive for the Zero Trust network.

Every agent, MCP, and worker acts only within an explicitly granted set of
**capabilities**. A capability is a namespaced string ``"<domain>.<action>"``
(e.g. ``"trust.read"``, ``"vault.request_credential"``). Grants may use
wildcards: ``"trust.*"`` grants every ``trust.*`` action, and ``"*"`` grants
everything (reserved for the daemon itself).

The design follows the project's immutability rule: :class:`CapabilitySet` is
frozen, and ``grant`` / ``revoke`` return **new** sets rather than mutating.
The capability vocabulary here is kept consistent with the Rust daemon's
``Capability`` mapping (``daemon/src/security/capability.rs``) so a single grant
means the same thing in both languages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A capability name must be ``*`` or ``namespace.action`` / ``namespace.*``.
_CAPABILITY_RE = re.compile(r"^(?:\*|[a-z][a-z0-9_]*\.(?:\*|[a-z][a-z0-9_]*))$")


class CapabilityError(ValueError):
    """Raised when a capability string is malformed."""


@dataclass(frozen=True)
class Capability:
    """A known capability with a human-readable description and risk level."""

    name: str
    description: str
    risk: str = "medium"  # one of: low | medium | high


#: The canonical capability registry (extended each phase as agents land).
CAPABILITIES: tuple[Capability, ...] = (
    # Trust store
    Capability("trust.read", "Read trust scores and reputation data", "low"),
    Capability("trust.write", "Record outcomes and update reputation", "medium"),
    Capability("trust.search", "Search trust records", "low"),
    Capability("trust.admin", "Administer trust store", "high"),
    # Secret vault
    Capability("vault.request_credential", "Request a scoped credential proxy", "high"),
    Capability("vault.store_secret", "Store a new secret", "high"),
    Capability("vault.rotate", "Rotate a secret", "high"),
    Capability("vault.audit", "Read a secret's access log", "medium"),
    Capability("vault.revoke", "Immediately revoke a secret", "high"),
    Capability("vault.detect_exposure", "Scan content for leaked secrets", "low"),
    # Context optimization
    Capability("context.compress", "Compress conversation history", "low"),
    Capability("context.dedupe", "Remove duplicate context", "low"),
    Capability("context.summarize", "Summarize for handoff", "low"),
    Capability("context.evict", "Evict stale context", "low"),
    # Backend / database
    Capability("backend.scaffold", "Scaffold a backend project", "medium"),
    Capability("backend.schema", "Design a database schema", "medium"),
    Capability("backend.auth", "Design an auth system", "high"),
    Capability("backend.queue", "Design an async job queue", "medium"),
    Capability("db.query_optimize", "Optimize database queries", "low"),
    Capability("db.migrate", "Plan database migrations", "high"),
    # Filesystem / shell / network (sandbox-enforced)
    Capability("fs.read", "Read files in the project sandbox", "medium"),
    Capability("fs.write", "Write files in the project sandbox", "high"),
    Capability("shell.exec", "Execute whitelisted shell commands", "high"),
    Capability("net.proxied", "Network access via the daemon proxy", "medium"),
    # Security operations
    Capability("secret.detect", "Detect secrets before commit", "low"),
    Capability("supply_chain.scan", "Scan MCPs/plugins/packages", "medium"),
    # A2A — required by the receiving daemon for each RPC method
    Capability("a2a.send_task", "Send a task via A2A message/send", "medium"),
    Capability("a2a.send_result", "Return a result via A2A tasks/result", "medium"),
    Capability("a2a.read_status", "Read task status via A2A tasks/get", "low"),
)

#: Default A2A capability set granted to a CLI/adapter agent so it can both
#: send tasks and return results. Used by ``commands/send_task`` and the
#: ``synapse`` adapters as the baseline grant.
DEFAULT_A2A_CAPABILITIES: tuple[str, ...] = (
    "a2a.send_task",
    "a2a.send_result",
    "a2a.read_status",
)

#: Fast lookup of registered capability names.
_KNOWN: frozenset[str] = frozenset(c.name for c in CAPABILITIES)


def validate(name: str) -> str:
    """Return ``name`` if it is a well-formed capability, else raise.

    Raises:
        CapabilityError: if the format is invalid.
    """
    if not _CAPABILITY_RE.match(name):
        raise CapabilityError(
            f"invalid capability {name!r}; expected '*' or 'namespace.action'"
        )
    return name


def is_known(name: str) -> bool:
    """Whether ``name`` is in the canonical :data:`CAPABILITIES` registry."""
    return name in _KNOWN


def _pattern_matches(granted: str, required: str) -> bool:
    """Whether a single granted pattern satisfies a required capability.

    A namespace wildcard (``"x.*"``) only matches a required cap that
    actually carries a ``"<namespace>.<action>"`` shape — bare words never
    match a wildcard grant, even if the bare word equals the namespace.
    """
    if granted == "*":
        return True
    if granted == required:
        return True
    if granted.endswith(".*"):
        namespace = granted[:-2]
        if "." not in required:
            return False
        return required.split(".", 1)[0] == namespace
    return False


@dataclass(frozen=True)
class CapabilitySet:
    """An immutable set of granted capability patterns."""

    granted: frozenset[str]

    @classmethod
    def of(cls, *names: str) -> CapabilitySet:
        """Build a set from capability strings, validating each."""
        return cls(frozenset(validate(n) for n in names))

    @classmethod
    def empty(cls) -> CapabilitySet:
        """An empty capability set (grants nothing)."""
        return cls(frozenset())

    def allows(self, required: str) -> bool:
        """Whether any granted pattern satisfies ``required``."""
        validate(required)
        return any(_pattern_matches(g, required) for g in self.granted)

    def grant(self, *names: str) -> CapabilitySet:
        """Return a **new** set with ``names`` added (immutability)."""
        return CapabilitySet(self.granted | {validate(n) for n in names})

    def revoke(self, *names: str) -> CapabilitySet:
        """Return a **new** set with ``names`` removed (immutability)."""
        return CapabilitySet(self.granted - set(names))

    def to_sorted_list(self) -> list[str]:
        """Return the granted patterns as a sorted list."""
        return sorted(self.granted)

    def __len__(self) -> int:
        """Number of granted patterns."""
        return len(self.granted)
