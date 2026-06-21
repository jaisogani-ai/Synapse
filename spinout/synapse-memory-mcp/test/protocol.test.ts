// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/** Unit tests for the Synapse Protocol message builders. */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_MODEL,
  PROTOCOL_VERSION,
  encodeLine,
  memoryWrite,
  parseLine,
  ping,
} from "../src/protocol.ts";

test("default model is claude-opus-4-8", () => {
  assert.equal(DEFAULT_MODEL, "claude-opus-4-8");
  assert.equal(PROTOCOL_VERSION, "1.0");
});

test("ping has the externally-tagged request body", () => {
  const msg = ping("agent-1");
  assert.deepEqual(msg.body, { request: "ping" });
  assert.equal(msg.version, "1.0");
  assert.ok(msg.id.length > 0);
});

test("memory write matches the Rust wire shape", () => {
  const msg = memoryWrite("agent-1", "working", "goal", "ship");
  assert.deepEqual(msg.body, {
    request: { memory: { write: { tier: "working", key: "goal", value: "ship" } } },
  });
});

test("encodeLine / parseLine round-trip", () => {
  const msg = ping("a");
  const line = encodeLine(msg);
  assert.ok(line.endsWith("\n"));
  assert.deepEqual(parseLine(line), msg);
});
