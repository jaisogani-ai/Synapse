<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# @synapse/context-mcp

**MCP #3** — context optimization as infrastructure. Compress, dedupe, and
summarize conversation history so agents stay under the context wall.

## Tools

| Tool | Purpose |
|------|---------|
| `context.compress` | Compress history toward a token budget (4 strategies) |
| `context.dedupe` | Remove duplicate / near-duplicate lines (Jaccard) |
| `context.summarize_for_handoff` | Tight agent-to-agent handoff summary |
| `context.share_summary` | Push a summary into shared memory (team/project/global) |
| `context.evict` | Evict stale/low-importance items (lru/importance/age) |

```bash
npm install
npm test         # node --test on the TS core (no build needed)
npm run build    # tsc -> dist/ (publish-ready)
```

> Publish-ready, **not yet published**. Core (`src/context.ts`) is
> dependency-free and unit-tested.

License: Apache 2.0.
