// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/** Tests for the microservice splitter. */

import { test } from "node:test";
import assert from "node:assert/strict";

import { designMicroservices } from "../src/design_microservices.ts";

test("always emits an api-gateway, even with no anchors", () => {
  const services = designMicroservices({ requirements: "just a marketing site" });
  assert.equal(services.length, 1);
  assert.equal(services[0].name, "api-gateway");
});

test("detects auth, billing, payments, notifications from prose", () => {
  const services = designMicroservices({
    requirements:
      "Build a SaaS where users sign up with SSO, subscribe to a plan, " +
      "checkout via card, and get email + SMS notifications.",
  });
  const names = services.map((s) => s.name);
  assert.ok(names.includes("auth-service"));
  assert.ok(names.includes("billing-service"));
  assert.ok(names.includes("payments-service"));
  assert.ok(names.includes("notifications-service"));
  // billing-service depends on payments-service.
  const billing = services.find((s) => s.name === "billing-service")!;
  assert.ok(billing.depends_on.includes("payments-service"));
});

test("api-gateway depends on every detected service", () => {
  const services = designMicroservices({
    requirements: "Need login, payments via Stripe, and an analytics dashboard.",
  });
  const gateway = services.find((s) => s.name === "api-gateway")!;
  assert.ok(gateway.depends_on.includes("auth-service"));
  assert.ok(gateway.depends_on.includes("payments-service"));
  assert.ok(gateway.depends_on.includes("analytics-service"));
});

test("team_size caps the number of returned services", () => {
  const services = designMicroservices({
    requirements:
      "auth payment order search chat message file media analytics notification",
    team_size: 2,
  });
  assert.ok(services.length <= 4);
});
