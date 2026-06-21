# Synapse v1 — Security Review

**Date:** 2026-06-20
**Scope:** `vault.py`/`vault.ts`, `identity_resolver.py`, `a2a_signer.py`,
`trust.py`, `audit.py`, `inbox_store.py`, plus `zero_trust.py` and
`capabilities.py` (the primitives those files depend on).

**Method:** Focused review for secret leakage in logs/errors, weak crypto
defaults, injection via task/file fields, and capability bypasses via
crafted requests.

---

## CRITICAL

### SC-1: Replay attack — captured signed payload can be re-sent
**Files:** `a2a_signer.py`, `receiver.py`, `transport.py`

The signature is computed over the JSON-RPC bytes only. No timestamp,
nonce, or session id is bound to the signature. An attacker who captures
one signed `message/send` or `tasks/result` payload can replay it
indefinitely; the `tasks/result` path has no PRIMARY KEY collision
protection at all.

**Impact:** Replay of `tasks/result` from a trusted sender after a real
task was rejected can spoof "completed" status. Replay-pollution of the
audit log makes forensic reconstruction unreliable.

Same as bug C-1.

### SC-2: Malformed JSON-RPC params crash the receiver and leak the
exception text in the 500 response
**File:** `receiver.py`

`{"params": null}` from a signed sender causes `params.get(...)` →
`AttributeError`. The outer handler returns the exception's `str()` in
the body, exposing the internal type and the line/attribute name.

**Impact:** Probe surface for attackers; signed (low-rep, but trusted-
identity) senders can map internal types of the receiver.

Same as bug C-2.

---

## HIGH

### SH-1: `audit.py` is append-only but not tamper-evident
Anyone with file-write access can edit, reorder, or delete entries. The
trust-model documentation promises forensic certainty; this file alone
cannot deliver it.

**Mitigation suggestion:** chained SHA-256 hash per entry, or sign each
entry with the daemon key. Out of scope for the current fix pass.

### SH-2: `trust.json` is unauthenticated plaintext
Anyone with file-write access can rewrite reputation scores, promoting
an attacker-controlled agent above the trust threshold. The score store
trusts the JSON file completely.

**Mitigation suggestion:** sign the trust file with the daemon key, OR
require the daemon to be the sole writer via Unix-socket RPC.

### SH-3: `IdentityResolver` accepts any URL with no scheme/host pinning
A modified `identity.json` can re-point a known agent_id to
`http://attacker.example.com/a2a`. Outbound `send_task` will then post
the signed payload (containing the bearer token) to the attacker.

**Mitigation:** pin allowed schemes (http/https), reject loopback-only
in production, or store hash-pinned endpoint fingerprints.

### SH-4: `task_text` first 40 chars logged to audit verbatim
If a sender wrote `"deploy with sk-ant-api03-LIVE-KEY..."`, the prefix
including the credential start is now in the audit log. The
secret-detector is not invoked on audit detail strings.

### SH-5: `vault_client.py` stores secrets as plaintext in a Python dict
The class is documented as "mirrors the MCP server" but is missing the
AES-256-GCM encryption-at-rest the TS vault provides. Anyone who can
core-dump the process can read every secret.

### SH-6: `verify_request` can crash on a token with malformed `caps`
`CapabilitySet.of` raises `CapabilityError` if any cap string fails the
regex. Not caught. A captured token replayed against a stricter capability
schema would crash the verifier.

Same as bug H-2.

---

## MEDIUM

### SM-1: File upload has no size limit (DoS)
`send_task` reads entire file into memory; receiver's `do_POST` does
`self.rfile.read(length)` where `length` is the client-controlled
`Content-Length`. A 4 GB POST OOMs the receiver.

### SM-2: `transport.post_jsonrpc` follows redirects by default
`urllib.request.urlopen` follows 3xx redirects without consulting the
identity resolver. A compromised endpoint can redirect to anywhere.

### SM-3: `receiver.do_POST` does not enforce `Content-Length` upper bound
Same root as SM-1 from the receiver side. Should hard-cap inbound body.

### SM-4: `inbox_store.py` SQLite has no `journal_mode=WAL` / busy timeout
Concurrent writes throw `OperationalError: database is locked` rather
than retrying.

### SM-5: `audit.read_all` crashes on a partial last line
Same as bug H-3. Forensic tools that tail the audit file will die on the
first interrupted write.

### SM-6: `inbox` has no row cap or rate limit per sender
A signed sender can spam tasks until disk fills.

---

## LOW

### SL-1: Per-process master key in `vault.ts`
If no key is provided, a random key is generated each boot. Restart →
all stored secrets unrecoverable. Acceptable while the store is in-mem;
worth flagging before any disk persistence lands.

### SL-2: `urllib.request.urlopen` calls have no proxy/SSRF mitigation
`supply_chain.py` calls OSV.dev. If the URL were attacker-controlled it
could SSRF. It is not — `OSV_QUERY_URL` is a module constant. Safe as-is,
but the helper `_default_fetcher` exposes the pattern.

### SL-3: `redact()` in `vault.ts` reveals length
`{secret.slice(0, 4)}…[redacted:N chars]` discloses the length, which
narrows brute-force search space. Minor.

### SL-4: `random` not used; `secrets`/`randomBytes` used throughout
Confirmed clean. (Listed only to record the positive finding.)
