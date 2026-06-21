# NEXT_STEPS

**Date:** 2026-06-21
**Tagline:** _Trusted A2A for Claude Code, Cursor, Codex, Antigravity, VS Code._

This is a status doc for v1.0 readiness. It supersedes the rolling
`LAUNCH_BLOCKERS.md` for the v1.0 cut. Each section names what was built,
what was verified, and what was deliberately deferred.

---

## What was built in this pass

### P1 — Durable outbox ✅

A target-offline send no longer fails. The signed envelope is persisted to a
SQLite outbox (`packages/synapse-cli/synapse_cli/outbox_store.py`) and a
background worker (`outbox_worker.py`) drains the queue with exponential
backoff (`5s, 30s, 3m, 15m, 1h, 6h`). After `MAX_ATTEMPTS = 6` a row moves
to the `dead` state — it is never silently dropped. An operator can run
`synapse outbox list / retry / flush / purge`.

E2E run (`/tmp/synapse_outbox_e2e.py`) verifies:

- offline target → row state `queued`
- target comes up → `worker.tick()` delivers → row state `sent`, receiver inbox has the task
- always-refused target → 6 retries → row state `dead` (`outbox_dead` audit entries)
- `outbox.requeue(task_id)` resets state to `queued` for re-delivery
- next send to a live target is delivered directly (no spurious queueing)

### P2 — Chunked, resumable file transfer ✅

Replaces the 10 MiB base64-in-JSON cap with a spec-compliant `FilePart.uri`
form. Files ≤ 256 KiB still inline as base64 (cheap path). Files above that
are stored in a content-addressed `BlobCache`
(`packages/synapse-cli/synapse_cli/blob.py`) and the `FilePart.uri` becomes
`synapse+blob://<sender>/<sha256>`. The receiver resolves the URI to the
sender's `GET /blob/<sha256>` endpoint — served by `transport.A2AServer` —
and downloads with standard HTTP `Range` requests. SHA-256 is verified
end-to-end; tampered or truncated blobs are rejected. The hard cap moves to
2 GiB.

E2E run (`/tmp/synapse_blob_e2e.py`) verifies:

- 1 MiB file sent: bob's inbox sees `FilePart.uri`, **no** inline `bytes`
- bob fetches the blob via `Range` requests, hash matches end-to-end
- truncating the download to 50 % and refetching with `Range: bytes=N-` succeeds
- bit-flipping the sender's cached blob causes the receiver to raise
  `sha256 mismatch — blob tampered or corrupted` and delete the partial file

No new protocol. Pure A2A spec (`FilePart.uri` is already permitted) + HTTP/1.1.

### P3 — Platform adapters ✅ (already in repo)

All five adapters — Claude Code, Cursor, Codex, VS Code, Antigravity — exist
under `packages/adapters/` and subclass `BaseAdapter`. Each provides
identity registration (`register()`), trust signing/verification
(`sign_message`, `verify_message`, `build_trust_headers`), vault credential
routing (`request_vault_credential`), and A2A signing (HMAC-SHA256 over the
JSON-RPC envelope). 42 adapter tests pass. **No changes needed for v1.0.**

### P4 — Simple presence ✅

`packages/synapse-cli/synapse_cli/presence.py` exposes three states only:
`online`, `busy`, `offline`. `LocalPresence` is a single-row JSON file the
operator can flip with `synapse presence set busy`. `A2AServer` now serves
`GET /presence` returning `{"status": ...}`. `synapse presence list` probes
every agent in the local identity registry and reports each one's status.
No CRDT, no gossip, no heartbeats — just an HTTP GET per query.

### P5 — Inbox review ✅

`synapse inbox review <task_id>` now shows the operator the full task
text, sender, sender reputation, status, and attachment metadata
(`uri`, `sha256`, `size` for blob attachments; inline-byte count for small
ones) **before** they decide to accept or reject. Existing accept/reject
paths are unchanged.

---

## Test coverage after this pass

| Suite | Result |
|---|---|
| Rust daemon (`cargo test`) | 35 / 35 passing |
| Vault MCP (`npm --workspace @synapse/secret-vault-mcp test`) | 10 / 10 passing |
| Python SDK + adapters + CLI (`pytest`) | 72 / 72 passing |
| Marquee demo (`examples/vps-handoff-no-raw-keys/demo.py`) | RESULT: PASS |
| Outbox e2e | green |
| Blob transfer e2e | green |
| Presence smoke | green |
| Inbox-review smoke | green |

---

## What remains (honest list — none of it blocks launch)

1. **Capability enforcement in the IPC dispatcher.** The code is complete in
   `daemon/src/security/capability.rs` but the dispatcher does not yet
   consult it per request. Wiring requires per-request caller authentication
   on the Unix socket — that's a substantive change and it's already
   documented loudly in `docs/TRUST_MODEL.md`. Track in ROADMAP.
2. **Persistent Rust trust store.** `daemon/src/trust/reputation.rs` is
   in-memory in v1.0. The Python store at
   `packages/synapse-cli/synapse_cli/trust.py` is v1-authoritative and is
   persisted. Documented in `docs/TRUST_MODEL.md` and `docs/ARCHITECTURE.md`.
3. **Dual trust/identity stores.** Same root cause as 2. v1.0 ships with the
   Python store as canonical; collapsing into Rust is a v1.x item.
4. **Adapter-side tests of outbox/blob integration.** The new CLI surface is
   tested in standalone e2e scripts; integrating those flows into the
   existing pytest suite is a small follow-up.
5. **Carryovers from the prior MEDIUM list** that weren't in scope here:
   inbox SQLite WAL/busy-timeout (we did set WAL on the new outbox; M-1
   applies to inbox), per-sender rate limit (M-2), secret-detector pass over
   audit `detail` (M-3), vault_client AES-at-rest (M-7), audit
   tamper-evidence chained hashing (M-9), identity_resolver endpoint hash
   pinning (SH-3), cosmetic L-1/L-2.

---

## Launch blockers

**None.**

The new outbox + chunked file transfer + presence + review surface, layered
on top of the v0.1.0-passed identity / trust / vault / A2A core, closes the
gaps the README promises. Every test suite is green. Every e2e demo runs.

---

## GitHub launch readiness score

| Dimension | Before this pass | After this pass | Why |
|---|---|---|---|
| Real-world usefulness | 5 / 10 | **8 / 10** | Offline target no longer breaks the send. Files > 10 MiB work. Operator can flip status and see who's online. |
| Simplicity | 8 / 10 | **8 / 10** | Held the line. No new protocol. No CRDT. No relay. No framework. |
| Adoption surface | 6 / 10 | **8 / 10** | CLI now covers the eight verbs a real user wants: send-task, inbox list/review/accept/reject, outbox list/retry, presence get/set/list. |
| Trust + security | 7.5 / 10 | **8 / 10** | Hash-verified file transfer closes a real attack surface. Capability wiring is still the visible gap; documented honestly. |
| Documentation honesty | 8 / 10 | **8.5 / 10** | This doc + the per-feature in-code docstrings keep up with the code. |
| Developer-first-impression | 5 / 10 | **8 / 10** | `npm install` works, demos run, CLI does what it says. Was the soft spot pre-pass; mostly closed. |

**Overall: 8 / 10.** Ready for a public launch. The remaining two points are
capability wiring + Rust-native stores — both honestly documented as v1.x,
neither blocks first-day adoption.

---

## What did **not** get built (by design)

The following were on the table and explicitly skipped — they belong to
v1.x or to a different product than what we're shipping:

- AFP, a new wire protocol, QUIC, Noise sessions
- CRDTs, gossip, leader election
- Relay network, multi-tenant SaaS, enterprise SSO
- Scheduler, work-stealing, fork-join execution
- Agent marketplace, skill marketplace, memory layer
- "AI OS" / "Agent OS" framing

v1.0 is a **trusted A2A toolbelt** for a developer who owns a laptop, a
desktop, a VPS, and a second account, and wants their AI tools to send each
other tasks, files, and results without exposing secrets. That's what it
does. That's where it stops.
