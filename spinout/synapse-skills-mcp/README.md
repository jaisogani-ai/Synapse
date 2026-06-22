<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# @synapse/skills-mcp

**MCP #2 (spinout / deprecated)** — skill registry + invocation. Not part of Synapse v0.1.0-alpha — see [`spinout/README.md`](../README.md) for the spinout policy.

 Exposes Synapse's portable
SKILL.md-style skills as MCP tools so any MCP client (Claude Code, Cursor, …)
can list, search, and run them.

## Tools

| Tool | Purpose |
|------|---------|
| `skills.list` | List every registered skill |
| `skills.search` | Free-text search by id/name/description/tags |
| `skills.get` | Read one skill's metadata |
| `skills.invoke` | Run a skill with structured input |
| `skills.register` | Add a new skill at runtime |

## Built-in skills

`text.slugify`, `text.title_case`, `text.word_count`, `json.format`,
`shell.exec` (sandbox-only). Each is a real handler with tests, not a stub.

Skills declaring `requiresSandbox: true` are refused in-process — they must
route through the daemon's [agent sandbox](../../daemon/src/security/sandbox.rs).

```bash
npm install
npm test         # node --test (no build needed)
npm run build    # tsc -> dist/ (publish-ready)
```

License: Apache 2.0.
