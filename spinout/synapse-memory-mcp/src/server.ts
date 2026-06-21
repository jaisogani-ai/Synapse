// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * MCP server wiring for Synapse Memory access (MCP #1).
 *
 * Bridges MCP tool calls to the Synapse daemon's 8-tier memory over the Unix
 * socket ({@link ./client.ts}). The protocol + client core is dependency-free
 * and unit-tested; this file adapts it to `@modelcontextprotocol/sdk`.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { SynapseClient, DEFAULT_SOCKET_PATH } from "./client.ts";

const TIERS = [
  "working",
  "episodic",
  "vector",
  "graph",
  "team",
  "project",
  "temporal",
  "reputation",
] as const;

/** Build the memory-access MCP server backed by a daemon `client`. */
export function createMemoryServer(
  client: SynapseClient = new SynapseClient(process.env.SYNAPSE_SOCKET ?? DEFAULT_SOCKET_PATH),
): McpServer {
  const server = new McpServer({ name: "synapse-memory-mcp", version: "0.1.0" });

  server.registerTool(
    "memory.read",
    {
      description: "Read a key from one of the 8 Synapse memory tiers.",
      inputSchema: { tier: z.enum(TIERS), key: z.string() },
    },
    async ({ tier, key }) => {
      const response = await client.readMemory(tier, key);
      return { content: [{ type: "text", text: JSON.stringify(response.body) }] };
    },
  );

  server.registerTool(
    "memory.write",
    {
      description: "Write a value to one of the 8 Synapse memory tiers.",
      inputSchema: { tier: z.enum(TIERS), key: z.string(), value: z.string() },
    },
    async ({ tier, key, value }) => {
      const response = await client.writeMemory(tier, key, value);
      return { content: [{ type: "text", text: JSON.stringify(response.body) }] };
    },
  );

  server.registerTool(
    "memory.search",
    {
      description: "Search one of the 8 Synapse memory tiers.",
      inputSchema: { tier: z.enum(TIERS), query: z.string() },
    },
    async ({ tier, query }) => {
      const response = await client.searchMemory(tier, query);
      return { content: [{ type: "text", text: JSON.stringify(response.body) }] };
    },
  );

  server.registerTool(
    "memory.ping",
    { description: "Liveness check against the Synapse daemon.", inputSchema: {} },
    async () => {
      const response = await client.ping();
      return { content: [{ type: "text", text: JSON.stringify(response.body) }] };
    },
  );

  server.registerTool(
    "memory.health",
    { description: "Daemon + memory health (reports tiers and default model).", inputSchema: {} },
    async () => {
      const response = await client.health();
      return { content: [{ type: "text", text: JSON.stringify(response.body) }] };
    },
  );

  return server;
}
