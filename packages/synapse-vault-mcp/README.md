<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# @synapse/secret-vault-mcp

**MCP #4** — the secret vault. Solves the #1 unsolved problem (29M secrets
leaked from AI tools in 2025): agents **never see raw API keys**. They request a
scoped, time-limited *credential proxy*; only the daemon resolves it.

- 🔐 AES-256-GCM encryption at rest (authenticated — tampering is detected)
- 🎟️ credential proxies (max 1h), not raw keys
- ♻️ rotation with a grace window
- 🧾 append-only audit log (values never logged)
- 🔎 pre-commit secret-exposure detection

## Tools

| Tool | Purpose |
|------|---------|
| `vault.store_secret` | Store a secret (encrypted at rest) |
| `vault.request_credential` | Get a scoped, time-limited proxy |
| `vault.rotate` | Rotate a secret with a grace window |
| `vault.audit_log` | Read a secret's access log |
| `vault.detect_exposure` | Scan content for leaked secrets |
| `vault.revoke` | Immediately revoke a secret |

## Develop

```bash
npm install      # installs @modelcontextprotocol/sdk + zod
npm test         # node --test on the TS core (no build needed)
npm run build    # tsc -> dist/ (publish-ready)
```

> Publish-ready, **not yet published**. The crypto core (`src/vault.ts`) is
> dependency-free and fully unit-tested with Node's built-in test runner.

License: Apache 2.0.
