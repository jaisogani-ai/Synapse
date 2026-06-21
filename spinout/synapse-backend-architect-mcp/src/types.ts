// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Shared types for the backend-architect MCP.
 *
 * These keep scaffolder inputs/outputs consistent across frameworks and let the
 * MCP server's zod schemas mirror the same union of supported values.
 */

/** Supported API frameworks. */
export type Framework =
  | "fastapi"
  | "nestjs"
  | "express"
  | "django"
  | "go-gin"
  | "go-fiber";

/** Supported relational/document databases. */
export type Database = "postgres" | "mysql" | "mongodb" | "sqlite";

/** Optional features that can be wired into a scaffold. */
export type Feature = "auth" | "rate_limit" | "websockets" | "queues";

/** Deployment target. */
export type Deployment = "docker" | "k8s" | "serverless";

/** Schema generator output format. */
export type SchemaFormat = "sql" | "prisma" | "django_orm" | "sqlalchemy";

/** Auth methods that can be combined. */
export type AuthMethod = "jwt" | "oauth" | "magic_link" | "sso";

/** Auth provider. */
export type AuthProvider = "auth0" | "clerk" | "supabase" | "custom";

/** Queue backend. */
export type QueueBackend = "redis" | "rabbitmq" | "sqs" | "kafka";

/** A single generated source file. */
export interface GeneratedFile {
  /** Relative path inside the generated scaffold. */
  path: string;
  /** UTF-8 file contents. */
  contents: string;
}

/** A complete scaffold. */
export interface Scaffold {
  /** Display name (often the project name). */
  name: string;
  /** Generated files; the caller can write them to disk verbatim. */
  files: GeneratedFile[];
  /** Human-readable notes (e.g. "run `uv pip install -r requirements.txt`"). */
  notes: string[];
}

/** Microservice boundary recommendation. */
export interface Microservice {
  /** Service name. */
  name: string;
  /** What the service owns. */
  responsibilities: string[];
  /** Other services it talks to. */
  depends_on: string[];
  /** Datastore the service owns. */
  data_store: string;
}
