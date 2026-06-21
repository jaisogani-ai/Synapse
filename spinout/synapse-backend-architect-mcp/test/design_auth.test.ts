// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/** Tests for the auth designer. */

import { test } from "node:test";
import assert from "node:assert/strict";

import { designAuth } from "../src/design_auth.ts";

test("JWT scaffold compiles in spirit and includes verifier", () => {
  const files = designAuth({ methods: ["jwt"] });
  const jwt = files.find((f) => f.path === "auth/jwt.py");
  assert.ok(jwt);
  assert.ok(jwt!.contents.includes("from jose import"));
  assert.ok(jwt!.contents.includes("def issue_token"));
  assert.ok(jwt!.contents.includes("def verify_token"));
  assert.ok(jwt!.contents.includes("HS256"));
});

test("JWT multi-tenancy adds tenant parameter", () => {
  const files = designAuth({ methods: ["jwt"], multi_tenancy: true });
  const jwt = files.find((f) => f.path === "auth/jwt.py")!;
  assert.ok(jwt.contents.includes("tenant_id"));
  assert.ok(jwt.contents.includes('"tenant": tenant_id'));
});

test("OAuth, magic-link, SSO emit their respective files", () => {
  const files = designAuth({ methods: ["oauth", "magic_link", "sso"], provider: "auth0" });
  const paths = files.map((f) => f.path);
  assert.ok(paths.includes("auth/oauth.py"));
  assert.ok(paths.includes("auth/magic_link.py"));
  assert.ok(paths.includes("auth/sso.py"));
  const env = files.find((f) => f.path === "auth/.env.example")!;
  assert.ok(env.contents.includes("AUTH0_DOMAIN"));
});

test("magic-link uses hmac.compare_digest for verification", () => {
  const files = designAuth({ methods: ["magic_link"] });
  const ml = files.find((f) => f.path === "auth/magic_link.py")!;
  assert.ok(ml.contents.includes("hmac.compare_digest"));
});

test("empty methods is rejected", () => {
  assert.throws(() => designAuth({ methods: [] }));
});
