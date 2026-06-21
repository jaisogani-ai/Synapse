// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * MCP server wiring for the Synapse Secret Vault (MCP #4).
 *
 * Exposes the vault as Model Context Protocol tools. The crypto core lives in
 * {@link ./vault.ts} (dependency-free + unit-tested); this file only adapts it
 * to the `@modelcontextprotocol/sdk` transport.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { SecretVault } from "./vault.ts";

/** Build an MCP server backed by `vault` exposing the vault tool surface. */
export function createVaultServer(vault: SecretVault = new SecretVault()): McpServer {
  const server = new McpServer({ name: "synapse-secret-vault-mcp", version: "0.1.0" });

  server.registerTool(
    "vault.store_secret",
    {
      description: "Store a new secret. Encrypted at rest with AES-256-GCM. Value is redacted from logs.",
      inputSchema: { name: z.string(), value: z.string(), metadata: z.record(z.string()).optional() },
    },
    async ({ name, value, metadata }) => {
      vault.storeSecret(name, value, metadata ?? {});
      return { content: [{ type: "text", text: `stored secret '${name}'` }] };
    },
  );

  server.registerTool(
    "vault.request_credential",
    {
      description: "Request a SCOPED, TIME-LIMITED credential proxy. The agent never sees the raw key.",
      inputSchema: {
        service: z.string(),
        purpose: z.string(),
        duration_seconds: z.number().int().positive().max(3600).optional(),
        scope: z.string().optional(),
      },
    },
    async ({ service, purpose, duration_seconds, scope }) => {
      const proxy = vault.requestCredential({
        service,
        purpose,
        durationSeconds: duration_seconds,
        scope,
      });
      return { content: [{ type: "text", text: JSON.stringify(proxy) }] };
    },
  );

  server.registerTool(
    "vault.rotate",
    {
      description: "Rotate a secret. The previous version stays valid for grace_seconds.",
      inputSchema: { name: z.string(), value: z.string(), grace_seconds: z.number().int().nonnegative().optional() },
    },
    async ({ name, value, grace_seconds }) => {
      vault.rotate(name, value, grace_seconds ?? 300);
      return { content: [{ type: "text", text: `rotated '${name}'` }] };
    },
  );

  server.registerTool(
    "vault.audit_log",
    {
      description: "Get the access log for a specific secret (values never appear).",
      inputSchema: { name: z.string() },
    },
    async ({ name }) => {
      return { content: [{ type: "text", text: JSON.stringify(vault.auditLog(name)) }] };
    },
  );

  server.registerTool(
    "vault.detect_exposure",
    {
      description: "Scan a file/diff for leaked secrets BEFORE commit. Findings are redacted.",
      inputSchema: { content: z.string() },
    },
    async ({ content }) => {
      return { content: [{ type: "text", text: JSON.stringify(vault.detectExposure(content)) }] };
    },
  );

  server.registerTool(
    "vault.revoke",
    {
      description: "Immediately revoke a secret. All active proxies for it die.",
      inputSchema: { name: z.string(), reason: z.string() },
    },
    async ({ name, reason }) => {
      vault.revoke(name, reason);
      return { content: [{ type: "text", text: `revoked '${name}'` }] };
    },
  );

  return server;
}
