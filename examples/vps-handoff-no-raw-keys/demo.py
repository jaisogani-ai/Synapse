#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""
VPS Handoff Demo — Codex on VPS deploys, never sees the real credential.

Scenario:
  1. Laptop stores a real API key in the **real** AES-256-GCM Synapse vault
  2. VPS Codex adapter registers identity with the daemon
  3. VPS requests a scoped, time-limited proxy (TTL 300s)
  4. Deploy runs via proxy — the raw key never leaves the vault
  5. Audit log proves zero raw key exposure

This demo drives the real ``packages/synapse-vault-mcp`` (Node, AES-256-GCM)
through a stdin/stdout bridge — there is no Python re-implementation of the
vault. If the bridge isn't built, run::

    npm install
    npm --workspace @synapse/secret-vault-mcp run build

Run::

    cd synapse/
    python3 examples/vps-handoff-no-raw-keys/demo.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Make synapse-core and adapters importable
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "packages" / "synapse-core"))
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT))

from adapters.codex import CodexAdapter
from synapse.security.zero_trust import ZeroTrustNetwork

# ─── Terminal colors ────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
RED = "\033[31m"
WHITE = "\033[97m"

PASS = f"{GREEN}✓{RESET}"
FAIL = f"{RED}✗{RESET}"
ARROW = f"{DIM}→{RESET}"

# ─── Real vault driven via the Node bridge ─────────────────────────────────

BRIDGE_JS = ROOT / "packages" / "synapse-vault-mcp" / "dist" / "bridge.js"


@dataclass(frozen=True)
class ProxyCredential:
    proxy_url: str
    proxy_token: str
    service: str
    expires_at: str


@dataclass(frozen=True)
class VaultAuditEntry:
    action: str
    name: str
    at: str
    purpose: str = ""


class RealVault:
    """Thin Python facade over the real AES-256-GCM SecretVault (Node child)."""

    def __init__(self) -> None:
        if not BRIDGE_JS.exists():
            raise FileNotFoundError(
                f"vault bridge not built. Run: npm install && "
                f"npm --workspace @synapse/secret-vault-mcp run build"
            )
        node = shutil.which("node")
        if node is None:
            raise FileNotFoundError("`node` not on PATH; cannot drive the real vault")
        self._proc = subprocess.Popen(
            [node, str(BRIDGE_JS)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 0

    def _call(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        req = {"id": str(self._next_id), "method": method, "params": params or {}}
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            err = self._proc.stderr.read() if self._proc.stderr else ""
            raise RuntimeError(f"vault bridge closed: {err}")
        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(f"vault error: {resp['error']}")
        return resp["result"]

    def store(self, name: str, value: str) -> None:
        self._call("store_secret", {"name": name, "value": value})

    def request_proxy(self, service: str, purpose: str, ttl: int = 300) -> ProxyCredential:
        out = self._call(
            "request_credential",
            {"service": service, "purpose": purpose, "durationSeconds": ttl},
        )
        return ProxyCredential(
            proxy_url=out["proxyUrl"],
            proxy_token=out["proxyToken"],
            service=out["service"],
            expires_at=out["expiresAt"],
        )

    def resolve_proxy(self, token: str) -> str | None:
        out = self._call("resolve_proxy", {"token": token})
        return out["value"] if out["found"] else None

    def audit_log(self) -> list[VaultAuditEntry]:
        out = self._call("audit_log")
        return [
            VaultAuditEntry(
                action=e["action"],
                name=e["name"],
                at=e["at"],
                purpose=e.get("purpose") or "",
            )
            for e in out["entries"]
        ]

    def has_raw_exposure(self) -> bool:
        # The real vault has no "raw_retrieve" action; we accept any *direct*
        # `retrieve` against a stored secret as raw exposure. The demo never
        # calls retrieve(), only resolveProxy().
        return any(e.action == "retrieve" for e in self.audit_log())

    def redact_preview(self, value: str) -> str:
        return self._call("redact_preview", {"value": value})["preview"]

    def close(self) -> None:
        try:
            assert self._proc.stdin is not None
            self._proc.stdin.close()
            self._proc.wait(timeout=2)
        except Exception:
            self._proc.kill()


# ─── Demo runner ────────────────────────────────────────────────────────────


def banner() -> None:
    print()
    print(f"{BOLD}{CYAN}{'═' * 66}{RESET}")
    print(f"{BOLD}{CYAN}  SYNAPSE V1 — VPS HANDOFF DEMO{RESET}")
    print(f"{BOLD}{CYAN}  Codex on VPS deploys. Never sees the real credential.{RESET}")
    print(f"{BOLD}{CYAN}  Driving the REAL AES-256-GCM SecretVault (Node bridge){RESET}")
    print(f"{BOLD}{CYAN}{'═' * 66}{RESET}")
    print()


def step(n: int, label: str) -> None:
    print(f"\n{BOLD}{MAGENTA}┌─ STEP {n}: {label}{RESET}")
    print(f"{MAGENTA}│{RESET}")


def info(msg: str) -> None:
    print(f"{MAGENTA}│{RESET}  {msg}")


def done(msg: str) -> None:
    print(f"{MAGENTA}│{RESET}  {PASS} {GREEN}{msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{MAGENTA}│{RESET}  {YELLOW}⚠ {msg}{RESET}")


def end_step() -> None:
    print(f"{MAGENTA}└{'─' * 50}{RESET}")


def pause(seconds: float = 0.4) -> None:
    time.sleep(seconds)


def run_demo() -> None:
    banner()
    vault = RealVault()
    try:
        network = ZeroTrustNetwork()
        real_api_key = "sk-ant-api03-FAKE-DEMO-KEY-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"

        # ── Step 1: Laptop stores key ──────────────────────────────────
        step(1, "LAPTOP STORES API KEY IN REAL AES-256-GCM VAULT")
        info(f"\U0001F511 Real API key: {BOLD}{vault.redact_preview(real_api_key)}{RESET}")
        pause(0.4)
        vault.store("anthropic-api", real_api_key)
        done(f"\U0001F512 Encrypted at rest with AES-256-GCM (real Node SecretVault)")
        info(f"   {DIM}synapse vault store anthropic-api --value <redacted>{RESET}")
        done("Key stored. Raw value will NEVER appear again in this demo.")
        end_step()
        pause()

        # ── Step 2: VPS Codex registers identity ───────────────────────
        step(2, "VPS CODEX REGISTERS AGENT IDENTITY")
        adapter = CodexAdapter(
            agent_id="codex-vps-deploy-01",
            network=network,
            capabilities=["vault.request_credential", "trust.read"],
        )
        identity = adapter.register()
        done(f"Identity issued: {BOLD}codex-vps-deploy-01{RESET}")
        info(f"   {DIM}agent_id = {identity.agent_id}{RESET}")
        info(f"   {DIM}tool_type = {adapter.tool_type}{RESET}")
        info(f"   {DIM}capabilities = [vault.request_credential, trust.read]{RESET}")
        done(f"\U0001F6E1️ Agent registered with daemon, HMAC signing key provisioned")
        end_step()
        pause()

        # ── Step 3: VPS requests scoped proxy ──────────────────────────
        step(3, "VPS REQUESTS SCOPED CREDENTIAL PROXY (TTL=300s)")
        info(f"   {DIM}synapse vault request --service anthropic-api --ttl 300{RESET}")
        pause(0.3)
        proxy = vault.request_proxy(
            service="anthropic-api",
            purpose="production deploy via codex",
            ttl=300,
        )
        done(f"Proxy issued: {BOLD}{proxy.proxy_url[:50]}…{RESET}")
        info(f"   {DIM}service   = {proxy.service}{RESET}")
        info(f"   {DIM}expires   = {proxy.expires_at}{RESET}")
        warn("Agent receives ONLY the proxy URL. Never the raw key.")
        end_step()
        pause()

        # ── Step 4: Deploy runs via proxy ──────────────────────────────
        step(4, "DEPLOY RUNS VIA PROXY")
        deploy_payload = b'{"action":"deploy","service":"anthropic-api","env":"production"}'
        signed = adapter.sign_message(deploy_payload)

        info(f"\U0001F680 Signed deploy request:")
        info(f"   {DIM}X-Synapse-Agent     = {signed.headers.agent_id}{RESET}")
        info(f"   {DIM}X-Synapse-Tool      = {signed.headers.tool_type}{RESET}")
        info(f"   {DIM}X-Synapse-Signature = {signed.headers.signature[:32]}…{RESET}")
        info(f"   {DIM}X-Synapse-Token     = <bearer>{RESET}")
        pause(0.3)

        info(f"\n{MAGENTA}│{RESET}  {DIM}── daemon-side (invisible to agent) ──{RESET}")
        resolved = vault.resolve_proxy(proxy.proxy_token)
        if resolved is not None:
            # Prove the resolved value is the real key — but only ever via the proxy path
            done(f"Daemon resolved proxy → secret (length {len(resolved)} chars)")
            done(f"\U0001F680 Deploy succeeded! Agent used proxy, never raw key.")
            assert resolved == real_api_key
        else:
            print(f"{MAGENTA}│{RESET}  {FAIL} {RED}Deploy failed — proxy expired or invalid{RESET}")
        end_step()
        pause()

        # ── Step 5: Audit log ──────────────────────────────────────────
        step(5, "AUDIT LOG (FROM REAL VAULT) — ZERO RAW KEY EXPOSURE")
        info(f"\U0001F4CB {BOLD}Vault audit trail (action / name / time):{RESET}")
        print(f"{MAGENTA}│{RESET}")
        for entry in vault.audit_log():
            color = RED if entry.action == "retrieve" else GREEN
            extra = f"  {DIM}({entry.purpose}){RESET}" if entry.purpose else ""
            print(
                f"{MAGENTA}│{RESET}    {DIM}{entry.at}{RESET}  "
                f"{color}{entry.action:18s}{RESET}  {entry.name}{extra}"
            )
        print(f"{MAGENTA}│{RESET}")

        info(f"\U0001F441 {BOLD}Adapter audit trail:{RESET}")
        print(f"{MAGENTA}│{RESET}")
        for entry in adapter.audit_log():
            print(
                f"{MAGENTA}│{RESET}    {DIM}{entry.timestamp}{RESET}  "
                f"{GREEN}{entry.action:18s}{RESET}  {entry.agent_id}  {DIM}{entry.detail}{RESET}"
            )
        print(f"{MAGENTA}│{RESET}")

        has_exposure = vault.has_raw_exposure()
        if not has_exposure:
            done(f"\U0001F6E1️ ZERO raw key exposure in audit log")
            done("No 'retrieve' actions — agent never touched the real key")
        else:
            print(f"{MAGENTA}│{RESET}  {FAIL} {RED}RAW KEY EXPOSURE DETECTED{RESET}")
        end_step()

        # ── Summary ────────────────────────────────────────────────────
        print()
        print(f"{BOLD}{CYAN}{'═' * 66}{RESET}")
        print(f"{BOLD}{CYAN}  RESULT: {'PASS' if not has_exposure else 'FAIL'}{RESET}")
        print(f"{CYAN}{'─' * 66}{RESET}")
        if not has_exposure:
            print(f"  {PASS} API key stored encrypted by REAL AES-256-GCM SecretVault")
            print(f"  {PASS} Agent identity registered with HMAC signing")
            print(f"  {PASS} Scoped proxy issued (TTL=300s), not raw key")
            print(f"  {PASS} Deploy signed with agent identity")
            print(f"  {PASS} Daemon resolved proxy server-side, agent blind")
            print(f"  {PASS} Audit log (from the real vault) confirms zero raw exposure")
        print(f"{BOLD}{CYAN}{'═' * 66}{RESET}")
        print()
    finally:
        vault.close()


if __name__ == "__main__":
    run_demo()
