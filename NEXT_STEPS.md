# NEXT_STEPS

**Date:** 2026-06-22
**Tagline:** _Trusted A2A for Claude Code, Cursor, Codex, Antigravity, VS Code._

Status doc for the **v0.1 alpha** release. Each section names what was built,
what was verified, and what was deliberately deferred. Honest gaps live in
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

---

## What was built for v0.1

### Durable outbox ✅

A target-offline send no longer fails. The signed envelope is persisted to a
SQLite outbox (`packages/synapse-cli/synapse_cli/outbox_store.py`) and a
background worker (`outbox_worker.py`) drains the queue with exponential
backoff (`5s, 30s, 3m, 15m, 1h, 6h`). After `MAX_ATTEMPTS = 6` a row moves
to the `dead` state — it is never silently dropped. An operator can run
`synapse outbox list / retry / flush / purge`.

### Chunked, resumable file transfer ✅

Replaces the 10 MiB base64-in-JSON cap with a spec-compliant `FilePart.uri`
form. Files ≤ 256 KiB still inline as base64 (cheap path). Files above that
are stored in a content-addressed `BlobCache`
(`packages/synapse-cli/synapse_cli/blob.py`) and the `FilePart.uri` becomes
`synapse+blob://<sender>/<sha256>`. The receiver resolves the URI to the
sender's `GET /blob/<sha256>` endpoint — served by `transport.A2AServer` —
and downloads with standard HTTP `Range` requests. SHA-256 is verified
end-to-end; tampered or truncated blobs are rejected. The hard cap moves to
2 GiB.

No new protocol. Pure A2A spec (`FilePart.uri` is already permitted) + HTTP/1.1.

### Platform adapters ✅

All five adapters — Claude Code, Cursor, Codex, VS Code, Antigravity — exist
under `packages/adapters/` and subclass `BaseAdapter`. Each provides
identity registration (`register()`), trust signing/verification
(`sign_message`, `verify_message`, `build_trust_headers`), vault credential
routing (`request_vault_credential`), and A2A signing (HMAC-SHA256 over the
JSON-RPC envelope). 42 adapter tests pass.

### Simple presence ✅

`packages/synapse-cli/synapse_cli/presence.py` exposes three states only:
`online`, `busy`, `offline`. `LocalPresence` is a single-row JSON file the
operator can flip with `synapse presence set busy`. `A2AServer` now serves
`GET /presence` returning `{"status": ...}`. `synapse presence list` probes
every agent in the local identity registry and reports each one's status.
No CRDT, no gossip, no heartbeats — just an HTTP GET per query.

### Inbox review ✅

`synapse inbox review <task_id>` now shows the operator the full task
text, sender, sender reputation, status, and attachment metadata
(`uri`, `sha256`, `size` for blob attachments; inline-byte count for small
ones) **before** they decide to accept or reject. Existing accept/reject
paths are unchanged.

### Capability enforcement ✅

Capability gating is wired end-to-end:

- **A2A receiver** consults `METHOD_REQUIRED_CAPABILITY` for each inbound
  JSON-RPC and rejects with `capability denied` if the sender's
  `X-A2A-Token` JWT does not grant the required cap. Subject/sender mismatch
  is also rejected. 7 tests in
  `packages/synapse-cli/tests/test_capability_enforcement.py`.
- **Rust daemon IPC** reads a `caps` field on every `SynapseMessage`
  and checks each `TrustOp` against `is_granted()` before any mutation.
  4 tests in `daemon/src/ipc/mod.rs`.
- `docs/TRUST_MODEL.md` Gate 3 section documents the wiring with the
  method → capability and op → capability tables.

---

## Test coverage

| Suite | Result |
|---|---|
| Rust daemon (`cargo test`) | **39 / 39** passing |
| Vault MCP (`npm --workspace @synapse/secret-vault-mcp test`) | **10 / 10** passing |
| Python SDK + adapters + CLI (`pytest`) | **79 / 79** passing |
| **Total** | **128 / 128** |

Demos (end-to-end against real code paths):

| Demo | Status |
|---|---|
| `examples/vps-handoff-no-raw-keys/demo.py` | **PASS** |
| `examples/malicious-sender-rejection/demo.py` | **PASS** |
| `examples/cross-device-task-delegation/` | green |
| Outbox e2e (offline → queue → retry → dead → requeue) | green |
| Blob e2e (1 MiB, Range resume, sha256) | green |

---

## What remains (honest list — none blocks the alpha)

1. **Persistent Rust trust store.** `daemon/src/trust/reputation.rs` is
   in-memory in v0.1. The Python store at
   `packages/synapse-cli/synapse_cli/trust.py` is authoritative and is
   persisted. See `KNOWN_LIMITATIONS.md` T-1, T-2.
2. **Dual trust/identity stores.** v0.1 ships with the Python store as
   canonical; collapsing into Rust is a v0.2 item.
3. **Adapter-side tests of outbox/blob integration.** The new CLI surface is
   tested in standalone e2e scripts; integrating those flows into the
   existing pytest suite is a small follow-up.
4. **Carryovers from the bug-report MEDIUM list:**
   inbox SQLite WAL/busy-timeout (I-1), per-sender rate limit (I-2),
   secret-detector pass over audit `detail` (A-3), vault_client AES-at-rest (V-1),
   audit tamper-evidence chained hashing (A-1), identity_resolver endpoint hash
   pinning (N-1).

All carryovers are tracked in [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md)
and listed as v0.2 follow-ups in [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## Launch blockers

**None.**

Every test suite is green. Every e2e demo runs.

---

## What did **not** get built (by design)

The following were on the table and explicitly skipped — they belong to
later releases or to a different product than what we're shipping:

- AFP, a new wire protocol, QUIC, Noise sessions
- CRDTs, gossip, leader election
- Relay network, multi-tenant SaaS, enterprise SSO
- Scheduler, work-stealing, fork-join execution
- Agent marketplace, skill marketplace, memory layer
- "AI OS" / "Agent OS" framing

v0.1 is a **trusted A2A trust layer** for a developer who owns a laptop, a
desktop, a VPS, and a second account, and wants their AI tools to send each
other tasks, files, and results without exposing secrets. That's what it
does. That's where it stops.
