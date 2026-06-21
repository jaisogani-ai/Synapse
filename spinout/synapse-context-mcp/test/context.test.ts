// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/** Unit tests for the context-optimization core. */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  compress,
  dedupe,
  estimateTokens,
  evict,
  shareSummary,
  summarizeForHandoff,
} from "../src/context.ts";

test("estimateTokens uses ~4 chars per token", () => {
  assert.equal(estimateTokens(""), 0);
  assert.equal(estimateTokens("abcd"), 1);
  assert.equal(estimateTokens("abcde"), 2);
});

test("dedupe removes exact and near-duplicate lines", () => {
  const content = ["the cat sat", "the cat sat", "the cat sat down", "a dog ran"].join("\n");
  const result = dedupe(content, 0.8);
  assert.ok(result.removedLines >= 1);
  assert.ok(result.keptLines < 4);
});

test("compress reduces tokens and respects the budget", () => {
  const lines = [];
  for (let i = 0; i < 40; i += 1) lines.push(`filler line number ${i} with some words`);
  lines.push("DECISION: we chose Rust for the daemon because of performance");
  const text = lines.join("\n");
  const result = compress(text, 30, "semantic");
  assert.ok(result.tokensAfter <= result.tokensBefore);
  assert.ok(result.reductionPct > 0);
  // The important decision line should survive compression.
  assert.ok(result.content.includes("DECISION"));
});

test("compress auto-selects hierarchical when headings exist", () => {
  const text = "# Section A\nsome detail\n# Section B\nmore detail";
  const result = compress(text, 20, "auto");
  assert.equal(result.strategy, "hierarchical");
});

test("summarizeForHandoff produces targeted bullets", () => {
  const ctx = "we decided to use postgres\nrandom chatter\nerror: timeout on boot\nmore chatter";
  const summary = summarizeForHandoff(ctx, "qa-agent");
  assert.ok(summary.startsWith("Handoff to qa-agent:"));
  assert.ok(summary.includes("decided") || summary.includes("error"));
});

test("shareSummary wraps with a scope", () => {
  const shared = shareSummary("done", "team");
  assert.equal(shared.scope, "team");
  assert.ok(shared.sharedAt.length > 0);
});

test("evict keeps the right items per strategy", () => {
  const items = [
    { key: "a", importance: 1, lastUsedAt: 100 },
    { key: "b", importance: 9, lastUsedAt: 50 },
    { key: "c", importance: 5, lastUsedAt: 200 },
  ];
  assert.deepEqual(evict(items, "importance", 1).kept.map((i) => i.key), ["b"]);
  assert.deepEqual(evict(items, "lru", 1).kept.map((i) => i.key), ["c"]);
  assert.equal(evict(items, "age", 2).evicted.length, 1);
});
