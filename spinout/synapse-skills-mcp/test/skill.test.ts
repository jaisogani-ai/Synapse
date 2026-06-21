// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/** Unit tests for the skill registry + built-in catalog. */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  BUILTIN_SKILLS,
  SkillRegistry,
  createDefaultRegistry,
  validateInput,
} from "../src/skill.ts";

test("default registry exposes the built-in catalog", () => {
  const registry = createDefaultRegistry();
  assert.equal(registry.size(), BUILTIN_SKILLS.length);
  const ids = registry.list().map((s) => s.id);
  assert.ok(ids.includes("text.slugify"));
  assert.ok(ids.includes("json.format"));
});

test("search matches id, name, description and tags", () => {
  const registry = createDefaultRegistry();
  const byTag = registry.search("transform").map((s) => s.id);
  assert.ok(byTag.includes("text.slugify"));
  assert.ok(byTag.includes("text.title_case"));
  // Empty query returns everything.
  assert.equal(registry.search("").length, registry.size());
});

test("slugify produces a URL-safe slug", async () => {
  const registry = createDefaultRegistry();
  const result = await registry.invoke("text.slugify", { text: "Hello, World!" });
  assert.deepEqual(result, { ok: true, data: { slug: "hello-world" } });
});

test("title_case capitalizes each word", async () => {
  const registry = createDefaultRegistry();
  const result = await registry.invoke("text.title_case", { text: "the linux of agents" });
  assert.equal((result.data as { text: string }).text, "The Linux Of Agents");
});

test("json.format pretty-prints with default indent", async () => {
  const registry = createDefaultRegistry();
  const result = await registry.invoke("json.format", { json: '{"a":1,"b":2}' });
  assert.ok(result.ok);
  const formatted = (result.data as { formatted: string }).formatted;
  assert.ok(formatted.includes("\n"));
  assert.ok(formatted.startsWith("{\n"));
});

test("word_count returns words, lines, chars", async () => {
  const registry = createDefaultRegistry();
  const result = await registry.invoke("text.word_count", { text: "one two\nthree" });
  assert.deepEqual(result.data, { words: 3, lines: 2, chars: 13 });
});

test("missing required input is reported", async () => {
  const registry = createDefaultRegistry();
  const result = await registry.invoke("text.slugify", {});
  assert.equal(result.ok, false);
  assert.match(result.error ?? "", /missing required/);
});

test("sandbox-required skills are refused in-process", async () => {
  const registry = createDefaultRegistry();
  const result = await registry.invoke("shell.exec", { command: "ls" });
  assert.equal(result.ok, false);
  assert.match(result.error ?? "", /sandbox/);
});

test("handler errors are returned as result errors, not thrown", async () => {
  const registry = createDefaultRegistry();
  const result = await registry.invoke("json.format", { json: "not json" });
  assert.equal(result.ok, false);
  assert.ok(result.error);
});

test("validateInput reports every missing required key", () => {
  assert.deepEqual(validateInput({ required: ["a", "b"] }, { a: 1 }), ["b"]);
  assert.deepEqual(validateInput({ required: ["a", "b"] }, { a: 1, b: 2 }), []);
});

test("unknown skill id yields a clean error", async () => {
  const result = await new SkillRegistry().invoke("nope", {});
  assert.equal(result.ok, false);
  assert.match(result.error ?? "", /not found/);
});
