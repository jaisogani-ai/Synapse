# VPS Handoff Demo — No Raw Keys

Codex on a VPS deploys to production. It never sees the real API key.

## What happens

1. **Laptop** stores a real API key in the Synapse vault (AES-256-GCM encrypted at rest)
2. **VPS Codex** registers an agent identity with the Synapse daemon (HMAC-SHA256 signing key)
3. **VPS Codex** requests a scoped, time-limited credential proxy (TTL=300s)
4. **Deploy** runs — the daemon resolves the proxy server-side; the agent only holds a proxy URL
5. **Audit log** confirms zero raw key exposure across the entire flow

## Run

```bash
cd synapse/
python3 examples/vps-handoff-no-raw-keys/demo.py
```

## Record GIF

```bash
# Using VHS (https://github.com/charmbracelet/vhs)
vhs examples/vps-handoff-no-raw-keys/demo.tape

# Using asciinema
asciinema rec --command "python3 examples/vps-handoff-no-raw-keys/demo.py" demo.cast
agg demo.cast demo.gif
```

## Zero dependencies

The demo uses only `synapse-core` (Python stdlib crypto) and the Codex adapter.
No external packages required.
