<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Roadmap

> v1.0 is feature-complete. v1.x is the honest follow-up list, not a wishlist.

## v1.0 — shipped

Everything below is in the repo today, with tests:

- **Identity** — HMAC-SHA256 + HS256 JWT with `caps` claim ([`zero_trust.py`](../packages/synapse-core/synapse/security/zero_trust.py))
- **Vault** — AES-256-GCM with scoped, time-limited proxies; raw secret never crosses the wire ([`vault.ts`](../packages/synapse-vault-mcp/src/vault.ts))
- **Trust + reputation** — confidence-weighted scoring; low-rep content redacted ([`trust.py`](../packages/synapse-cli/synapse_cli/trust.py), [`reputation.rs`](../daemon/src/trust/reputation.rs))
- **A2A** — standard JSON-RPC over HTTP; signed envelopes; FilePart `uri` form for large files
- **Capability enforcement** — receiver-side per RPC method + Rust IPC per TrustOp
- **Durable outbox** — SQLite + exponential backoff + DLQ
- **Chunked file transfer** — content-addressed, HTTP `Range`, sha256 end-to-end
- **Presence** — `online` / `busy` / `offline`
- **Inbox + review** — accept / reject / review-before-decide
- **Audit log** — append-only JSONL, every gate failure recorded
- **5 adapters** — Claude Code, Cursor, Codex, VS Code, Antigravity
- **3 demos** — VPS handoff, cross-device delegation, malicious sender rejection
- **128 tests** — 39 Rust + 79 Python + 10 TypeScript, all green

## v1.x — planned follow-ups

These are honest gaps documented in [`KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md). Each is a contained change, not a new subsystem.

### Security hardening

- [ ] Persist Rust `TrustStore` to SQLite (T-1) — collapses the dual-store gap
- [ ] Endpoint hash pinning on `identity.json` (N-1 / SH-3)
- [ ] Hash-chained audit log (A-1 / M-9)
- [ ] Per-sender rate limit on receiver (I-2 / M-2)
- [ ] Encrypt-at-rest for `vault_client.py` (V-1 / M-7)
- [ ] Inbox SQLite WAL + busy timeout (I-1 / M-1)
- [ ] JWT `cnf` (confirmation) claim binding token to specific request

### Developer experience

- [ ] GitHub Actions CI workflow (H-1)
- [ ] Release automation (H-2)
- [ ] CycloneDX SBOM on release (H-3)
- [ ] Linux package in addition to source install

### Documentation

- [ ] Tutorial: setting up a 3-device personal cluster end-to-end
- [ ] How-to: rotating a compromised agent identity
- [ ] How-to: integrating a custom adapter

## v2 — open questions

These are ideas the project has not committed to. They earn their way in only if real use justifies the maintenance cost.

- Asymmetric (Ed25519) tokens instead of HS256
- Optional end-to-end payload encryption (probably Noise XK if it lands at all)
- Code-gen the capability vocabulary from one source-of-truth (K-1)
- Rust-native identity + vault, replacing the Python + Node implementations

## Non-goals (explicit)

These will not be built in any version of Synapse:

- Federation protocol / AFP / new wire format
- Memory layer
- Agent runtime or orchestration
- Multi-tenant SaaS
- Skill or agent marketplace
- "Agent OS" / "AI OS"

Synapse stays small on purpose.
