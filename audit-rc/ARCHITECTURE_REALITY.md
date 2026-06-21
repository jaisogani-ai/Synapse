# ARCHITECTURE_REALITY

**Date:** 2026-06-21
**Method:** Followed the call graph from `daemon/src/main.rs`, then from every
Python entry point (`a2a_signer.py`, `receiver.py`, `commands/send_task.py`,
`commands/inbox.py`), then `packages/synapse-vault-mcp/src/server.ts`. Only
code that is reachable from a real entry point is documented as "implemented".

This document **replaces** `docs/ARCHITECTURE.md` (which describes Phase B and
is now stale; see `DOC_AUDIT.md` § ARCHITECTURE.md for the divergences).

---

## 1. What actually runs

At v1 release, Synapse consists of **three independent processes** plus a set
of in-process libraries:

| Process | Binary | Language | What it owns |
|---------|--------|----------|--------------|
| Daemon | `synapsed` | Rust | Reputation store (SQLite in-memory), Synapse Protocol v1.0, Unix-socket IPC |
| Vault MCP | `synapse-secret-vault-mcp` | TypeScript / Node | AES-256-GCM secret store, scoped credential proxies, exposure scanner |
| Receiving daemon | embedded in `synapse_cli.transport.A2AServer` | Python | A2A HTTP receiver, signature/freshness/reputation gates, inbox SQLite |

In-process libraries linked into the host tool / CLI / receiver:

| Library | Where it lives | What it provides |
|---------|----------------|------------------|
| `synapse.security.zero_trust` | `packages/synapse-core` | `ZeroTrustNetwork`: issue identities (HMAC keys), issue HS256 JWTs, sign and verify request bodies |
| `synapse.security.capabilities` | `packages/synapse-core` | Capability registry + wildcard matcher (`vault.*`, `trust.read`, etc.) |
| `synapse.security.secret_detector` | `packages/synapse-core` | 140+ provider regexes + Shannon-entropy fallback |
| `synapse.security.supply_chain` | `packages/synapse-core` | OSV.dev CVE lookup + entropy heuristics |
| `synapse_cli.a2a_signer` | `packages/synapse-cli` | `A2ASigner` — signs `(payload || timestamp)`; 5-minute freshness window |
| `synapse_cli.receiver` | `packages/synapse-cli` | `ReceivingDaemon` — signature gate → reputation gate → inbox insert → audit |
| `synapse_cli.transport` | `packages/synapse-cli` | HTTP server with 12 MiB body cap; `post_jsonrpc` client |
| `synapse_cli.inbox_store` | `packages/synapse-cli` | SQLite pending-tasks table; `DuplicateTaskError` on replay |
| `synapse_cli.trust` | `packages/synapse-cli` | JSON-file reputation `0.0..=1.0` keyed by `agent_id` (separate from the daemon's) |
| `synapse_cli.identity_resolver` | `packages/synapse-cli` | JSON-file `agent_id → URL` registry |
| `synapse_cli.audit` | `packages/synapse-cli` | Append-only JSONL audit log (not tamper-evident) |
| `synapse_cli.vault_client` | `packages/synapse-cli` | **In-memory plaintext** secret store — diverges from the TS vault |
| `adapters.base.BaseAdapter` | `packages/adapters` | Per-agent identity registration + sign/verify wrapper |

## 2. Component diagram

```
                     ┌────────────────────────────────────────────────────────┐
                     │                                                        │
                     │   HOST TOOL  (Claude Code · Cursor · Codex · VS Code) │
                     │                                                        │
                     │   ┌──────────────────────────────────────────────┐    │
                     │   │ Python:  synapse_cli  +  synapse-core SDK    │    │
                     │   │                                              │    │
                     │   │  ZeroTrustNetwork ──┐                        │    │
                     │   │                     ▼                        │    │
                     │   │  A2ASigner ── sign(payload || ts) ──┐        │    │
                     │   │                                     │        │    │
                     │   │  TrustStore (trust.json) ◀──┐       │        │    │
                     │   │  IdentityResolver (json)    │       │        │    │
                     │   │                             │       │        │    │
                     │   │  send_task() ───── HTTP POST + headers ──────┼──► A2A receiver
                     │   │                                              │    │   (other host)
                     │   │  ReceivingDaemon ◀──────── HTTP POST ────────┘    │
                     │   │       │                                            │
                     │   │       ├─► InboxStore (SQLite)                      │
                     │   │       └─► AuditLog   (JSONL)                       │
                     │   └──────────────────────────────────────────────┘    │
                     │                                                        │
                     │   ┌──────────────────────────────────────────────┐    │
                     │   │ MCP client (host's own MCP runtime)          │    │
                     │   └────────────┬─────────────────────────────────┘    │
                     └────────────────┼─────────────────────────────────────┘
                                      │
                                      │ stdio MCP transport
                                      ▼
                     ┌──────────────────────────────────────────────────────┐
                     │  Node process: synapse-secret-vault-mcp              │
                     │                                                      │
                     │  SecretVault                                         │
                     │  · AES-256-GCM (node:crypto)                         │
                     │  · proxy tokens (`synapse+vault://proxy/<token>`)    │
                     │  · auditLog[]                                        │
                     │  · detectExposure(content)                           │
                     └──────────────────────────────────────────────────────┘


                     ┌──────────────────────────────────────────────────────┐
                     │  (Future) Rust process: synapsed                      │
                     │                                                      │
                     │  TrustStore::new_in_memory()      ──╮                │
                     │  ReputationMemory  (SQLite memory) │                │
                     │  protocol::SynapseMessage codec    │ Unix socket    │
                     │  ipc::serve(unix-socket-path)      │  (no Python    │
                     │                                    │   client yet)  │
                     │  (security::capability defined,   ◀─╯               │
                     │   but never called from IPC)                        │
                     └──────────────────────────────────────────────────────┘
```

**Reality check:** the dashed Rust process at the bottom is up and serving the
Synapse Protocol, but no satellite in the v1 codebase actually connects to
it. The trust score the Python `send_task` consults is the Python-side
`trust.json`, not the Rust daemon's SQLite. The Rust daemon is the foundation
the rest of v1 will move onto in Phase E; today it is exercised only by its
own integration tests.

## 3. Trust flow (end-to-end, signed A2A `message/send`)

```
sender host                                receiver host
──────────────────────────────────────────────────────────────────
ZeroTrustNetwork
  · issue_identity(sender_id)            ◀─ (one time)
  · issue_token(sender_id, caps, ttl=15m)

A2ASigner.sign(sender_id, payload)
  · ts = now()
  · sig = HMAC_SHA256(secret, payload || "|" || ts)

post_jsonrpc(url, payload, sender, sig, ts)
  · POST application/json
  · X-A2A-Sender:    sender_id
  · X-A2A-Signature: sig (hex)
  · X-A2A-Timestamp: ts                  ──HTTP──►
                                                    ReceivingDaemon.handle_request
                                                      Gate 1 (signature + freshness)
                                                        · reject if signature mismatch
                                                        · reject if |now - ts| > 300
                                                          → audit("reject_unsigned" / "bad_signature_or_stale")
                                                      Gate 2 (reputation)
                                                        · score = trust.get_score(sender_id)
                                                        · score < threshold ⇒ low-rep queue
                                                          (still queued; never silently dropped)
                                                      Gate 3 (capability)
                                                        · enforced inside the JWT/CapabilitySet
                                                          at the call site
                                                      InboxStore.insert(task_id, sender, ...)
                                                        · IntegrityError on duplicate task_id
                                                          → audit("reject_replay")
                                                      audit("receive_task", score=<n>)
                                                    ◀──HTTP 200 {"taskId":..., "state":"submitted"}
```

The capability check (Gate 3 in the trust model) is **declarative** today: the
JWT carries `caps`, and `ZeroTrustNetwork.verify_request(token, required)` is
the choke point. There is no separate enforcement process; each satellite
performs the check on the API surface it owns.

## 4. Vault flow (no raw key on the wire)

```
sender host (Codex on a VPS)              vault MCP                vault store
──────────────────────────────────────────────────────────────────────────────
agent decides to deploy
   │
   ▼
vault.request_credential
   service="anthropic_api"
   purpose="deploy worker-N"             ──MCP tool call──►
   duration_seconds=300
                                                          ttl = min(d, 3600)
                                                          token = randomBytes(24)
                                                          proxies[token] = {service, expires}
                                                          auditEntries += "issue_proxy"
                                          ◀─────────────  CredentialProxy {
                                                              proxyUrl: synapse+vault://proxy/<token>,
                                                              proxyToken: token,
                                                              expiresAt: <ISO-8601>
                                                          }
agent gets only the proxy URL
   │
   ▼
HTTP layer (or daemon network proxy) sees the request,
detects `synapse+vault://proxy/<token>`, calls:
                                          ──MCP tool call──►
                                                          vault.resolveProxy(token, now)
                                                              · expired? → null
                                                              · else: decrypt(store.get(service))
                                                              · auditEntries += "resolve_proxy"
                                          ◀─────────────  <real secret>
                                          (passed only into the outbound HTTP)

audit log holds: issue_proxy + resolve_proxy + (eventually) revoke
NO raw key ever appears in the agent's process, on the A2A wire, or in
any log.
```

Real key never leaves the vault process. Audit log records *which* secret
was resolved, *when*, *for which purpose* — never the value.

## 5. Identity flow (where keys come from)

```
host tool starts up
   │
   ▼
adapter (BaseAdapter subclass)
   adapter.register()
     · ZeroTrustNetwork.issue_identity(agent_id)
         secret = secrets.token_bytes(32)        ◀── per-agent HMAC key
         _secrets[agent_id] = secret
     · ZeroTrustNetwork.issue_token(agent_id, caps, ttl=900)
         header   = {alg:"HS256", typ:"JWT"}
         payload  = {sub, iat, exp=iat+900, caps:[...]}
         sig      = HMAC_SHA256(secret, signing_input)
         token    = b64url(header).b64url(payload).b64url(sig)
   │
   ▼
adapter holds: AgentIdentity {agent_id, secret}  +  token (HS256 JWT)
```

The token's `caps` claim is the only authorization the receiver consults:
`CapabilitySet.of(*claims.caps).allows(required)`. Capabilities are
namespaced strings (`vault.request_credential`, `trust.read`) with wildcard
support (`vault.*`).

**Gap surfaced by this audit:** there is no shared identity registry across
processes. Each `ZeroTrustNetwork` instance has its own dictionary of
agent secrets. Cross-process verification works **only because the demos
construct one `ZeroTrustNetwork` and pass it to both the sender and
receiver code paths**. A real deployment with separate sender/receiver
processes will need the empty `daemon/src/identity/` module to be filled
in; that is the Phase E identity store.

## 6. A2A integration

Synapse does **not** speak A2A on the wire. A2A's transport is JSON-RPC 2.0
over HTTP; Synapse uses exactly that transport (`synapse_cli.transport`).
What Synapse adds is three HTTP headers:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-A2A-Sender` | the agent id | tells the receiver which HMAC key to verify against |
| `X-A2A-Signature` | hex HMAC-SHA256 | the signature over `(body || "|" || timestamp)` |
| `X-A2A-Timestamp` | unix seconds | bound into the signed material to defeat replay |

The body is an unmodified A2A JSON-RPC envelope (`message/send`, `tasks/get`,
`tasks/result`). A non-Synapse receiver would simply ignore the three headers
and process the body as plain A2A; a Synapse receiver enforces the gates
before parsing.

The Rust daemon does **not** see A2A traffic. The headers are added by the
Python `A2ASigner`, sent by Python `post_jsonrpc`, verified by Python
`ReceivingDaemon.handle_request`. The daemon owns reputation and Synapse
Protocol, nothing else.

## 7. What used to be here but isn't

The repo history shows previous architectures the documentation may still
reference; this v1 explicitly does not include them:

| Removed / out of scope | Replaced by |
|------------------------|-------------|
| 8-tier memory system (T1–T8) | Memory is owned by the host tool. Synapse does not store conversation context. |
| Generic "agent worker" / orchestration framework | Synapse provides primitives; orchestration is the host tool's job (see ROADMAP.md non-goals). |
| `daemon/src/{identity,vault,a2a_signer}/` Rust modules | Currently empty directories. Identity and vault primitives live in Python and TypeScript respectively; consolidating them into the Rust daemon is Phase E. |
| `packages/synapse-trust-mcp/` | Empty placeholder declared in `package.json` workspaces. Will be deleted before launch (see `RELEASE_SCORE.md` blockers) — the daemon already exposes trust ops over the Synapse Protocol. |
| Model router / cost utility | Spun out under `spinout/synapse-router/`. May move to its own repo. |
| Memory / context / skills MCPs | Spun out under `spinout/*`. Standalone value, but not part of the v1 trust layer. |

## 8. Reality summary

| Pillar | Real today | Notes |
|--------|------------|-------|
| Identity (HMAC keys, HS256 JWTs, request signing) | yes | Python in-process; no cross-process registry yet |
| Trust (reputation 0–100, SQLite) | partial | Rust daemon: in-memory only. Python CLI: separate JSON file. Two stores. |
| Vault (AES-256-GCM, scoped proxies) | yes | Per-process master key; on-disk persistence pending |
| Signed A2A | yes | HMAC over `(payload || timestamp)`, 5-minute drift window |
| Capability enforcement | partial | Python: live and checked. Rust: defined but unused. |
| Supply-chain scanning | yes | OSV.dev + Shannon entropy; no retry/circuit breaker |
| Secret detection | yes | 140+ patterns + entropy fallback |
| Audit log | yes-but | JSONL, not tamper-evident (chained-hash deferred to Phase E) |
| Adapters | thin | 5 tool labels, one shared implementation |
| 3 demos | yes | All run; vps-handoff uses a simulated vault, not the TS one |

This is the architecture to ship. Phase E should consolidate the identity
store into the Rust daemon, move the trust store to on-disk SQLite, and
either fill in the empty `daemon/src/{identity,vault,a2a_signer}/` modules
or delete them.
