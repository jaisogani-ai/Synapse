# Cross-Device A2A Task Delegation

**Demo 2** — Laptop delegates a task to a VPS over the A2A protocol.
End-to-end: sign → presence check → reputation gate → vault routing →
inbox → accept → result returns.

> This is the **second** launch demo, complementing
> `vps-handoff-no-raw-keys/`. That one shows credential isolation;
> this one shows **task** delegation.

## Two-terminal walkthrough

### Terminal 1 — VPS (receiver)

```bash
cd synapse/
python3 examples/cross-device-task-delegation/run_vps.py
```

The VPS daemon starts on `127.0.0.1:8101` and waits for incoming A2A
tasks. It will print each task as it arrives, prompt for accept/reject,
and send the result back to the sender.

### Terminal 2 — Laptop (sender)

```bash
cd synapse/
python3 examples/cross-device-task-delegation/run_laptop.py
```

The laptop:
1. Resolves `vps-bob` → `http://127.0.0.1:8101/a2a` via identity store
2. Pings the VPS for presence (fails fast if down — no offline queue)
3. Checks `vps-bob`'s reputation score (0.9, above threshold)
4. Builds a standard A2A `Task` with a `TextPart` describing the task
   and a `FileArtifact` carrying `auth_module.py`
5. Signs the JSON-RPC payload with HMAC-SHA256 (reuses Phase B
   `ZeroTrustNetwork`)
6. POSTs to the VPS endpoint
7. Waits for the result that comes back via `tasks/result`

## What you'll see

```
Terminal 1 (VPS):
  📬  Task received from laptop-alice
      task: review auth module
      signature: 4c76a02cb48a2095… ✓
      reputation: 0.90 ✓
      attached: auth_module.py (1.2 KB)
  Accept? [y/N] y
  ✓ accepted — result sent back

Terminal 2 (Laptop):
  → Sending task to vps-bob
    presence:    ✓ reachable
    reputation:  0.90 (≥ 0.50 threshold)
    signature:   HMAC-SHA256
  ← Result received: completed
    "task accepted; surfaced to local tool for execution"
```

## What's NOT in v1 (per spec)

- ❌ Offline queueing / retry-on-reconnect (fails fast)
- ❌ Auto-execution of received tasks (surface only)
- ❌ Custom encryption (uses A2A transport security)
- ❌ Multi-hop relay
- ❌ Persistent presence dashboard
