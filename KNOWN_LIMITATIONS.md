<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Known Limitations

**Date:** 2026-06-21
**Applies to:** v1.0.x

This is the honest list. No marketing. If something does not work the way the docs imply, it should be in this file. If you find a limitation that isn't listed, please open an issue — the omission is a bug.

---

## Architecture / scope (intentional)

These are not gaps. They are non-goals. Listed so nobody is surprised.

1. **No federation, relay, or discovery service.** Synapse is for the developer who owns their devices. Each peer's endpoint URL goes in `identity.json` by hand. No mDNS, no relay, no rendezvous.
2. **No memory layer.** Use Mem0, Supermemory, Graphiti, or none. Synapse does not store conversation context.
3. **No agent runtime / orchestration.** Use Claude Code, Cursor, Codex, or whatever you have. Synapse does not run agents; it gives them identity, capabilities, and a vault.
4. **No multi-tenant SaaS.** Self-hosted only. v1 has no notion of "tenant," "organisation," or "billing."
5. **No GUI.** CLI plus library calls. A web UI is not planned.

---

## Cryptography

| # | Limitation | Impact | Mitigation today | Plan |
|---|---|---|---|---|
| C-1 | No end-to-end payload encryption | A network observer can read A2A JSON-RPC payloads (not raw vault secrets — those never serialize) | Put HTTPS / Tailscale / WireGuard / SSH tunnel underneath | Documented choice — TLS-or-tunnel is the v1 answer. If we add encryption later it will be opt-in. |
| C-2 | Per-agent secret is the trust root | Exfiltrating a secret lets an attacker forge messages and tokens for that one agent | Rotate via `network.issue_identity(agent_id)` (one call) | Stays per-agent for v1. Hardware-key-backed identity is a maybe for v2. |
| C-3 | JWT TTL is 15 min by default | An exfiltrated token works for up to 15 minutes | Lower `DEFAULT_TTL_SECONDS` if your environment needs it | Configurable per-issue. No change planned. |
| C-4 | HS256 (HMAC) tokens, not asymmetric | Receiver must hold the sender's secret to verify | Per-agent secret is shared at identity issuance time, never on the wire | Asymmetric (Ed25519) tokens are a v1.x consideration. |

---

## Trust store

| # | Limitation | Impact | Mitigation today | Plan |
|---|---|---|---|---|
| T-1 | Rust `TrustStore` is in-memory | Daemon restart loses recorded outcomes | Python store (`trust.json`) is v1-authoritative and is persisted | SQLite backing for Rust store — v1.x |
| T-2 | Two trust stores exist (Python + Rust); only the Python one is authoritative | If you query the Rust daemon over IPC for `get_score`, the answer comes from a different store than the one the CLI uses | Read the docs: Python is canonical for v1 | Collapse to one store — v1.x |
| T-3 | No trust score decay over time | A score earned in 2024 weighs the same as one earned today | Operator can manually reset | Time-decay weighting — v1.x |

---

## Audit log

| # | Limitation | Impact | Mitigation today | Plan |
|---|---|---|---|---|
| A-1 | No hash chain | An attacker with write access can delete or rewrite past entries | Recommend `chattr +a` on the audit file (Linux) | Hash-chained audit — v1.x (M-9 in BUG_REPORT.md) |
| A-2 | No external sink | Audit is local-only | Tail the file into your SIEM / syslog | Pluggable audit sink — v1.x |
| A-3 | Audit `detail` is not run through the secret detector | An accidental key-shaped string in a detail field would land in `audit.jsonl` | Don't put secrets in detail strings; CLI doesn't | Wrap `AuditLog.append` with `secret_detector.detect` — v1.x (M-3) |

---

## Vault

| # | Limitation | Impact | Mitigation today | Plan |
|---|---|---|---|---|
| V-1 | `vault_client.py` is in-memory only | A process restart of the sender CLI loses any locally-stored secrets | Use the vault MCP for any persisted secret; `vault_client.py` is for in-flight proxy issuance during a single CLI run | Encrypt-at-rest for `vault_client.py` — v1.x (M-7) |
| V-2 | Vault master key is generated per-process | Restart the vault MCP, lose access to previously-stored ciphertext | Persist the master key out-of-band (env var, KMS, etc.) when running in production | Documented integration path; no change in v1 |
| V-3 | Proxy TTL max is 1 hour (`MAX_PROXY_SECONDS`) | Long-running deploys must re-issue proxies | Re-request periodically | Configurable — v1.x |

---

## Inbox / Outbox

| # | Limitation | Impact | Mitigation today | Plan |
|---|---|---|---|---|
| I-1 | Inbox SQLite is not WAL + busy-timeout (M-1) | Concurrent writers could see `database is locked` | One process per host is the v1 default — not a real issue | Enable WAL on inbox (outbox already has it) — v1.x |
| I-2 | No per-sender rate limit (M-2) | A flood of valid messages from one sender fills the inbox | OS / reverse proxy limits | Token-bucket per sender — v1.x |
| O-1 | Outbox row's `endpoint_url` is fixed at enqueue time | Retargeting requires a fresh `send-task` | This is by design — the signed payload binds to a specific receiver | No change planned |
| O-2 | Outbox worker re-issues a fresh JWT at delivery time | If you remove the sender's identity from the network, in-flight retries silently produce empty-token rejections | Keep identities until the outbox drains | No change planned — fail-closed is the right behaviour |

---

## Networking / discovery

| # | Limitation | Impact | Mitigation today | Plan |
|---|---|---|---|---|
| N-1 | `identity.json` is operator-controlled, no endpoint hash pinning (SH-3) | Whoever writes the file can redirect messages | Restrict file permissions on `$SYNAPSE_HOME` | Endpoint pinning by sha256 — v1.x |
| N-2 | No NAT traversal | Both peers must be reachable, or one must be | Use a VPN (Tailscale / WireGuard) | No change — using a VPN is the right answer |
| N-3 | No connection pooling | Each `post_jsonrpc` opens a new TCP connection | Latency is the cost, not correctness | HTTP keep-alive — v1.x |

---

## Capability system

| # | Limitation | Impact | Mitigation today | Plan |
|---|---|---|---|---|
| K-1 | Capability vocabulary lives in two places (Python and Rust) | Must be kept in sync by hand | Compared in code review; same set | Code-gen one from the other — v1.x consideration |
| K-2 | `*` wildcard grants everything | Operator misconfiguration is dangerous | Documented: `*` is for the daemon's self-signed requests only | No change — explicit is better than disabling |
| K-3 | Downstream MCPs (e.g. vault MCP) do their own cap enforcement | The receiver checks A2A method caps, but the vault MCP's HTTP endpoints must independently enforce `vault.*` caps | Wire vault MCP to consult the same JWT — already done in synapse-vault-mcp | No change |

---

## Platform support

| # | Limitation | Impact | Mitigation today |
|---|---|---|---|
| P-1 | Tested on macOS (Darwin 25.5) | Linux should work; Windows is untested | Use Linux/macOS for v1 |
| P-2 | Python 3.11+ required | Older 3.x missing PEP 604 union syntax | Pin in `pyproject.toml` |
| P-3 | Node 20+ required for vault MCP | Older Node missing built-in test runner | Pin in `package.json` engines |

---

## Process / housekeeping

| # | Limitation | Impact | Mitigation today | Plan |
|---|---|---|---|---|
| H-1 | No CI workflow in `.github/workflows/` | Tests must be run locally before push | Run `cargo test && pytest && npm test` before every commit | Add GitHub Actions — v1.x |
| H-2 | No release automation | Tags published by hand | Maintainer cuts each release manually | Add release-please / similar — v1.x |
| H-3 | No SBOM | Downstream consumers can't audit dependency tree mechanically | `cargo tree`, `pip list`, `npm ls` work | Generate CycloneDX SBOM on release — v1.x |

---

## What's specifically **not** a limitation

Mentioning these because they get asked:

- **"Synapse doesn't replace A2A."** Correct, by design. Synapse signs and verifies A2A; it doesn't fork the wire format. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- **"Synapse doesn't have a memory tier."** Correct, by design. Use whatever memory tool you like.
- **"Synapse doesn't ship a hosted relay."** Correct, by design. Self-hosted only.
- **"Synapse uses HMAC, not Ed25519."** True, and intentional — HMAC has no PKI requirement. Asymmetric is a v1.x consideration if it earns its way in.
- **"Synapse stores trust as JSON on disk."** Yes — small surface, easy to inspect, easy to back up. Rust SQLite store is a v1.x parallel option.
