// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * MCP server wiring for Synapse Backend Architect (MCP #5).
 *
 * Each tool delegates to a pure scaffolder/designer in this package. All
 * generated code is real and runnable — paste the output into a fresh project
 * and it boots.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { designAuth } from "./design_auth.ts";
import { designMicroservices } from "./design_microservices.ts";
import { designQueue } from "./design_queue.ts";
import { designSchema, type Column } from "./design_schema.ts";
import { scaffoldApi } from "./scaffold_api.ts";

const FRAMEWORKS = ["fastapi", "nestjs", "express", "django", "go-gin", "go-fiber"] as const;
const DATABASES = ["postgres", "mysql", "mongodb", "sqlite"] as const;
const FEATURES = ["auth", "rate_limit", "websockets", "queues"] as const;
const DEPLOYMENTS = ["docker", "k8s", "serverless"] as const;
const SCHEMA_FORMATS = ["sql", "prisma", "django_orm", "sqlalchemy"] as const;
const AUTH_METHODS = ["jwt", "oauth", "magic_link", "sso"] as const;
const AUTH_PROVIDERS = ["auth0", "clerk", "supabase", "custom"] as const;
const QUEUE_BACKENDS = ["redis", "rabbitmq", "sqs", "kafka"] as const;
const COLUMN_TYPES = ["uuid", "string", "int", "bigint", "bool", "timestamp", "json"] as const;

/** Build the backend-architect MCP server. */
export function createBackendArchitectServer(): McpServer {
  const server = new McpServer({ name: "synapse-backend-architect-mcp", version: "0.1.0" });

  server.registerTool(
    "backend.scaffold_api",
    {
      description: "Generate a complete, runnable backend API project for the chosen framework.",
      inputSchema: {
        framework: z.enum(FRAMEWORKS),
        name: z.string().optional(),
        features: z.array(z.enum(FEATURES)).optional(),
        database: z.enum(DATABASES).optional(),
        deployment: z.enum(DEPLOYMENTS).optional(),
      },
    },
    async (input) => {
      const scaffold = scaffoldApi(input);
      return { content: [{ type: "text", text: JSON.stringify(scaffold) }] };
    },
  );

  server.registerTool(
    "backend.design_schema",
    {
      description: "Generate a database schema in SQL, Prisma, Django ORM, or SQLAlchemy format.",
      inputSchema: {
        format: z.enum(SCHEMA_FORMATS),
        tables: z.array(
          z.object({
            name: z.string(),
            comment: z.string().optional(),
            columns: z.array(
              z.object({
                name: z.string(),
                type: z.enum(COLUMN_TYPES),
                nullable: z.boolean().optional(),
                unique: z.boolean().optional(),
                primary: z.boolean().optional(),
                references: z.object({ table: z.string(), column: z.string() }).optional(),
              }),
            ),
          }),
        ),
      },
    },
    async (input) => {
      const files = designSchema({ format: input.format, tables: input.tables as { name: string; columns: Column[] }[] });
      return { content: [{ type: "text", text: JSON.stringify(files) }] };
    },
  );

  server.registerTool(
    "backend.design_auth",
    {
      description: "Generate an auth system (JWT, OAuth, magic-link, SSO) for the chosen provider.",
      inputSchema: {
        methods: z.array(z.enum(AUTH_METHODS)),
        provider: z.enum(AUTH_PROVIDERS).optional(),
        multi_tenancy: z.boolean().optional(),
      },
    },
    async (input) => {
      const files = designAuth(input);
      return { content: [{ type: "text", text: JSON.stringify(files) }] };
    },
  );

  server.registerTool(
    "backend.design_queue",
    {
      description: "Design an async job queue with retries, DLQ, and (where supported) scheduling.",
      inputSchema: { use_case: z.string(), backend: z.enum(QUEUE_BACKENDS) },
    },
    async (input) => {
      const files = designQueue(input);
      return { content: [{ type: "text", text: JSON.stringify(files) }] };
    },
  );

  server.registerTool(
    "backend.design_microservices",
    {
      description: "Split a monolith requirement into service boundaries (always emits an api-gateway).",
      inputSchema: { requirements: z.string(), team_size: z.number().int().positive().optional() },
    },
    async (input) => {
      const services = designMicroservices(input);
      return { content: [{ type: "text", text: JSON.stringify(services) }] };
    },
  );

  return server;
}
