// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Stdin/stdout JSON line bridge over the real {@link SecretVault}.
 *
 * Each line on stdin is a JSON object `{ "id": "...", "method": "...", "params": {...} }`.
 * Each response is one JSON line on stdout: `{ "id": "...", "result": ... }` or
 * `{ "id": "...", "error": "..." }`.
 *
 * Exists so non-Node callers (e.g. the Python vps-handoff demo) can exercise
 * the real AES-256-GCM code path instead of an in-process simulation.
 */

import { createInterface } from "node:readline";
import { SecretVault, redact } from "./vault.ts";

interface BridgeRequest {
  id?: string | number;
  method: string;
  params?: Record<string, unknown>;
}

const vault = new SecretVault();

function handle(req: BridgeRequest): unknown {
  const params = req.params ?? {};
  switch (req.method) {
    case "store_secret":
      vault.storeSecret(String(params.name), String(params.value));
      return { ok: true };
    case "redact_preview":
      return { preview: redact(String(params.value)) };
    case "request_credential": {
      const proxy = vault.requestCredential({
        service: String(params.service),
        purpose: String(params.purpose ?? ""),
        durationSeconds: params.durationSeconds == null ? undefined : Number(params.durationSeconds),
      });
      return proxy;
    }
    case "resolve_proxy": {
      const value = vault.resolveProxy(String(params.token));
      return { value, found: value !== null };
    }
    case "audit_log":
      return { entries: vault.auditLog(params.name == null ? undefined : String(params.name)) };
    default:
      throw new Error(`unknown method: ${req.method}`);
  }
}

const rl = createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let req: BridgeRequest;
  try {
    req = JSON.parse(trimmed) as BridgeRequest;
  } catch (err) {
    process.stdout.write(JSON.stringify({ id: null, error: `invalid json: ${(err as Error).message}` }) + "\n");
    return;
  }
  try {
    const result = handle(req);
    process.stdout.write(JSON.stringify({ id: req.id ?? null, result }) + "\n");
  } catch (err) {
    process.stdout.write(JSON.stringify({ id: req.id ?? null, error: (err as Error).message }) + "\n");
  }
});
