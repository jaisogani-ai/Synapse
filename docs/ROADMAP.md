<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Synapse Roadmap

> From foundation to production-ready agent trust infrastructure.

## Completed

### Phase A — Audit & Direction

- Full repository audit (~118 files, ~10,700 LOC)
- Classified every file: KEEP / REWRITE / SPIN OUT / REMOVE
- Established four-pillar architecture: Identity, Vault, Trust, A2A
- Identified ~60 files (33%) for removal, ~30 files (31%) for spinout

### Phase B — Foundation

- **Rust daemon** with trust store, protocol codec, Unix-socket IPC
- **Zero-trust identity** — JWT (HS256) + HMAC-SHA256 request signing
- **Secret vault** — AES-256-GCM encrypted store with scoped proxy tokens
- **Capability system** — namespaced grants with wildcard support
- **Supply chain scanner** — OSV.dev + Shannon entropy heuristics
- **Reputation store** — in-memory in v1, confidence-weighted scoring; SQLite persistence is a P1 follow-up

### Phase C — CLI & A2A Integration

- **synapse-cli** — send-task, inbox, accept/reject, audit trail
- **A2A transport** — JSON-RPC over HTTP with signed headers
- **Identity resolver** — agent-to-endpoint directory
- **Receiving daemon** — signature verification, reputation gating, inbox

### Phase D — Adapters, Demos, Docs (current)

- **5 adapters** — Claude Code, Cursor, Codex, VS Code, Antigravity
  - Identity registration, trust headers, vault integration, A2A signing
- **3 launch demos**
  - VPS deploy with no raw credentials (drives the **real** AES-256-GCM vault)
  - Malicious sender rejection (3 attack vectors)
  - Trust-gated cross-device task delegation
- **Documentation** — README, ARCHITECTURE, TRUST_MODEL, PROTOCOL, ROADMAP

## Planned

### P1 — Rust-native identity / vault / a2a-signer modules

Identity, vault, and trust currently live in the Python SDK at
`packages/synapse-core/synapse/security/`. The Rust daemon today only owns
the trust store + IPC + audit transport.

- [ ] Rust-native identity module (move from `synapse.security.zero_trust`)
- [ ] Rust-native vault module backed by `synapse-vault-mcp`'s AES-256-GCM core
- [ ] Rust-native A2A signer (today in `synapse_cli/a2a_signer.py`)
- [ ] Wire `daemon/src/security/capability.rs` into the IPC dispatcher
      (code-complete, currently not consulted on each request)
- [ ] Persist `daemon/src/trust/reputation.rs` to SQLite — currently
      in-memory, despite TRUST_MODEL.md's "SQLite-backed" language
- [ ] Reconcile the dual trust/identity stores (Rust + Python) — pick one
      authoritative source rather than letting both drift

### Phase E — Production Hardening

- [ ] Token refresh / automatic rotation
- [ ] Rate limiting on the receiving daemon
- [ ] Connection pooling for high-throughput A2A
- [ ] Structured logging (JSON) with correlation IDs
- [ ] Graceful shutdown with in-flight task draining
- [ ] Health check endpoint on the daemon

### Phase F — Distribution & Packaging

- [ ] `pip install synapse-agent` (Python SDK + CLI)
- [ ] `cargo install synapsed` (Rust daemon)
- [ ] `npm install @synapse/vault-mcp` (Vault MCP server)
- [ ] Docker image with daemon + vault
- [ ] Homebrew formula

### Phase G — Advanced Trust

- [ ] Multi-domain reputation (per-skill trust scores)
- [ ] Trust delegation chains (A trusts B, B vouches for C)
- [ ] Reputation decay (scores fade without recent positive outcomes)
- [ ] Trust arbiter — weighted consensus from multiple agents
- [ ] Cross-network federation (trust across Synapse instances)

### Phase H — Ecosystem

- [ ] MCP marketplace integration (trust-gated skill registry)
- [ ] Pluggable compliance workers (GDPR, DPDP, SOC2)
- [ ] Dashboard UI for trust scores, audit trails, vault access
- [ ] Webhook notifications for trust events

## Non-Goals

These are explicitly out of scope for Synapse:

- **General-purpose AI agent framework** — Synapse provides identity and
  trust, not agent logic. Use Claude Code, Cursor, Codex, etc. for that.
- **Replacing A2A** — Synapse signs and verifies A2A messages, never
  replaces the A2A protocol.
- **LLM routing / model selection** — spun out as a standalone utility.
- **Memory management** — the 8-tier system was removed; memory is handled
  by the host tool.
