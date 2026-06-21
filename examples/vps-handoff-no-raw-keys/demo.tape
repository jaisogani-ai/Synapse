# VHS tape for recording the VPS Handoff Demo GIF
# Install VHS: brew install charmbracelet/tap/vhs
# Run (from repo root): vhs examples/vps-handoff-no-raw-keys/demo.tape
#
# The demo drives the real AES-256-GCM SecretVault via the Node bridge,
# so make sure you've run `npm install` and built the vault first:
#   npm install
#   npm --workspace @synapse/secret-vault-mcp run build

Output assets/demo.gif

Set Shell "zsh"
Set FontSize 14
Set Width 900
Set Height 600
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 40ms
Set PlaybackSpeed 1.5

Type "# SYNAPSE V1 — VPS Handoff Demo"
Enter
Sleep 400ms

Type "# Codex on VPS deploys, never sees the real credential"
Enter
Sleep 400ms

Type "python3.11 examples/vps-handoff-no-raw-keys/demo.py"
Enter
Sleep 12s

Sleep 3s
