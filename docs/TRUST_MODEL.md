<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Synapse Trust Model

> How Synapse decides which agents to trust, and how much.

## Core Principle: Zero Trust

No agent is implicitly trusted. Every request is verified cryptographically
before any action is taken. Trust is earned through observed outcomes, not
declared by configuration.

## The Three Gates

Every inbound A2A message passes through three gates in sequence. Failure
at any gate stops processing immediately.

```
   inbound message
        │
        ▼
  ┌─────────────┐
  │  Gate 1:     │  Does the message carry a valid HMAC-SHA256 signature
  │  SIGNATURE   │  from a known agent identity?
  └──────┬──────┘
         │ pass
         ▼
  ┌─────────────┐
  │  Gate 2:     │  Is the sender's reputation score above the minimum
  │  REPUTATION  │  threshold for the requested action?
  └──────┬──────┘
         │ pass
         ▼
  ┌─────────────┐
  │  Gate 3:     │  Does the sender's capability set include the
  │  CAPABILITY  │  permission required for this operation?
  └──────┬──────┘
         │ pass
         ▼
     process task
```

## Gate 1: Cryptographic Identity

Every agent receives a unique HMAC-SHA256 signing key from the daemon when
it registers. Every outbound message is signed with this key. The receiver
verifies the signature before parsing the payload.

- **Algorithm:** HMAC-SHA256 (stdlib only, zero deps)
- **Key size:** 256-bit random secret per agent
- **Token format:** HS256 JWT with `sub`, `iat`, `exp`, `caps` claims
- **TTL:** 15 minutes by default (short-lived by design)

Unsigned or wrongly-signed messages are rejected immediately and logged to
the audit trail with `action=reject_unsigned`.

**Implementation:** `packages/synapse-core/synapse/security/zero_trust.py`

## Gate 2: Reputation Scoring

Each agent has a reputation score in `[0.0, 1.0]` maintained by the trust
store. The score reflects confidence-weighted historical outcomes.

| Score range | Treatment |
|-------------|-----------|
| `>= 0.5` (default threshold) | Normal processing |
| `< 0.5` | Task queued but content **redacted** until explicit accept |
| `0.0` | Effectively blocked — content always redacted |

Low-reputation senders are never silently dropped. Their messages are queued
so the receiver can inspect metadata (sender, timestamp, signature validity)
and choose to accept or reject. Content is only revealed after explicit
acceptance.

**Implementation:** The **Python store** at
`packages/synapse-cli/synapse_cli/trust.py` is the **v0.1-authoritative** trust
store and is what the CLI consults. `daemon/src/trust/reputation.rs` is the
Rust-native target for the same logic, currently **in-memory** and **not
synchronized** with the Python store — it is a roadmap target, not a
production source of truth. See [ROADMAP.md](ROADMAP.md) for the
"reconcile dual stores" follow-up.

## Gate 3: Capability Authorization

Agents are granted named capabilities when their token is issued. The
capability system uses namespaced strings with wildcard support:

```
vault.request_credential   — exact grant
vault.*                    — namespace wildcard
*                          — global wildcard (admin)
```

A request that requires a capability not present in the agent's token is
rejected with a clear error. Capabilities are checked after signature
verification but before any side effects.

### How Gate 3 is wired (v0.1)

**A2A receiver — `packages/synapse-cli/synapse_cli/receiver.py`**

Every inbound JSON-RPC envelope carries a sender-issued JWT in the
`X-A2A-Token` header. The receiver consults
`METHOD_REQUIRED_CAPABILITY` for the requested method and calls
`ZeroTrustNetwork.verify_request(token, required_capability, payload, signature)`.
Missing token, expired token, subject ≠ HMAC sender, or insufficient `caps` →
the request is rejected with a `capability denied: <reason>` error and a
`reject_capability` audit entry. Method → required capability:

| A2A method        | Required capability  |
|-------------------|----------------------|
| `message/send`    | `a2a.send_task`      |
| `tasks/result`    | `a2a.send_result`    |
| `tasks/get`       | `a2a.read_status`    |

**Rust daemon IPC — `daemon/src/ipc/mod.rs`**

The `SynapseMessage` envelope now carries a `caps: Vec<String>` field.
Every `TrustOp` requires a capability, checked by `is_granted()` from
`daemon/src/security/capability.rs` before any mutation. Old envelopes that
omit `caps` deserialize to an empty vec — those requests are denied for any
op that requires a capability. Trust op → required capability:

| TrustOp variant  | Required capability |
|------------------|---------------------|
| `RecordOutcome`  | `trust.write`       |
| `GetScore`       | `trust.read`        |
| `ShouldTrust`    | `trust.read`        |
| `RankAgents`     | `trust.read`        |

Wildcard grants work as documented: `"trust.*"` allows every trust op,
`"*"` allows everything (intended for the daemon's own self-signed
requests). `Ping` and `Health` are not capability-gated.

**Implementation:**
- Capability vocabulary: `packages/synapse-core/synapse/security/capabilities.py`
  (canonical) and `daemon/src/security/capability.rs` (Rust mirror; strings must stay in sync).
- A2A enforcement: `packages/synapse-cli/synapse_cli/receiver.py` —
  `METHOD_REQUIRED_CAPABILITY` table + `_check_capability` helper.
- IPC enforcement: `daemon/src/ipc/mod.rs` — `required_capability_for(&op)` +
  `is_granted()` check at the top of `handle_request`.

## Vault Integration

The trust model extends to credential access. Agents never receive raw API
keys. Instead:

1. Agent requests a scoped, time-limited **credential proxy** from the vault
2. Vault issues a proxy token with a TTL (default 300s)
3. Agent uses the proxy token; only the daemon resolves it to the real secret
4. Every access is recorded in an append-only audit log

Raw secrets are encrypted at rest with AES-256-GCM. The proxy mechanism
ensures that even a compromised agent cannot exfiltrate the real credential.

**Implementation:** `packages/synapse-vault-mcp/src/vault.ts`

## Supply Chain Verification

Before trusting a third-party MCP server or package, Synapse checks:

1. **OSV.dev CVE lookup** — known vulnerabilities in declared dependencies
2. **Shannon entropy analysis** — flags suspiciously obfuscated manifests
3. **Signature presence** — unauthenticated servers get lower initial trust

**Implementation:** `packages/synapse-core/synapse/security/supply_chain.py`

## Audit Trail

Every trust decision is logged to an append-only audit trail:

- `receive_task` — task accepted with sender score
- `reject_unsigned` — signature verification failed
- `vault_request` — credential proxy issued
- `send_task` — outbound task with signature hash

The audit trail is the single source of truth for forensic analysis. No
trust decision happens without a corresponding log entry.

## Threat Model

| Threat | Mitigation |
|--------|-----------|
| Replay attacks | JWT `exp` claim enforces 15-minute TTL |
| Key compromise | Per-agent keys; rotation via `issue_identity` |
| Privilege escalation | Capability set is immutable per token |
| Credential theft | Vault proxy tokens, never raw secrets |
| Social engineering | Low-rep content redacted until explicit accept |
| Supply chain attack | OSV + entropy scanning before trust |
