// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Synapse Protocol v1.0 message builders (TypeScript side).
 *
 * Mirrors the Rust daemon's `protocol` module exactly: newline-delimited JSON
 * envelopes with externally-tagged bodies, e.g. a memory write serializes to
 * `{ "request": { "memory": { "write": { tier, key, value } } } }`. Keeping
 * this in lock-step with the daemon is what lets any MCP client read/write the
 * 8-tier memory through synapse-memory-mcp.
 */

import { randomUUID } from "node:crypto";

/** Protocol version spoken by this client. */
export const PROTOCOL_VERSION = "1.0";
/** Default model for Synapse agent reasoning (single source of truth). */
export const DEFAULT_MODEL = "claude-opus-4-8";

/** The eight memory tiers (identical to the Rust `MemoryTier` enum). */
export type MemoryTier =
  | "working"
  | "episodic"
  | "vector"
  | "graph"
  | "team"
  | "project"
  | "temporal"
  | "reputation";

/** A Synapse Protocol message envelope. */
export interface SynapseMessage {
  id: string;
  version: string;
  timestamp: string;
  sender: string;
  body: unknown;
}

function newMessage(sender: string, body: unknown): SynapseMessage {
  return {
    id: randomUUID(),
    version: PROTOCOL_VERSION,
    timestamp: new Date().toISOString(),
    sender,
    body,
  };
}

/** A `ping` request. */
export function ping(sender: string): SynapseMessage {
  return newMessage(sender, { request: "ping" });
}

/** A `health` request. */
export function health(sender: string): SynapseMessage {
  return newMessage(sender, { request: "health" });
}

/** A memory `read` request. */
export function memoryRead(sender: string, tier: MemoryTier, key: string): SynapseMessage {
  return newMessage(sender, { request: { memory: { read: { tier, key } } } });
}

/** A memory `write` request. */
export function memoryWrite(
  sender: string,
  tier: MemoryTier,
  key: string,
  value: string,
): SynapseMessage {
  return newMessage(sender, { request: { memory: { write: { tier, key, value } } } });
}

/** A memory `search` request. */
export function memorySearch(sender: string, tier: MemoryTier, query: string): SynapseMessage {
  return newMessage(sender, { request: { memory: { search: { tier, query } } } });
}

/** Encode a message as a protocol line (JSON + newline). */
export function encodeLine(message: SynapseMessage): string {
  return `${JSON.stringify(message)}\n`;
}

/** Parse a protocol line back into a message. */
export function parseLine(line: string): SynapseMessage {
  return JSON.parse(line.trim()) as SynapseMessage;
}
