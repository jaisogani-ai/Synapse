// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Integration tests for the daemon client, against an in-process fake Unix
 * socket server that speaks the Synapse Protocol (no Rust daemon required).
 */

import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import net from "node:net";
import fs from "node:fs";

import { SynapseClient } from "../src/client.ts";

const SOCKET = `/tmp/syn-mem-test-${process.pid}-${Date.now()}.sock`;
let server: net.Server;

before(async () => {
  try {
    fs.unlinkSync(SOCKET);
  } catch {
    // no stale socket
  }
  server = net.createServer((socket) => {
    let buffer = "";
    socket.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      const newline = buffer.indexOf("\n");
      if (newline === -1) return;
      const message = JSON.parse(buffer.slice(0, newline));
      const request = (message.body as { request: unknown }).request as
        | string
        | { memory?: { read?: { key: string }; write?: unknown } };

      let responseBody: unknown;
      if (request === "ping") {
        responseBody = { response: "pong" };
      } else if (request === "health") {
        responseBody = { response: { data: { default_model: "claude-opus-4-8", tiers: [] } } };
      } else if (typeof request === "object" && request.memory?.read) {
        responseBody = { response: { data: { key: request.memory.read.key, value: "stored-value" } } };
      } else if (typeof request === "object" && request.memory?.write) {
        responseBody = { response: "ok" };
      } else {
        responseBody = { response: { error: { code: "not_implemented", message: "x" } } };
      }

      const response = {
        id: "resp",
        version: "1.0",
        timestamp: new Date().toISOString(),
        sender: "daemon",
        body: responseBody,
      };
      socket.end(`${JSON.stringify(response)}\n`);
    });
  });
  await new Promise<void>((resolve) => server.listen(SOCKET, resolve));
});

after(() => {
  server.close();
  try {
    fs.unlinkSync(SOCKET);
  } catch {
    // already gone
  }
});

test("ping returns pong over a real unix socket", async () => {
  const client = new SynapseClient(SOCKET, "test");
  const response = await client.ping();
  assert.deepEqual(response.body, { response: "pong" });
});

test("memory write then read round-trips through the protocol", async () => {
  const client = new SynapseClient(SOCKET, "test");
  const write = await client.writeMemory("working", "goal", "ship phase 2");
  assert.deepEqual(write.body, { response: "ok" });
  const read = await client.readMemory("working", "goal");
  const body = read.body as { response: { data: { value: string } } };
  assert.equal(body.response.data.value, "stored-value");
});

test("health reports the default model", async () => {
  const client = new SynapseClient(SOCKET, "test");
  const response = await client.health();
  const body = response.body as { response: { data: { default_model: string } } };
  assert.equal(body.response.data.default_model, "claude-opus-4-8");
});
