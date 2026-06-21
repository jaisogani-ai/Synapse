// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * MCP server wiring for Synapse Context Optimization (MCP #3).
 *
 * The optimization logic lives in {@link ./context.ts} (dependency-free +
 * unit-tested); this file adapts it to `@modelcontextprotocol/sdk`.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { compress, dedupe, evict, shareSummary, summarizeForHandoff } from "./context.ts";

/** Build the context-optimization MCP server. */
export function createContextServer(): McpServer {
  const server = new McpServer({ name: "synapse-context-mcp", version: "0.1.0" });

  server.registerTool(
    "context.compress",
    {
      description: "Compress conversation history toward a token budget, keeping the most important lines.",
      inputSchema: {
        history: z.union([z.string(), z.array(z.string())]),
        target_tokens: z.number().int().positive(),
        strategy: z.enum(["semantic", "decision_tree", "hierarchical", "auto"]).optional(),
      },
    },
    async ({ history, target_tokens, strategy }) => {
      const result = compress(history, target_tokens, strategy ?? "auto");
      return { content: [{ type: "text", text: JSON.stringify(result) }] };
    },
  );

  server.registerTool(
    "context.dedupe",
    {
      description: "Remove duplicate / near-duplicate lines from context.",
      inputSchema: { content: z.string(), similarity_threshold: z.number().min(0).max(1).optional() },
    },
    async ({ content, similarity_threshold }) => {
      const result = dedupe(content, similarity_threshold ?? 0.9);
      return { content: [{ type: "text", text: JSON.stringify(result) }] };
    },
  );

  server.registerTool(
    "context.summarize_for_handoff",
    {
      description: "Generate a tight summary for agent-to-agent handoff.",
      inputSchema: { context: z.string(), target_agent: z.string() },
    },
    async ({ context, target_agent }) => {
      return { content: [{ type: "text", text: summarizeForHandoff(context, target_agent) }] };
    },
  );

  server.registerTool(
    "context.share_summary",
    {
      description: "Push a summary into shared memory accessible by all agents.",
      inputSchema: { summary: z.string(), scope: z.enum(["team", "project", "global"]) },
    },
    async ({ summary, scope }) => {
      return { content: [{ type: "text", text: JSON.stringify(shareSummary(summary, scope)) }] };
    },
  );

  server.registerTool(
    "context.evict",
    {
      description: "Evict stale/low-importance context items by a strategy.",
      inputSchema: {
        items: z.array(z.object({ key: z.string(), importance: z.number(), lastUsedAt: z.number() })),
        strategy: z.enum(["lru", "importance", "age"]),
        keep: z.number().int().nonnegative(),
      },
    },
    async ({ items, strategy, keep }) => {
      return { content: [{ type: "text", text: JSON.stringify(evict(items, strategy, keep)) }] };
    },
  );

  return server;
}
