<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Inspirations

> Ideas, systems, and papers that shaped Synapse's design.

## Identity & Cryptography

**SSH key-based authentication** — The mental model for Synapse identity.
Every agent gets a unique signing key. Every request is verified. No
passwords, no shared secrets between agents.

**JWT (RFC 7519)** — Short-lived bearer tokens with embedded claims. Synapse
uses HS256 JWTs with `sub`, `iat`, `exp`, and `caps` (capabilities) claims.
The 15-minute TTL is deliberately short — tokens are cheap to issue and
expensive to misuse.

**HMAC-SHA256** — The signature primitive. Chosen because it's available in
every language's standard library (Python `hmac`, Rust `hmac` crate, Node
`crypto`), requires no PKI infrastructure, and provides 256-bit security.

## Trust & Reputation

**eBay/Amazon seller ratings** — Confidence-weighted reputation from
observed outcomes. A new agent starts at 0.5 (neutral), not 1.0 (fully
trusted). Trust is earned through successful task completions.

**Google PageRank (conceptual)** — Trust as a network property, not a
per-node attribute. An agent trusted by many trusted agents inherits
credibility. (Phase G will implement trust delegation chains.)

**Certificate Transparency (CT logs)** — Append-only audit logs that make
every trust decision visible and verifiable after the fact. Synapse's JSONL
audit trail serves the same purpose: you can forensically reconstruct every
trust decision.

## Capability Systems

**Capsicum / capability-based security** — Agents receive an explicit set
of named capabilities at registration time. No ambient authority. The
principle of least privilege is enforced at the protocol level, not by
convention.

**AWS IAM policies** — Namespaced permissions (`vault.request_credential`,
`trust.read`) with wildcard support (`vault.*`). Familiar to anyone who has
written IAM policy documents.

## Vault & Secret Management

**HashiCorp Vault** — The proxy credential pattern. Agents request scoped,
time-limited access tokens instead of raw secrets. The vault resolves the
proxy to the real credential at the last possible moment.

**1Password Connect / Doppler** — Scoped API tokens that abstract away the
underlying secret. The consuming application never knows (or needs to know)
the actual API key.

**Envelope encryption (AWS KMS pattern)** — Secrets encrypted at rest with
AES-256-GCM. The encryption key is derived per-secret, not shared.

## Protocol & Transport

**Google A2A (Agent-to-Agent protocol)** — The A2A specification defines
Tasks, Messages, Parts, and Artifacts. Synapse signs and verifies A2A
messages — it never replaces the protocol. The JSON-RPC 2.0 transport
layer is per the A2A spec.

**gRPC / Protocol Buffers** — Synapse Protocol v1.0 uses a structured wire
format (JSON-encoded, length-prefixed over Unix sockets) inspired by
protobuf's message discipline. A future version may adopt protobuf for
performance.

**Unix domain sockets** — The daemon listens on a local socket, not a TCP
port. This provides OS-level access control (file permissions) and avoids
exposing the trust infrastructure to the network.

## Architecture

**Microkernel / message-passing OS** — The Synapse daemon is a small,
privileged kernel. Everything else (adapters, MCP servers, CLI) runs as an
untrusted satellite that communicates through the protocol. The daemon
enforces policy; satellites implement functionality.

**Zero Trust Architecture (NIST SP 800-207)** — No implicit trust based on
network location. Every request is authenticated, authorized, and logged
regardless of origin. The daemon verifies even local-socket requests.

**Sidecar proxy pattern (Envoy/Istio)** — Adapters act as sidecars to
their host tools (Claude Code, Cursor, etc.). They handle identity and
signing transparently, so the host tool doesn't need to know about Synapse
internals.

## What Synapse Is Not

Synapse deliberately avoids being inspired by:

- **LangChain / CrewAI / AutoGen** — Agent orchestration frameworks.
  Synapse provides trust infrastructure, not agent logic.
- **Kubernetes RBAC** — Too coarse-grained for agent-level capabilities.
  Synapse's capability system is finer-grained and per-token.
- **Blockchain / DID** — Interesting for decentralized identity, but adds
  complexity that isn't justified for single-user or small-team deployments.
  May revisit in Phase G for cross-network federation.
