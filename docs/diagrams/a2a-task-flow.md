<!-- SPDX-License-Identifier: Apache-2.0 -->

# A2A task flow

> Source: `packages/synapse-cli/synapse_cli/commands/send_task.py`, `transport.py`, `receiver.py`, `outbox_store.py`, `outbox_worker.py`, `inbox_store.py`, `commands/inbox.py`.

```mermaid
flowchart TB
    SEND[/"synapse send-task<br/>--from alice --to bob"/]
    RESOLVE{"resolver.resolve(bob)<br/>known endpoint?"}
    UNKNOWN["return: unknown agent<br/>(audit: send_task_failed)"]
    PRESENCE{"GET endpoint/presence<br/>reachable?"}
    BUILD[/"build A2A Task<br/>+ TextPart / FilePart<br/>+ vault proxy if cred-touching"/]
    SIGN[/"HMAC sign payload + ts<br/>issue JWT with a2a.* caps"/]
    ENQUEUE[("outbox.db<br/>state=queued<br/>attempts=0")]
    POST[/"POST /a2a<br/>X-A2A-{Sender,Sig,TS,Token}"/]
    WORKER["OutboxWorker.tick()<br/>backoff 5s,30s,3m,15m,1h,6h"]
    DEAD[("outbox.db<br/>state=dead<br/>after MAX_ATTEMPTS")]

    SEND --> RESOLVE
    RESOLVE -- no --> UNKNOWN
    RESOLVE -- yes --> PRESENCE
    PRESENCE -- offline --> BUILD
    PRESENCE -- online --> BUILD
    BUILD --> SIGN
    SIGN -- target offline --> ENQUEUE
    ENQUEUE --> WORKER
    WORKER -- success --> POST
    WORKER -- max retries --> DEAD
    SIGN -- target online --> POST

    POST --> RECV[/"receiver.handle_request"/]
    RECV --> G1{"Gate 1<br/>HMAC + ts valid?"}
    G1 -- no --> R1["audit: reject_unsigned<br/>HTTP 200 + JSON-RPC error"]
    G1 -- yes --> G3{"Gate 3<br/>token cap covers method?"}
    G3 -- no --> R3["audit: reject_capability<br/>HTTP 200 + JSON-RPC error"]
    G3 -- yes --> INSERT[("inbox.db<br/>insert task_id<br/>PK = task_id<br/>(replay detected)")]
    INSERT --> AUDIT["audit: receive_task<br/>with sender score"]
    AUDIT --> WAIT[/"task pending in inbox<br/>wait for operator"/]

    WAIT --> REVIEW[/"synapse inbox review &lt;id&gt;"/]
    REVIEW --> CHOOSE{accept or reject?}
    CHOOSE -- accept --> ACCEPT[/"synapse inbox accept &lt;id&gt;<br/>send tasks/result back"/]
    CHOOSE -- reject --> REJECT[/"synapse inbox reject &lt;id&gt;<br/>audit: reject_task"/]
    ACCEPT --> RESULT[("sender receives result<br/>audit: receive_result")]

    style SEND fill:#e8f4ff
    style POST fill:#fff5e6
    style RECV fill:#f0ffe6
    style ENQUEUE fill:#f8e8e8
    style DEAD fill:#ffe8e8
    style RESULT fill:#e8ffe8
```

## What lives where

| State | Storage | Lifetime |
|---|---|---|
| Outbox row | `outbox.db` (SQLite WAL) | Until `purge_sent` or `state=dead` cleared by operator |
| Inbox row | `inbox.db` (SQLite) | Until operator's `accept` / `reject` (then `status` updated; row remains for audit) |
| Audit entries | `audit.jsonl` | Append-only, forever |
| Blob cache (sender side) | `blobs/<sha256[:2]>/<sha256>` | Until operator clears |
