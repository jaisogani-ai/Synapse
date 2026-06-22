<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# @synapse/memory-mcp

**MCP #1 (spinout / deprecated)** — memory access for any MCP client. Not part of Synapse v0.1.0-alpha — see [`spinout/README.md`](../README.md) for the spinout policy.

 Bridges MCP tool calls to the
Synapse daemon's **8-tier memory** over its Unix socket, speaking Synapse
Protocol v1.0 (kept in lock-step with the Rust daemon).

## Tools

| Tool | Purpose |
|------|---------|
| `memory.read` | Read a key from a tier |
| `memory.write` | Write a value to a tier |
| `memory.search` | Search a tier |
| `memory.ping` | Liveness check |
| `memory.health` | Daemon + memory health |

Set `SYNAPSE_SOCKET` to the daemon socket (default `/tmp/synapse.sock`).

```bash
npm install
npm test         # node --test: protocol + a real unix-socket client test
npm run build    # tsc -> dist/ (publish-ready)
```

> Publish-ready, **not yet published**. The protocol + client core
> (`src/protocol.ts`, `src/client.ts`) is dependency-free and tested against an
> in-process fake socket.

License: Apache 2.0.
