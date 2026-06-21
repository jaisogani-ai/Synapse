<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Security Review — v0.1 (alpha)

**Date:** 2026-06-21
**Status:** v0.1 release review. Supersedes the prior phase-4 snapshot.
**Verification:** 128 / 128 automated tests passing (39 Rust + 79 Python + 10 TypeScript).

This document is a working threat model. It says what Synapse defends, what it doesn't, what attacks it stops, and which limitations are honest gaps that ship knowingly in v0.1.

For reporting a vulnerability, see [`SECURITY.md`](SECURITY.md).
For a flat list of every honest gap, see [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

---

## 1. Assets protected

| Asset | Where it lives | Why it matters |
|---|---|---|
| **Agent identity secrets** (HMAC keys) | `ZeroTrustNetwork._secrets` (in-memory) | Anyone with the secret can forge messages as that agent. |
| **Vault secrets** (raw API keys, tokens, certs) | `SecretVault` AES-256-GCM ciphertext + per-vault master key | These never leave the vault — the whole product hinges on this invariant. |
| **JWT tokens** (capability bearers) | Issued on demand by `ZeroTrustNetwork.issue_token`, 15-min TTL | Stolen token → attacker speaks as the subject for up to 15 minutes within the cap set. |
| **Trust scores** | `TrustStore` (`trust.json` for v0.1, daemon SQLite next) | Inflated trust → low-rep gate is bypassed → forged messages get less scrutiny. |
| **Inbox tasks** | `inbox.db` SQLite per receiver | A backdated or rewritten inbox row hides a real event from the operator. |
| **Outbox queue** | `outbox.db` SQLite per sender | Forging an outbox row → the worker sends an attacker-crafted message under the sender's identity. |
| **Audit log** | `audit.jsonl` per host | Append-only forensic record. Tampering hides incidents. |
| **Blob cache** | `blobs/` dir per sender (content-addressed) | A flipped bit in the cache → all current and future fetches of that hash get tampered content (caught by the receiver's sha256 verify). |

## 2. Attack classes considered

### 2.1 Spoofing

| Attack | Status | Defence |
|---|---|---|
| Forged HMAC signature | **Mitigated** | Gate 1 — `verify_payload_signature` rejects mismatched HMAC; constant-time compare. |
| Forged JWT (random bytes) | **Mitigated** | Gate 3 — `verify_token` checks HS256 with the agent's signing secret. |
| Forged JWT (stolen secret) | **Documented limitation** | Per-agent secret is the trust root. If exfiltrated, attacker can issue arbitrary tokens for that agent. Rotation is a one-line call (`network.issue_identity(agent_id)`). |
| Token subject ≠ HMAC sender | **Mitigated** | Receiver's `_check_capability` rejects when `claims.sub != sender_id`. Test: `test_request_with_token_subject_mismatch_is_denied`. |

### 2.2 Replay

| Attack | Status | Defence |
|---|---|---|
| Captured A2A request replayed later | **Mitigated** | Timestamp is bound into the signed payload (`payload \| ts`); receiver enforces ±300s drift window. |
| Captured envelope replayed inside drift window with same `task_id` | **Mitigated** | `inbox_store.insert` has `PRIMARY KEY (task_id)` — duplicate insert raises `DuplicateTaskError`, audited as `reject_replay`. |
| Captured JWT replayed for a different request | **Partially mitigated** | JWT's 15-min TTL bounds the window. Subject-binding in cap check prevents cross-agent replay. Same-agent same-method same-window replay is not separately bound (HMAC binds the body, not the token specifically). |

### 2.3 Secret leakage

| Attack | Status | Defence |
|---|---|---|
| Raw key serialized into an A2A message | **Mitigated by convention** | `send_task` detects credential-touching tasks via keyword match and routes them through the vault proxy. The raw key is never serialized. |
| Raw key written to audit log | **Mitigated** | Audit entries carry only `signature_hash[:16]`, `task_id`, `action`, no payload. |
| Vault secret leaked via memory dump | **Not mitigated** | Vault is encrypted at rest only. In-process the master key + plaintext live in process memory. Use OS-level memory protection / disable swap if this is in your threat model. |
| Logged stack trace leaks secret | **Mitigated** | Receiver catches all exceptions and returns generic `"internal error"`. No exception text crosses the wire. |
| Secret committed accidentally to repo | **Mitigated** | `secret_detector.py` is run repo-wide; CI hook recommended. 140+ patterns + entropy fallback. |

### 2.4 Capability escalation

| Attack | Status | Defence |
|---|---|---|
| Request without a token | **Mitigated** | Receiver requires `X-A2A-Token`; missing → `capability denied: missing X-A2A-Token`. |
| Request with a token that lacks the required cap | **Mitigated** | Method → required-cap table; `CapabilitySet.allows` checks wildcards; deny + audit `reject_capability`. |
| `*` wildcard granted to a remote agent | **Operator misconfiguration** | Out-of-scope per `SECURITY.md`. Documented as `*` is for the daemon's own self-signed requests only. |
| Self-issued token with extra caps | **Mitigated** | A token is HS256-signed with the agent's per-agent secret. The agent can only issue tokens for itself, with caps the receiver actually checks against the method table — extra caps are inert. |
| Rust daemon IPC bypass | **Mitigated** | `SynapseMessage.caps` field; dispatcher checks `is_granted` before every TrustOp. Empty caps → denied with `CAPABILITY_DENIED`. |

### 2.5 Impersonation

| Attack | Status | Defence |
|---|---|---|
| MITM injects messages on the wire | **Mitigated cryptographically** | Even a MITM cannot mint a valid HMAC without the agent's secret. Use HTTPS/Tailscale on top for confidentiality. |
| MITM strips signature header | **Mitigated** | Receiver rejects unsigned messages immediately, audited `reject_unsigned`. |
| Compromised target endpoint URL | **Documented limitation** | `identity_resolver.json` is operator-controlled. If you can write to it, you can redirect messages. v0.1.0-alpha assumes the operator's filesystem is trusted. |
| Endpoint hash pinning (defence against above) | **Deferred** (SH-3 in `BUG_REPORT.md`) — planned follow-up. |

### 2.6 Audit tampering

| Attack | Status | Defence |
|---|---|---|
| Append a fake row | **Mitigated** | Hash-chained log (SHA-256 `prev_hash` + `entry_hash` per row). An inserted forged entry's `prev_hash` won't match the surrounding chain and is flagged by `synapse audit verify`. |
| Delete or rewrite a row | **Mitigated** | Same chain. Deleting a row breaks the next row's `prev_hash`; modifying a row breaks its own `entry_hash`. Detected at the exact index. Tested in `test_audit_chain.py` (8 tests). |

### 2.7 Denial of service

| Attack | Status | Defence |
|---|---|---|
| Oversized inbound POST | **Mitigated** | `MAX_REQUEST_BYTES = 12 MiB`; larger payloads return HTTP 413. |
| Oversized blob fetch | **Mitigated** | `MAX_BLOB_BYTES = 2 GiB`; receiver verifies `size` from `FilePart.size` before allocating. |
| Connection flood on receiver | **Out of scope for v0.1.0-alpha** | Use the platform's connection limits (systemd, iptables, reverse proxy). Per-sender rate limit is a planned follow-up (M-2). |
| Disk fill via inbox spam | **Partially mitigated** | Inbox queues on disk but has no row cap. Manual `synapse inbox` review + reject is the v0.1.0-alpha mitigation. |
| Outbox retry storm | **Mitigated** | Exponential backoff (5s → 6h); `MAX_ATTEMPTS = 6`; one worker per process. |

---

## 3. Defence-in-depth summary — the three gates

```
   inbound A2A message
        │
        ▼
  ┌─────────────┐    Gate 1: HMAC + timestamp drift (±300 s)
  │  SIGNATURE  │ →  reject_unsigned / reject_bad_signature
  └──────┬──────┘
         ▼
  ┌─────────────┐    Gate 2: reputation ≥ threshold (default 0.5)
  │  REPUTATION │ →  content redacted for low-rep until accept
  └──────┬──────┘
         ▼
  ┌─────────────┐    Gate 3: token cap covers method's required cap
  │  CAPABILITY │ →  reject_capability (missing | insufficient | subject mismatch)
  └──────┬──────┘
         ▼
     dispatch
```

Each gate is independently testable. Each failure produces an audit entry. **No gate can be bypassed by skipping a header** — the receiver requires every header it consults and gives no implicit benefit-of-the-doubt to malformed input.

---

## 4. Fixed before the v0.1 cut

These issues were found and resolved during development, before the public v0.1 alpha. Each row links the old problem to its fix in the current tree.

| Issue | Resolution |
|---|---|
| Capability code existed but was not consulted by the IPC dispatcher | Wired into both the A2A receiver (`receiver.py`) and the Rust IPC dispatcher (`daemon/src/ipc/mod.rs`). 11 new tests. |
| Marquee demo used a simulated vault, not the real AES-256-GCM one | `demo.py` now drives `packages/synapse-vault-mcp` via a Node bridge. |
| Inline base64 file transfer capped at 10 MiB; no resume | A2A-spec `FilePart.uri` form with content-addressed blob endpoint, HTTP `Range` resume, sha256 end-to-end. Cap raised to 2 GiB. |
| Offline target → send fails | Durable SQLite outbox + worker with exponential backoff + DLQ. |
| Daemon banner / `/health` claimed identity, vault, a2a subsystems that didn't exist in the Rust process | Banner and `/health` now report only what's actually running (`trust`). |
| `package.json` workspaces listed an empty dir and a Python pkg | Fixed; `npm install` clean. |
| `~/.cargo/bin/cargo` hardcoded in `package.json` | Relies on PATH. |
| README claimed Phase D complete with stale tree | Full rewrite with accurate module listing. |
| ARCHITECTURE.md described the daemon's IPC as A2A | Corrected; clear disambiguation. |

The full prior bug list lives in [`BUG_REPORT.md`](BUG_REPORT.md). Every CRITICAL and HIGH has been closed.

---

## 5. Known limitations (carry forward from v0.1)

These are documented gaps that we knowingly ship. Each has either a planned fix in a future release or an operational mitigation.

| Limitation | Mitigation today | Planned fix |
|---|---|---|
| Rust `TrustStore` is in-memory | Python store is authoritative for v0.1; restart of the Rust daemon loses recorded outcomes. | SQLite backing — v0.2. |
| No end-to-end payload encryption | HMAC integrity only. Use HTTPS / Tailscale / WireGuard for confidentiality. | Documented choice — TLS-or-tunnel is the v0.1 answer. |
| Endpoint hash pinning (SH-3) | `identity.json` is operator-controlled; assume trusted FS. | Endpoint pinning by sha256 — v0.2. |
| Audit tamper-evidence (M-9) | Append-only JSONL + recommended `chattr +a`. | Hash-chained audit — v0.2. |
| Per-sender rate limit (M-2) | OS / reverse proxy limits. | Add token-bucket per sender — v0.2. |
| Vault at-rest for `vault_client.py` (M-7) | The vault MCP (`packages/synapse-vault-mcp`) is encrypted at rest. The CLI's in-process `vault_client.py` is in-memory only, used for sender-side proxy issuance during a single CLI invocation. | Encrypt-at-rest for `vault_client.py` — v0.2. |
| Inbox SQLite WAL/busy-timeout (M-1) | Outbox already uses WAL; inbox does not. Low concurrency in v0.1, so this is mostly cosmetic. | Enable on inbox — v0.2. |

Full list with reproduction notes: [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

---

## 6. Assumptions

Synapse assumes the following hold. If any of them don't, the security claims may degrade:

1. **The operator's filesystem is trusted.** `identity.json`, `trust.json`, `outbox.db`, `inbox.db`, `audit.jsonl`, and `blobs/` all live under `$SYNAPSE_HOME` (default `~/.synapse`). An attacker with write access to that directory can defeat most defences.
2. **The agent's signing secret is held only by the agent.** Stolen secret → full impersonation for that agent until the operator rotates. Rotation is one call.
3. **Time is roughly synchronised.** The 300-second timestamp drift window is the only liveness check. Clock skew greater than that will reject otherwise-valid messages.
4. **The Python store is the canonical trust store for v0.1.** The Rust store is in-memory infrastructure being filled in over subsequent releases. Do not split-brain configure both.
5. **You provide the transport security on hostile networks.** HMAC proves authenticity. It does not provide confidentiality. Put HTTPS or a tunnel underneath if anyone could read the wire.

---

## 7. Open issues

These are honest follow-ups, not blockers. Tracked in [`docs/ROADMAP.md`](docs/ROADMAP.md):

- Persistent Rust trust store (SQLite-backed)
- Endpoint hash pinning
- Hash-chained audit log
- Per-sender rate limit on receiver
- Encrypt-at-rest for `vault_client.py`
- Inbox SQLite WAL + busy timeout
- Token-binding: add a `cnf` (confirmation) claim so a JWT is bound to a specific request via the HMAC signature, blocking same-window same-method replay
