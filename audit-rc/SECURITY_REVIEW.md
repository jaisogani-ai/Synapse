# SECURITY_REVIEW (RC pass)

**Date:** 2026-06-21
**Scope:** Same modules as the original `SECURITY_REVIEW.md` plus the daemon's
IPC and capability code. This audit was performed after the Phase 4 fixes
landed; findings here are **what remains in the working tree as of the RC
cut**.

The previous `SECURITY_REVIEW.md` is preserved as the historical record. This
file is the **current** view: which items were closed, which are still open,
and which are new.

---

## Status of prior findings

### Closed (verified fix in the working tree)

| Prior | Where verified | What changed |
|-------|----------------|--------------|
| SC-1 / C-1 (replay) | `a2a_signer.py:22–24, 41–60`, `receiver.py:50–61` | Signature now binds `(payload || "|" || ts)`; `MAX_TIMESTAMP_DRIFT_SECONDS = 300`; receiver rejects with `bad_signature_or_stale`. |
| SC-2 / C-2 (malformed params crash) | `receiver.py:74–80, 100–102, 156–177` | `params or {}` + `isinstance(params, dict)` guard at the top; per-handler `isinstance(task_id, str)` checks. |
| H-1 (SQLite IntegrityError unhandled) | `inbox_store.py:19, 95–98` + `receiver.py:120–133` | `DuplicateTaskError` raised cleanly; receiver writes `audit("reject_replay")` and returns `-32000` JSON-RPC error. |
| H-3 / SM-5 (audit JSON crash on partial line) | `audit.py:49–54` | `try/except (json.JSONDecodeError, TypeError)` skips bad lines. |
| H-4 / SM-1 / SM-3 (file size DoS) | `transport.py:29, 128–141`, `send_task.py:48` | `MAX_REQUEST_BYTES = 12 MiB`, `MAX_ARTIFACT_BYTES = 10 MiB`, receiver returns `413` before reading body. |
| H-2 / SH-6 (capability decode crash) | `zero_trust.py:206–213` | `try: CapabilitySet.of(*claims.caps) except (CapabilityError, ValueError)` returns `VerificationResult(ok=False)`. |

That is six CRITICAL/HIGH items genuinely closed. The Phase 4 work was substantive.

### Still open (deferred per `LAUNCH_BLOCKERS.md`)

| Prior | Severity now | Still present in | Note |
|-------|--------------|------------------|------|
| SH-1 / M-9 | HIGH | `audit.py` | No chained-hash / no signature. File-write access = silent audit edits. |
| SH-2 / M-8 | HIGH | `trust.py` | Plain JSON `0.0–1.0` scores; no signature; file owner is sole gate. |
| SH-3 | HIGH | `identity_resolver.py` | Any `agent_id → URL` allowed; no scheme/host pinning. |
| SH-4 / M-3 | MEDIUM | `commands/send_task.py` | `task_text[:40]` still flows into audit `detail`. Secret detector not invoked. |
| SH-5 / M-7 | MEDIUM | `vault_client.py` | Plaintext `dict`; "mirrors the MCP server" comment still misleading. |
| H-5 | HIGH (latent) | `capabilities.py:_pattern_matches` | Bare-word required-cap edge mostly mitigated by `_CAPABILITY_RE`, but `_pattern_matches` itself still has the silent-grant shape. |
| M-1 / SM-4 | MEDIUM | `inbox_store.py` | No `journal_mode=WAL`, no `busy_timeout`. Concurrent writers OperationalError. |
| M-2 / SM-6 | MEDIUM | `inbox_store.py` | No per-sender row cap or rate limit. Inbox can be filled by a signed low-rep sender. |
| M-4 | MEDIUM | `vault_client.py:52–55` | `pass` branch silently issues a proxy token for a missing service. |
| M-5 | MEDIUM | `vault_client.py` | Expired entries in `_proxies` never evicted. |
| L-4 / SL-2 | LOW | `supply_chain.py` | OSV call has 10s timeout; no retry / circuit breaker. |
| SL-1 | LOW | `vault.ts:98` | Random master key per Node process boot. Fine in-memory; will break the moment on-disk persistence lands. |
| SL-3 | LOW | `vault.ts:80–83` | Redaction reveals the length of the secret. |

### New findings introduced by this RC pass

#### N-1: Daemon advertises subsystems that do not exist — **MEDIUM**
**Files:** `daemon/src/main.rs:64–70`, `daemon/src/ipc/mod.rs:120–127`

The startup banner and the `health` response both report
`subsystems: ["identity", "vault", "trust", "a2a"]`. Only `trust` has code
behind it. The three empty directories (`daemon/src/identity/`,
`daemon/src/vault/`, `daemon/src/a2a_signer/`) make the gap easy to verify.

**Impact:** An operator reading the `health` response over the wire is
misinformed about what the daemon enforces — they may assume identity or
vault gates are running daemon-side when none are. Anyone building a Synapse
Protocol client against the documented surface will write code for
endpoints that will never exist.

**Mitigation:** trim the banner / health response to `["trust"]` until the
other subsystems are implemented, or implement them. Empty directories are
not "Phase C placeholders" — they are a documentation lie.

#### N-2: Capability enforcement compiled but unreachable — **MEDIUM**
**File:** `daemon/src/security/capability.rs`, `daemon/src/ipc/mod.rs`

`CapabilityPolicy` is fully implemented, tested, and exported, but
`daemon/src/ipc/mod.rs::dispatch` does not consult it. Any client that
speaks the Synapse Protocol can call any `TrustOp` without a capability
check. The trust model docs (`docs/TRUST_MODEL.md` § Gate 3) imply the
daemon enforces capabilities.

**Impact:** Today the only client of the daemon is the daemon's own test
suite, so the practical attack surface is zero. But the architecture
**claims** an enforcement gate that does not run. The day a satellite
connects, the gap becomes real and easy to overlook.

**Mitigation:** wire `is_granted(..., required)` into `handle_request` for
each `TrustOp`, or remove the Gate 3 mention from `TRUST_MODEL.md` until it
runs end-to-end.

#### N-3: Daemon trust store is in-memory only — **HIGH**
**File:** `daemon/src/main.rs:28`

`TrustStore::new_in_memory()` opens a SQLite `:memory:` connection. A
daemon restart drops every reputation outcome. The on-disk constructor
`ReputationMemory::open(path)` exists and is implemented but not wired up.
`TRUST_MODEL.md` line 76 says the store is "SQLite-backed"; readers will
interpret this as durable.

**Impact:** in a real deployment, a single `synapsed` crash erases the
sender's history. The reputation gate then defaults every sender back to
the neutral score (`50.0`). An attacker who can OOM the daemon can reset
reputation.

**Mitigation:** read a `SYNAPSE_TRUST_DB` env var (parallel to
`SYNAPSE_SOCKET`), default to a file under `XDG_STATE_HOME`, fall back to
in-memory only when explicitly set. One-line change.

#### N-4: `package.json` workspaces include empty / wrong-language directories — **HIGH for launch readiness, LOW for security**
**File:** `package.json:12–16`

```
"workspaces": [
  "packages/synapse-vault-mcp",
  "packages/synapse-trust-mcp",   ← empty directory
  "packages/synapse-cli"          ← Python package, no package.json
]
```

`npm install` from the repo root will fail. This is not a security finding
in the classical sense, but it forces every first contributor to either
(a) hand-edit `package.json` and submit a PR for the privilege of running
the build, or (b) `cd packages/synapse-vault-mcp && npm install`, missing
the documented workflow. **Either path damages first impressions.**

**Mitigation:** remove the two bad entries, or create matching empty
`package.json` shims. The empty `packages/synapse-trust-mcp/` should be
deleted.

#### N-5: `examples/vps-handoff-no-raw-keys/demo.py` uses an inline simulated vault — **LOW**
**File:** `examples/vps-handoff-no-raw-keys/demo.py:58 onward`

The vps-handoff demo — Synapse's marquee story about secret handoff —
**does not exercise the AES-256-GCM `SecretVault` in `packages/synapse-vault-mcp`**.
It implements a stub in the demo file. A reviewer who reads the demo
carefully will conclude the vault claim is theatre.

**Impact:** narrative risk, not technical. The TS vault is real and tested
in `packages/synapse-vault-mcp/test/vault.test.ts`. The demo just doesn't
use it.

**Mitigation:** rewrite the demo to spawn the MCP server or import
`SecretVault` over an FFI / subprocess shim. Until then, label the demo
honestly: "VPS deploy with a simulated vault — see
`packages/synapse-vault-mcp` for the real cryptographic vault".

#### N-6: `__main__.py` is still a stub — **LAUNCH BLOCKER, not security**
**File:** `packages/synapse-cli/synapse_cli/__main__.py:31, 34`

```python
if args.cmd == "send-task":
    print(f"Stub: would send task {args.task!r} from {args.sender} to {args.target}")
    return 0
```

The published CLI surface prints `"Stub: would send..."` and exits zero.
This was flagged as M-6 in `BUG_REPORT.md` and deferred in
`LAUNCH_BLOCKERS.md` — but the real command logic exists in
`commands/send_task.py` (225 LOC) and `commands/inbox.py` (202 LOC). It
just isn't wired.

**Impact:** a user who pip-installs Synapse, runs `synapse send-task ...`,
and sees `Stub:` will close the tab.

**Mitigation:** wire `__main__.main()` to call into `commands.send_task.send_task`
and `commands.inbox.*`. Estimated effort: under an hour. **This is the
single highest-leverage fix between here and launch.**

---

## Categorised summary

| Severity | Count | Items |
|----------|-------|-------|
| **CRITICAL** | 0 | (closed) |
| **HIGH** | 5 | SH-1, SH-2, SH-3, N-3, H-5 |
| **MEDIUM** | 7 | SH-4, SH-5, N-1, N-2, M-1, M-2, M-4, M-5 |
| **LOW** | 3 | L-4, SL-1, SL-3, N-5 |
| **Launch blocker (not security)** | 2 | N-4, N-6 |

**Net effect on the launch posture:**

`LAUNCH_BLOCKERS.md` currently states "Real blockers: None." That is
**overruled** by this audit on three counts:

1. **N-6** (CLI stub) — published surface does not work.
2. **N-4** (npm workspaces) — first-contributor build path is broken.
3. **N-3** (daemon in-memory) — durability claim in `TRUST_MODEL.md` does not hold.

None of the three is hard to fix. The first two are under an hour. N-3 is a
one-line env-var read plus a default path. After they land, the original
"no real blockers" framing is defensible.
