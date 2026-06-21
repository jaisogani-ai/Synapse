# GITHUB_REVIEW

**Date:** 2026-06-21
**Frame:** What does the front page of Hacker News / r/rust / r/programming /
r/netsec / Lobsters do with this on launch day? What does a Rust engineer who
opens `cargo doc` see? What does a security engineer who skims the trust model
see?

This is the brutal version. Things that look good are listed honestly; things
that will get attacked are listed without hedging.

---

## 1. What they will praise

### 1a. The framing
> *Your AI agents can already talk to each other. They have no idea who they're talking to.*

This lands. It is concrete, it names a real problem (A2A doesn't authenticate),
and it doesn't oversell. **HN comments will quote this line.** The four-pillar
table that follows is dense, scannable, and links each pillar to a file path —
that's exactly the form a working engineer wants to see.

### 1b. The Rust daemon is small and tidy
1,544 LOC. Two thirds of it is well-tested. `protocol/mod.rs` has clean serde
tagged unions and 5 round-trip tests. `trust/reputation.rs` has a clear data
model (confidence-weighted), a sensible default (`NEUTRAL_SCORE = 50.0`), and 7
focused tests. The capability module has 7 more.

Rust engineers will look at this and see **a thing they would actually want to
read.** No `unsafe`. No giant module. No bespoke async machinery — tokio
straight from the toolbox. `thiserror` for module errors, `anyhow` for the
binary, `tracing` for logs. Idiomatic.

### 1c. Zero-dep crypto where it matters
`zero_trust.py` does HS256 + HMAC using only `hmac` + `hashlib` + `base64` from
the Python standard library. No PyJWT, no `cryptography` dependency. The
docstring even tells you why: "vetted library (PyJWT) can be swapped in later".
**This is exactly the kind of choice that gets praised**: small surface, easy
to audit, no supply-chain exposure for the most security-sensitive primitive
in the system.

Same story for `vault.ts`: only `node:crypto`, AES-256-GCM with explicit IV
and auth tag handling. Reviewers will read this in 30 seconds and approve.

### 1d. Capability system shape
Capsicum-style namespaced capabilities (`vault.request_credential`,
`trust.read`) with wildcards (`vault.*`). The registry in `capabilities.py`
labels each capability with a risk level (`low/medium/high`). This is the
kind of detail security folks ask for and rarely see in agent infra.

### 1e. Honest non-goals
`docs/ROADMAP.md` "Non-Goals" section says outright: not an agent framework,
not a replacement for A2A, not a model router, not memory management.
**This will be praised.** Most projects in this space oversell scope. Synapse
draws the line.

### 1f. The audit transparency
The repo ships `BUG_REPORT.md`, `SECURITY_REVIEW.md`, `LAUNCH_BLOCKERS.md`
at the root. **Shipping your own bug report is a power move.** Done right,
it earns trust faster than any marketing line. (See § 2d for the failure
mode.)

### 1g. Apache-2.0 + clean NOTICE + per-file headers
80+ source files all have SPDX headers. The NOTICE file is correctly scoped.
The licence is unmodified standard text. **No Commons Clause, no "free for
non-commercial" trap.** This is the bar for serious OSS and Synapse clears it.

### 1h. Inspirations doc
`docs/INSPIRATIONS.md` is curated, not name-dropped. SSH, JWT, eBay seller
ratings, Certificate Transparency, Capsicum, HashiCorp Vault, A2A, Zero Trust
NIST SP 800-207. Every reference is functional, not aesthetic. This will be
read.

---

## 2. What they will attack

### 2a. "Phase D (complete)" but the CLI prints "Stub:"

Top comment on HN, day one:

> *Tried `synapse send-task`. It prints "Stub: would send task..." and exits.
> "Phase D complete" my left foot.*

`packages/synapse-cli/synapse_cli/__main__.py:31`. The real `send_task.py`
implementation exists in `commands/`, ~225 lines of working code, just not
wired. **Brutal because it's true and it's a one-hour fix.** See `RELEASE_SCORE.md`
launch blockers.

### 2b. The Rust daemon's `health` response lies

`{"subsystems": ["identity", "vault", "trust", "a2a"]}` — but three of those
directories are empty. Anyone running `nc -U /tmp/synapse.sock` and sending
a `health` request will see this. **The subsequent comment thread will
write itself.**

### 2c. The npm workspace is broken

```bash
git clone … && cd synapse && npm install
# npm error code ENOENT
# npm error workspace synapse-trust-mcp not found
```

That's the first command in the README's TypeScript build path. The fix is
deleting two lines from `package.json`. **The PR will exist within 24 hours
of launch.** It might be a good first PR; it is also a bad first impression.

### 2d. The vps-handoff demo doesn't use the real vault

The flagship demo of "VPS deploy with no raw credentials" implements a
simulated vault inline. The real AES-256-GCM `SecretVault` in
`packages/synapse-vault-mcp/src/vault.ts` is never spawned. Someone will
notice (likely via `grep -r 'class SecretVault' examples/`). The framing on
HN will be:

> *The demo that proves the marquee claim doesn't actually use the marquee
> code.*

Painful. Same shape as 2a: easy fix (rewrite the demo to subprocess the MCP
server) and the broken state damages credibility disproportionately.

### 2e. The "5 adapters" are one adapter labelled five ways

A reviewer who opens `packages/adapters/claude_code/__init__.py` finds
**24 lines** that set `tool_type = "claude-code"` and inherit from
`BaseAdapter`. Same for the other four. Adapters that look distinct in the
README turn out to be a single common path. The right framing is "one
adapter that can label itself" — and that's defensible. The current framing
overstates.

### 2f. Two trust stores, two identity stores

A security engineer who reads carefully finds:

- `daemon/src/trust/reputation.rs` — Rust, SQLite, score `0..=100`
- `packages/synapse-cli/synapse_cli/trust.py` — Python, JSON file, score `0.0..=1.0`

These are **not synchronised**, they use **different scales**, and the
daemon's store is **in-memory only**. The trust-model doc treats them as
one. Expect a comment like:

> *Which one is the source of truth? Why does the JSON one have no signature
> and the daemon one no persistence?*

Same story for identity: `ZeroTrustNetwork._secrets: dict[str, bytes]` per
process. No daemon-side identity registry.

### 2g. Spinout is 3,400 LOC of unrelated stuff

`spinout/` carries 6 mature-looking subprojects — memory MCP, context MCP,
skills MCP, backend-architect MCP, router, india-compliance worker. Total
~3,400 LOC. The README mentions it as "out of scope for v1". A reviewer will
ask:

> *Why is it in the repo, then? It bloats `git clone`. It dilutes the
> identity/trust story. Half of it looks like a separate project entirely.*

The cleanest answer is "we will move these out before launch, so please
ignore". The current answer ("they could be their own repos") is not
strong enough.

### 2h. The "T8 reputation memory" comment

`daemon/src/trust/reputation.rs:77`:

```rust
/// T8 reputation memory backed by SQLite.
```

Cosmetic leftover from the v0 8-tier memory architecture. Mentioned in
`BUG_REPORT.md` (L-1), still in the source. Anyone curious enough to grep
for `T8` will find it; combined with 2g, it confirms the impression that
the repo is mid-refactor.

### 2i. JSON-RPC error text leakage was fixed, but the new error is opaque

`transport.py:154–163` now returns `{"error": {"code": -32000, "message": "internal error"}, "id": null}` for any unhandled exception. Reviewers will
say:

> *Good for the wire. But now the operator has no traceback. Where do the
> tracebacks go?*

The answer is "stderr of the receiver process". Some won't think that's
enough. (Pragmatic, but document it.)

### 2j. The daemon uses tokio + a `Mutex<Connection>` for SQLite

`daemon/src/trust/reputation.rs:80` uses `std::sync::Mutex` around a
synchronous `rusqlite::Connection` inside a tokio runtime. Comment in the
docstring acknowledges "long-term these calls move to `spawn_blocking`".
Rust async folks will point out that a blocking lock inside an async task
**stalls the executor**. Today, with one client, fine. With concurrent
clients, the daemon serialises. **Expect a comment from someone with a
strong opinion about `tokio::sync::Mutex` vs `spawn_blocking` vs `r2d2`.**

### 2k. Default model line is jarring

`daemon/src/protocol/mod.rs:31`:

```rust
pub const DEFAULT_MODEL: &str = "claude-opus-4-8";
```

In a protocol module. Reviewer reaction:

> *Why does the wire protocol know about a Claude model? Wrong layer.*

Probably true. The constant is unused outside `health`, and putting it in
protocol is a layering smell.

### 2l. Architecture diagram in README shows only the daemon

```
┌──────────────────────────────────────────┐
│            SYNAPSE DAEMON (Rust)          │
│  ...                                     │
└──────────────────────────────────────────┘
```

But most of the v1 functionality is in Python and TypeScript outside the
daemon. The diagram understates by ~6,000 LOC and overstates the daemon's
role. (Fixed in `README_REWRITE.md`.)

---

## 3. What looks original

### Genuinely fresh framings

- **"Your AI agents can already talk to each other. They have no idea who
  they're talking to."** The problem statement maps to a real gap nobody
  has named cleanly yet. A2A defines the envelope and *deliberately* leaves
  identity/auth open. Synapse names the gap as a product category. **This
  is the most original thing in the repo.**

- **Reputation as a primitive for agent infra.** eBay-style scoring applied
  to non-human actors. The literature on agent trust exists, but a working
  open-source implementation that ships with three demos does not. *Worth
  the post.*

- **Vault proxy URLs as the credential-handoff primitive.** `synapse+vault://proxy/<token>`.
  Conceptually simple, sells the no-raw-keys story in one sentence. The TS
  vault implements it correctly. (See 2d — but the *primitive* is fresh.)

- **Three-gate framing (signature → reputation → capability).** It's not
  novel cryptography; it's a well-named user-facing model that maps to
  three real verification steps. Diagrams will get reused.

### Not original on their own, but well-composed

- HMAC + HS256 JWT + 15-minute TTL is textbook. The 5-minute payload
  freshness window on top of the JWT TTL is a sensible double-belt.
- AES-256-GCM secret storage with proxy tokens is HashiCorp Vault's
  pattern, openly cited in `INSPIRATIONS.md`. Not new — but well-executed
  in 230 lines of dep-free TS.
- OSV.dev + Shannon entropy supply-chain scan is a standard combo. The
  fact that the network call is injectable for offline tests is the
  small thing that makes it actually usable.

---

## 4. What looks derivative

- **The 4-pillar "Identity / Vault / Trust / A2A Integration" framing**
  echoes the AWS IAM "users / roles / policies" decomposition. Functional,
  but not original.
- **The Microkernel / sidecar framing** in `INSPIRATIONS.md` is borrowed
  language; today the architecture is closer to a library set than a
  microkernel (see § 2l). The framing is aspirational, not yet earned.
- **`secret_detector.py` 140+ patterns** looks like a port of
  trufflehog/gitleaks regex packs. Reviewer will check this. It is fine
  to mirror well-known patterns, but the doc should cite the prior art.
- **Spinout MCPs** (memory, context, skills) borrow heavily from the wider
  MCP ecosystem. Their `spinout/` placement is the right move; **do not
  let them creep into the README narrative.**

---

## 5. What is unclear (to a reviewer, on first read)

These are the questions a reader will form silently and never ask. Closing
them in docs gets people from "interesting" to "I trust this".

- **"Where does the daemon get its initial agent identities? How does an
  adapter on another machine prove it owns an agent_id?"** Answer: today
  the host process is the source of truth, and cross-host verification only
  works because demos share a `ZeroTrustNetwork`. Document this honestly.
- **"Does the Rust daemon participate in A2A signing?"** Answer: no. The
  daemon owns the Synapse Protocol; A2A signing is Python. README and
  ARCHITECTURE.md currently obscure this.
- **"What's the failure mode when the vault MCP isn't running?"** Answer:
  `vault_client.py:52–55` silently issues a proxy that will later resolve
  to `None`. Document or fix.
- **"How do I authenticate to the daemon over the Unix socket?"** Answer:
  filesystem permissions on the socket — which means whoever can read/write
  the socket can call any `TrustOp` unauthenticated. This is fine for a
  single-operator setup; document the assumption.
- **"What is `spinout/` for? Why is it in the repo?"** Answer: v0 code with
  standalone value. *Move it out* or *spell out the timeline*.

---

## 6. The single highest-leverage thing to do before launch

Wire `__main__.py` to the real `send_task` / `inbox` code. One hour. It
closes attack 2a entirely. Without it, every other strength gets read
through the lens of "but the CLI prints `Stub:`".

Then delete the empty `packages/synapse-trust-mcp/` and the broken workspace
entries. One minute. Closes 2c.

Then add one sentence to the vps-handoff demo's README acknowledging the
simulated vault and pointing to the real one. Five minutes. Closes 2d.

In ~75 minutes you can turn the top three attack surfaces into non-issues.
That changes the launch from "interesting but rough" to "interesting and
tight". Worth doing.
