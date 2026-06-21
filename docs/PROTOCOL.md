<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0. -->

# Daemon Internal IPC Protocol v1.0

> **This document describes the daemon's internal IPC protocol — NOT A2A.**
>
> A2A is the standard cross-agent protocol from [a2aproject.org](https://a2aproject.org), implemented in `packages/synapse-cli/synapse_cli/a2a.py`. Synapse does not fork or reinvent A2A.
>
> The protocol described below is what the Rust daemon (`synapsed`) speaks with local clients over its Unix domain socket. Normative source: `daemon/src/protocol/mod.rs`.

## Envelope

Every message is a `SynapseMessage`:

```json
{
  "id": "uuid-v4",
  "version": "1.0",
  "timestamp": "2026-06-21T00:00:00Z",
  "sender": "agent-id-or-client",
  "caps": ["trust.read", "trust.write"],
  "body": { "...": "tagged union: request | response | event" }
}
```

### Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | UUID v4 |
| `version` | string | yes | Currently `"1.0"`. Unsupported version → `unsupported_version` error |
| `timestamp` | RFC3339 | yes | UTC |
| `sender` | string | yes | Agent id / MCP name / client id |
| `caps` | string[] | no (default `[]`) | Asserted capability set for this request. Empty → all capability-gated ops denied |
| `body` | tagged object | yes | See below |

## Request bodies

| Variant   | Required capability | Meaning |
|-----------|---------------------|---------|
| `ping`    | none                | Liveness check |
| `health`  | none                | Daemon health + active subsystems |
| `trust`   | varies (see below)  | A trust operation |

## Trust operations

| Operation        | Required capability | Fields |
|------------------|---------------------|--------|
| `record_outcome` | `trust.write`       | `agent_id`, `decision_id`, `outcome`, `feedback_source`, `confidence`, `domain` |
| `get_score`      | `trust.read`        | `agent_id`, `domain` |
| `should_trust`   | `trust.read`        | `agent_id`, `domain` |
| `rank_agents`    | `trust.read`        | `domain` |

A request missing the required capability returns `capability_denied`. Wildcard `*` grants everything; `ns.*` grants all `ns.<anything>`. These rules match `daemon/src/security/capability.rs::is_granted`.

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
| `capability_denied`   | Caller's `caps` do not include the required capability |
| `not_implemented`     | Operation not available in this build |

## Example request — get_score with cap

```json
{
  "id": "5d8f...",
  "version": "1.0",
  "timestamp": "2026-06-21T12:00:00Z",
  "sender": "synapse-cli",
  "caps": ["trust.read"],
  "body": {
    "request": {
      "trust": {
        "get_score": { "agent_id": "alice", "domain": "default" }
      }
    }
  }
}
```

## Example error response — missing capability

```json
{
  "id": "5d8f...",
  "version": "1.0",
  "timestamp": "2026-06-21T12:00:00Z",
  "sender": "synapse-daemon",
  "caps": [],
  "body": {
    "response": {
      "error": {
        "code": "capability_denied",
        "message": "capability \"trust.read\" not granted"
      }
    }
  }
}
```

## Versioning

The protocol is versioned by the `version` field. Breaking changes bump the major; additive changes bump the minor. The `caps` field was added at `1.0` with `#[serde(default)]` — older messages that omit it deserialize to `caps: []` and are denied for any capability-gated op (defence in depth).

## Transport

- **Wire format:** line-delimited JSON, one message per line.
- **Underlying transport:** Unix domain socket at `$SYNAPSE_SOCKET` (default `<tmpdir>/synapse.sock`).
- **Concurrency:** each accepted connection runs on its own tokio task, sharing a single `Arc<TrustStore>`.

## What this protocol is **not**

- It is **not A2A.** A2A is JSON-RPC over HTTP between agents on different hosts. This protocol is line-delimited JSON over a local Unix socket between the daemon and its own local clients.
- It is **not** a federation or relay protocol.
- It is **not** the wire format clients send to each other. That's [`packages/synapse-cli/synapse_cli/a2a.py`](../packages/synapse-cli/synapse_cli/a2a.py).
