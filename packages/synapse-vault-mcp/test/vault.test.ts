// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/** Unit tests for the AES-256-GCM secret vault core. */

import { test } from "node:test";
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";

import { SecretVault, redact } from "../src/vault.ts";

test("stores and retrieves a secret round-trip", () => {
  const vault = new SecretVault();
  vault.storeSecret("anthropic", "sk-ant-secret-value");
  assert.equal(vault.retrieve("anthropic"), "sk-ant-secret-value");
});

test("a secret encrypted under one key cannot be read with another", () => {
  const a = new SecretVault(randomBytes(32));
  a.storeSecret("db", "p@ss");
  const b = new SecretVault(randomBytes(32));
  // Hand B the exact ciphertext A produced; B's different key must fail GCM auth.
  const aStore = (a as unknown as { store: Map<string, unknown> }).store;
  const bStore = (b as unknown as { store: Map<string, unknown> }).store;
  bStore.set("db", aStore.get("db"));
  assert.throws(() => b.retrieve("db"));
});

test("tampered ciphertext is rejected on decrypt", () => {
  const vault = new SecretVault();
  vault.storeSecret("x", "value");
  // Reach in and corrupt the stored ciphertext to prove GCM integrity.
  const internal = vault as unknown as { store: Map<string, { ciphertext: string }> };
  internal.store.get("x")!.ciphertext = Buffer.from("corrupted").toString("base64");
  assert.throws(() => vault.retrieve("x"));
});

test("request_credential returns a proxy, never the raw secret", () => {
  const vault = new SecretVault();
  vault.storeSecret("openai", "sk-super-secret");
  const proxy = vault.requestCredential({ service: "openai", purpose: "call model", durationSeconds: 60 });
  assert.ok(proxy.proxyUrl.startsWith("synapse+vault://proxy/"));
  assert.ok(!JSON.stringify(proxy).includes("sk-super-secret"));
  // Only the daemon side resolves a proxy back to the secret.
  assert.equal(vault.resolveProxy(proxy.proxyToken), "sk-super-secret");
});

test("proxies expire", () => {
  const vault = new SecretVault();
  vault.storeSecret("svc", "secret");
  const proxy = vault.requestCredential({ service: "svc", purpose: "x", durationSeconds: 1 });
  assert.equal(vault.resolveProxy(proxy.proxyToken, Date.now() + 5000), null);
});

test("rotate keeps the previous value within its grace window", () => {
  const vault = new SecretVault();
  vault.storeSecret("k", "old");
  vault.rotate("k", "new", 300);
  assert.equal(vault.retrieve("k"), "new");
  assert.equal(vault.peekPrevious("k"), "old");
  assert.equal(vault.peekPrevious("k", Date.now() + 400_000), null);
});

test("revoke removes the secret and its proxies", () => {
  const vault = new SecretVault();
  vault.storeSecret("k", "v");
  const proxy = vault.requestCredential({ service: "k", purpose: "p" });
  vault.revoke("k", "compromised");
  assert.equal(vault.has("k"), false);
  assert.equal(vault.resolveProxy(proxy.proxyToken), null);
});

test("detect_exposure finds and redacts leaked secrets", () => {
  // Fixtures assembled at runtime so the recognizable prefixes never appear
  // as contiguous literals in this source file (avoids tripping third-party
  // secret scanners on the repo itself). These are NOT real credentials.
  const awsFixture = "AKIA" + "IOSFODNN7EXAMPLE";
  const ghFixture = "ghp" + "_" + "0123456789abcdefghijklmnopqrstuvwxyz";
  const findings = new SecretVault().detectExposure(`key=${awsFixture} and ${ghFixture}`);
  const providers = findings.map((f) => f.provider);
  assert.ok(providers.includes("AWS"));
  assert.ok(providers.includes("GitHub"));
  for (const f of findings) assert.ok(!f.preview.includes(awsFixture));
});

test("audit log records access without secret values", () => {
  const vault = new SecretVault();
  vault.storeSecret("k", "supersecret");
  vault.retrieve("k");
  const log = vault.auditLog("k");
  assert.ok(log.length >= 2);
  assert.ok(!JSON.stringify(log).includes("supersecret"));
});

test("redact never reveals the full secret", () => {
  assert.ok(!redact("supersecretvalue").includes("supersecretvalue"));
  assert.equal(redact("short"), "*****");
});
