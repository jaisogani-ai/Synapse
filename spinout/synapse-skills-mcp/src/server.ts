// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * MCP server wiring for Synapse Skills (MCP #2).
 *
 * Bridges MCP tool calls to {@link ./skill.ts}'s registry. The registry is
 * dependency-free and unit-tested; this file only adapts it to
 * `@modelcontextprotocol/sdk`.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import {
  SkillRegistry,
  createDefaultRegistry,
  type Skill,
} from "./skill.ts";

/** Build the skills MCP server backed by `registry`. */
export function createSkillsServer(registry: SkillRegistry = createDefaultRegistry()): McpServer {
  const server = new McpServer({ name: "synapse-skills-mcp", version: "0.1.0" });

  server.registerTool(
    "skills.list",
    { description: "List every registered skill (id, name, version, tags, capabilities).", inputSchema: {} },
    async () => ({ content: [{ type: "text", text: JSON.stringify(registry.list()) }] }),
  );

  server.registerTool(
    "skills.search",
    {
      description: "Search registered skills by free text (id, name, description, tags).",
      inputSchema: { query: z.string() },
    },
    async ({ query }) => ({ content: [{ type: "text", text: JSON.stringify(registry.search(query)) }] }),
  );

  server.registerTool(
    "skills.get",
    { description: "Return the metadata for one skill by id.", inputSchema: { id: z.string() } },
    async ({ id }) => {
      const skill = registry.get(id);
      if (!skill) {
        return { content: [{ type: "text", text: JSON.stringify({ ok: false, error: "not found" }) }] };
      }
      const { handler: _handler, ...meta } = skill;
      return { content: [{ type: "text", text: JSON.stringify(meta) }] };
    },
  );

  server.registerTool(
    "skills.invoke",
    {
      description:
        "Invoke a skill by id with structured input. Refused if the skill requires the sandbox.",
      inputSchema: { id: z.string(), input: z.record(z.unknown()).optional() },
    },
    async ({ id, input }) => {
      const result = await registry.invoke(id, input ?? {});
      return { content: [{ type: "text", text: JSON.stringify(result) }] };
    },
  );

  server.registerTool(
    "skills.register",
    {
      description: "Register a new in-process skill at runtime (no sandbox-required skills here).",
      inputSchema: {
        id: z.string(),
        name: z.string(),
        version: z.string(),
        description: z.string(),
        capabilities: z.array(z.string()).optional(),
        tags: z.array(z.string()).optional(),
        required_input: z.array(z.string()).optional(),
      },
    },
    async ({ id, name, version, description, capabilities, tags, required_input }) => {
      const skill: Skill = {
        id,
        name,
        version,
        description,
        capabilities: capabilities ?? [],
        tags: tags ?? [],
        inputSchema: { required: required_input ?? [] },
        requiresSandbox: false,
        // Newly-registered skills are recorded but not executable until the
        // owning client supplies a handler over a follow-up channel.
        handler: () => ({ ok: false, error: "no handler installed for runtime-registered skill" }),
      };
      registry.register(skill);
      return { content: [{ type: "text", text: JSON.stringify({ ok: true, id, size: registry.size() }) }] };
    },
  );

  return server;
}
