# Synapse v1 — Full Bug Report (Phase A delayed audit)

**Date:** 2026-06-20
**Scope:** `daemon/`, `packages/`, `examples/` — all files
**Method:** Manual inspection focused on race conditions, replay attacks,
trust bypasses, vault edge cases, serialization safety, dead code.

---

## CRITICAL

### C-1: Signed A2A payload is replayable
**Files:** `packages/synapse-cli/synapse_cli/a2a_signer.py`,
`packages/synapse-cli/synapse_cli/receiver.py`,
`packages/synapse-cli/synapse_cli/transport.py`

The HMAC signature is computed over the JSON-RPC payload bytes only. No
nonce, timestamp, or sequence number is included in the signed material.

An MITM that captures one signed message can re-send it byte-for-byte and
the receiver will:
- For `tasks/result`: silently re-update the inbox row to "completed" and
  append another `receive_result` audit entry (idempotent state, but the
  audit log can be polluted indefinitely).
- For `message/send`: the second insert hits the `task_id` PRIMARY KEY
  uniqueness constraint and SQLite raises `IntegrityError`. This is not
  caught — it propagates to the HTTP layer which returns a 500 with the
  raw exception message. There is NO `reject_replay` audit entry.

The PRIMARY KEY collision provides accidental, partial mitigation but
neither replay-rejects cleanly nor protects the `tasks/result` and
`tasks/get` methods.

### C-2: `{"params": null}` or `{"params": <non-dict>}` crashes the receiver
**File:** `packages/synapse-cli/synapse_cli/receiver.py`

`handle_request` does `params = request.get("params", {})` then passes
`params` to `_handle_message_send` / `_handle_tasks_get` /
`_handle_tasks_result`. Each calls `params.get(...)`. If a signed sender
sends `{"params": null}`, `request.get("params", {})` returns `None` (not
`{}`), and `None.get(...)` raises `AttributeError`. Same applies to
`{"params": []}` or `{"params": "string"}`.

The outer `do_POST` exception handler catches it but returns a 500
response containing the raw exception text (information disclosure). No
clean `reject_malformed` audit entry is logged. The receiver process
stays up, but each malformed signed message is a free probe.

Lines `82` (`task = params.get("task") or {}`), `121`
(`task_id = params.get("id", "")`), `134` (`task_id = params.get("taskId", "")`)
all break with the same root cause.

---

## HIGH

### H-1: SQLite IntegrityError on duplicate `task_id` is unhandled
**File:** `packages/synapse-cli/synapse_cli/inbox_store.py`

`InboxStore.insert` uses a positional `INSERT INTO inbox VALUES (...)`.
The `task_id` column is the PRIMARY KEY. A replay (see C-1) raises
`sqlite3.IntegrityError`. This propagates out of `_handle_message_send`
through `handle_request` to `do_POST`'s blanket `except Exception` and
yields a 500. There is no `audit("reject_replay", ...)` entry.

### H-2: Capability validation inside JWT decode can crash `verify_request`
**File:** `packages/synapse-core/synapse/security/zero_trust.py`

`verify_request` calls `CapabilitySet.of(*claims.caps)`. `CapabilitySet.of`
runs `validate(name)` over every cap string, raising
`CapabilityError` (a `ValueError`) on malformed caps. The exception is
not caught. Although the daemon issues caps, any subsystem replaying
captured tokens or a misconfigured caller can crash the verifier.

### H-3: `audit.read_all()` raises uncaught `JSONDecodeError` on a partial line
**File:** `packages/synapse-cli/synapse_cli/audit.py`

`read_all` calls `json.loads(line)` per line with no try/except. If a
write is interrupted (`SIGKILL`, full disk), a partial line remains. The
next reader crashes instead of skipping the bad line and continuing.
Audit reads are used by the cross-device demo's "wait for result" loop —
a corrupted audit file kills the loop.

### H-4: `send_task` reads attached file with no size limit
**File:** `packages/synapse-cli/synapse_cli/commands/send_task.py`

`opts.file_path.read_bytes()` reads the entire file into memory and
base64-encodes it into a `FilePart`. A 4 GB file becomes a ~5.5 GB
in-memory payload, then a 5.5 GB HTTP POST. The receiver also reads the
entire body into RAM (`body = self.rfile.read(length)`). Either side
OOMs trivially.

### H-5: Capability bypass via shorthand wildcard mismatch
**File:** `packages/synapse-core/synapse/security/capabilities.py`

`_pattern_matches` does
`required.split(".", 1)[0] == namespace` for `granted.endswith(".*")`.
A required capability with no `.` (single word, e.g. `"admin"`) matches
*any* granted `"x.*"` whose `x` happens to equal `"admin"`. This is an
unusual edge — required capabilities are validated to require a `.` (see
`_CAPABILITY_RE`). Still, if a future caller passes an unvalidated
required capability string, the wildcard match silently grants. **Low
exploitability today; HIGH due to "silent grant" risk.**

---

## MEDIUM

### M-1: SQLite write-lock contention is not retried
`InboxStore` opens a fresh `sqlite3.Connection` per operation. Concurrent
INSERTs from multiple receiver threads can yield "database is locked".
Not retried; the request errors out.

### M-2: Inbox has no row cap
A signed low-rep sender can spam thousands of pending tasks. The inbox
grows unbounded.

### M-3: `task_text[:40]` leaks into audit log
`send_task.py` writes the first 40 chars of `task_text` to the audit
log's `detail` field. If the text contains a credential prefix (e.g.
`"deploy with sk-ant-..."`), the prefix lands in plaintext audit.

### M-4: `vault_client.request_proxy` issues tokens for missing services
The `pass` branch at lines 52–55 silently issues a proxy token whose
service has no stored secret. `resolve()` will later return `None` for
it. Caller gets a useless proxy with no error.

### M-5: Stale proxy tokens accumulate in `vault_client._proxies`
Expired entries are never evicted. Long-running process leaks memory.

### M-6: `__main__.py` is a stub
`packages/synapse-cli/synapse_cli/__main__.py` calls neither
`send_task()` nor the inbox helpers. The published CLI surface does
nothing. The actual CLI logic lives in `commands/` but isn't wired up.

### M-7: `vault_client.py` stores secrets in process-memory plaintext
The class comment says "mirrors the MCP server" — misleading. The TS
vault is AES-256-GCM at rest; this Python mirror is plain `dict`.
Acceptable for CLI tests; misleading for production.

### M-8: Trust scores stored in plain JSON with default file perms
`trust.json` is writable by anyone with file access. There is no integrity
check. Editing the file silently promotes an agent.

### M-9: Audit log is not tamper-evident
The JSONL audit log has no chained hashes or signatures. An attacker who
can write to the file can backdate entries or delete rejections.

---

## LOW

### L-1: Leftover "T8 reputation memory" comment in `daemon/src/trust/reputation.rs:77`
Cosmetic remnant of the 8-tier-memory architecture. Nothing else
references tiers in the active code.

### L-2: `field` imported but unused in `audit.py`
Minor lint.

### L-3: `FilePart.bytes` shadows the built-in `bytes`
Matches the A2A spec field name, so intentional, but a linter will flag.

### L-4: `urlopen` in `supply_chain.py` has no retry / circuit breaker
Single-shot 10s timeout against OSV.dev. Network blips fail the scan
permanently for that call.

### L-5: `IdentityResolver` reads JSON with no schema validation
A malformed file gives a confusing `KeyError` instead of a clean error.

### L-6: Tests do not exercise high-load concurrent inbox writes
Coverage gap. The Phase C-extra test only spins up 2 processes
sequentially.
