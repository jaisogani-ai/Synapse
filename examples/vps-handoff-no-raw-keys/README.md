<!-- SPDX-License-Identifier: Apache-2.0 -->

# Demo 1 — VPS deploy with no raw credentials

> **What it shows.** Codex on a VPS deploys an app using an Anthropic API key. The key never leaves the laptop's vault. The VPS sees only a 300-second proxy URL. Drives the real Node `SecretVault` (AES-256-GCM) — not an in-process simulation.

## What you'll see

```
══════════════════════════════════════════════════════════════════
  SYNAPSE V1 — VPS HANDOFF DEMO
  Codex on VPS deploys. Never sees the real credential.
  Driving the REAL AES-256-GCM SecretVault (Node bridge)
══════════════════════════════════════════════════════════════════

┌─ STEP 1: LAPTOP STORES API KEY IN REAL AES-256-GCM VAULT
│  🔑 Real API key: sk-a…[redacted:63 chars]
│  ✓ Encrypted at rest with AES-256-GCM (real Node SecretVault)
│
┌─ STEP 2: VPS CODEX REGISTERS AGENT IDENTITY
│  ✓ Identity issued: codex-vps-deploy-01
│  ✓ 🛡️ HMAC signing key provisioned
│
┌─ STEP 3: VPS REQUESTS SCOPED CREDENTIAL PROXY (TTL=300s)
│  ✓ Proxy issued: synapse+vault://proxy/…
│  ⚠ Agent receives ONLY the proxy URL. Never the raw key.
│
┌─ STEP 4: DEPLOY RUNS VIA PROXY
│  ✓ Daemon resolved proxy → secret (length 63 chars)
│  ✓ 🚀 Deploy succeeded! Agent used proxy, never raw key.
│
┌─ STEP 5: AUDIT LOG (FROM REAL VAULT) — ZERO RAW KEY EXPOSURE
│    2026-06-21T...  store           anthropic-api
│    2026-06-21T...  issue_proxy     anthropic-api  (production deploy via codex)
│    2026-06-21T...  resolve_proxy   anthropic-api
│  ✓ 🛡️ ZERO raw key exposure in audit log
│  ✓ No 'retrieve' actions — agent never touched the real key

══════════════════════════════════════════════════════════════════
  RESULT: PASS
══════════════════════════════════════════════════════════════════
```

## Architecture sketch

```
   ┌──────────────────────────────┐
   │      LAPTOP (operator)       │
   │                              │
   │  AES-256-GCM SecretVault     │ ◀──── raw key lives here
   │   • store(anthropic-api)     │       and never leaves
   │   • issue_proxy(service,     │
   │       purpose, ttl=300)      │
   │   • resolve_proxy(token)     │ ──┐
   └────────────┬─────────────────┘   │   (daemon-side only —
                │                     │    invisible to the agent)
       proxy URL only                 │
                ▼                     │
   ┌──────────────────────────────┐   │
   │   VPS — Codex adapter        │   │
   │                              │   │
   │   • Signed deploy request    │   │
   │     X-Synapse-Agent          │   │
   │     X-Synapse-Signature      │   │
   │     X-Synapse-Token          │   │
   │     X-Synapse-Tool=codex     │   │
   │   • Holds proxy URL,         │   │
   │     not the raw secret       │   │
   └────────────┬─────────────────┘   │
                │                     │
                ▼                     │
   Daemon resolves proxy ─────────────┘
   Calls api.anthropic.com on behalf of agent
```

## Run

```bash
# from repo root
python3.11 examples/vps-handoff-no-raw-keys/demo.py
```

Exit code 0 on success. Re-runnable; the demo cleans up after itself.

## Prereqs

The demo drives the real vault via a Node bridge. If you haven't already:

```bash
npm install
npm --workspace @synapse/secret-vault-mcp run build
```

Without the build, the demo fails fast with a clear error.

## Recording instructions

```bash
# VHS (https://github.com/charmbracelet/vhs) — config tracked at demo.tape
vhs examples/vps-handoff-no-raw-keys/demo.tape   # writes assets/demo.gif

# asciinema + agg
asciinema rec --command "python3.11 examples/vps-handoff-no-raw-keys/demo.py" /tmp/demo.cast
agg /tmp/demo.cast assets/demo-deploy.gif
```

Place the recording at `assets/demo-deploy.gif`. The README references it.

## Why this proves what it proves

- The vault that runs is the same `SecretVault` class in `packages/synapse-vault-mcp/src/vault.ts` that the production MCP would expose. **No alternative implementation.**
- The Python demo speaks to that vault over a stdin/stdout JSON bridge — a thin transport, not a re-implementation.
- The proxy resolves to the actual stored ciphertext, which is decrypted by GCM with the per-vault master key. The demo asserts `resolved == real_api_key` to prove the encrypt → decrypt round-trip ran end-to-end.
- `vault.audit_log()` returns entries directly from the Node process. No `retrieve` action appears — only `store`, `issue_proxy`, `resolve_proxy` — proving the raw value never went through the `retrieve()` code path that an exfiltration attempt would need.
