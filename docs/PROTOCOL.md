<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Synapse Protocol v1.0

> The normative source is `daemon/src/protocol/mod.rs`.

The Synapse Protocol is the line-delimited JSON message format spoken between
the daemon and every satellite (adapters, MCP servers, clients) over a local
Unix socket.

## Envelope

Every message is a `SynapseMessage`:

```json
{
  "id": "uuid-v4",
  "version": "1.0",
  "timestamp": "2026-06-17T00:00:00Z",
  "sender": "agent-id-or-client",
  "body": { "...": "tagged union: request | response | event" }
}
```

## Request bodies

| Variant   | Meaning                                          |
|-----------|--------------------------------------------------|
| `ping`    | Liveness check                                   |
| `health`  | Daemon health + active subsystems                |
| `trust`   | A trust operation (see below)                    |

## Trust operations

| Operation        | Fields                                                              |
|------------------|---------------------------------------------------------------------|
| `record_outcome` | `agent_id`, `decision_id`, `outcome`, `feedback_source`, `confidence`, `domain` |
| `get_score`      | `agent_id`, `domain`                                                |
| `should_trust`   | `agent_id`, `domain`                                                |
| `rank_agents`    | `domain`                                                            |

## Response bodies

| Variant   | Meaning                          |
|-----------|----------------------------------|
| `pong`    | Reply to `ping`                  |
| `ok`      | Operation succeeded (no payload) |
| `data`    | Operation succeeded with payload |
| `error`   | `{ code, message }`              |

## Error codes

| Code                  | Meaning                              |
|-----------------------|--------------------------------------|
| `bad_request`         | Unparseable message                  |
| `unsupported_version` | Protocol version mismatch            |
| `trust_error`         | Trust operation failed               |
| `not_implemented`     | Operation not available in this phase|

## Versioning

The protocol is versioned by the `version` field. Breaking changes bump
the major; additive changes bump the minor. Current version: `"1.0"`.
