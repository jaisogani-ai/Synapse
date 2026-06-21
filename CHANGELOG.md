<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Changelog

All notable changes to Synapse will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html);
the leading `0.` line is alpha — minor bumps may carry breaking changes.

## [Unreleased]

Tracked in [`docs/ROADMAP.md`](docs/ROADMAP.md) under v0.2.

## [0.1.0-alpha] — 2026-06-22

First public release.

### Added

- **Identity** — per-agent HMAC-SHA256 signing keys, short-lived HS256 JWTs with `sub`, `iat`, `exp`, `caps` claims (`packages/synapse-core/synapse/security/zero_trust.py`).
- **Vault** — AES-256-GCM secret store with scoped, time-limited proxy URLs; raw secret never crosses the wire (`packages/synapse-vault-mcp/src/vault.ts`).
- **Trust + reputation** — confidence-weighted scoring; low-rep senders' content redacted until explicit accept (`packages/synapse-cli/synapse_cli/trust.py`, `daemon/src/trust/reputation.rs`).
- **Capability gate** — every A2A method requires a specific capability; sender JWT must grant it and `sub` must match the HMAC sender. Wired on the Python receiver and the Rust IPC dispatcher (`receiver.py`, `daemon/src/ipc/mod.rs`).
- **A2A transport** — standard JSON-RPC over HTTP, HMAC-signed envelopes, spec-compliant `FilePart` with `uri` for large files (`packages/synapse-cli/synapse_cli/a2a.py`).
- **Durable outbox** — SQLite queue with exponential backoff (5s → 6h) and DLQ after `MAX_ATTEMPTS = 6` (`outbox_store.py`, `outbox_worker.py`).
- **Chunked file transfer** — content-addressed blob endpoint with HTTP `Range` resume and sha256 end-to-end verification (`blob.py`).
- **Presence** — `online` / `busy` / `offline` over `GET /presence`. No CRDT, no gossip (`presence.py`).
- **Inbox + review** — SQLite-backed received-task queue; `synapse inbox review <id>` shows content before accept/reject (`inbox_store.py`, `commands/inbox.py`).
- **Audit log** — append-only **hash-chained** JSONL. Each entry carries `prev_hash` + `entry_hash` (SHA-256), so any modified, deleted, or forged row is detectable. Verifiable via `synapse audit verify`. (`audit.py`)
- **5 adapters** — Claude Code, Cursor, Codex, VS Code, Antigravity (`packages/adapters/`).
- **3 demos** — `vps-handoff-no-raw-keys`, `cross-device-task-delegation`, `malicious-sender-rejection`.
- **CLI** — `send-task`, `inbox list|review|accept|reject`, `outbox list|retry|flush|purge`, `presence get|set|list`.
- **Documentation** — README, ARCHITECTURE, TRUST_MODEL, PROTOCOL, ROADMAP, INSPIRATIONS, KNOWN_LIMITATIONS, SECURITY_REVIEW, SECURITY, 6 Mermaid diagrams.

### Tests

- `cargo test`: 39 / 39
- `pytest`: 79 / 79
- `npm test` (vault MCP): 10 / 10
- **Total: 128 / 128**

### Known limitations

See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). Headlines: Rust `TrustStore` is in-memory; no E2E payload encryption (use HTTPS/Tailscale); audit log not hash-chained; no endpoint hash pinning yet.

### Security

No known vulnerabilities at release. Vulnerability reporting policy: [`SECURITY.md`](SECURITY.md). Threat model: [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md).

[Unreleased]: ../../compare/v0.1.0-alpha...HEAD
[0.1.0-alpha]: ../../releases/tag/v0.1.0-alpha
