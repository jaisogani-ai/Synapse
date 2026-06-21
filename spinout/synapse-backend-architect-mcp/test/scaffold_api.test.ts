// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/** Tests for the API scaffolder. Verifies generated code looks runnable. */

import { test } from "node:test";
import assert from "node:assert/strict";

import { scaffoldApi } from "../src/scaffold_api.ts";

test("fastapi scaffold emits a runnable app", () => {
  const scaffold = scaffoldApi({
    framework: "fastapi",
    name: "demo",
    features: ["auth", "rate_limit", "websockets", "queues"],
    database: "postgres",
    deployment: "docker",
  });
  const fileByPath = Object.fromEntries(scaffold.files.map((f) => [f.path, f.contents]));

  assert.ok(fileByPath["app/main.py"].includes("from fastapi import FastAPI"));
  assert.ok(fileByPath["app/main.py"].includes("FastAPI(title=\"demo\""));
  assert.ok(fileByPath["app/main.py"].includes("auth_router"));
  assert.ok(fileByPath["app/routes/auth.py"].includes("from jose import jwt"));
  assert.ok(fileByPath["app/routes/ws.py"].includes("WebSocket"));
  assert.ok(fileByPath["app/queue.py"].includes("from rq import Queue"));
  assert.ok(fileByPath["requirements.txt"].includes("fastapi>=0.115"));
  assert.ok(fileByPath["requirements.txt"].includes("slowapi"));
  assert.ok(fileByPath["Dockerfile"].includes("FROM python:3.11-slim"));
  assert.ok(scaffold.notes.some((n) => n.includes("uvicorn")));
});

test("express scaffold's package.json parses and lists real deps", () => {
  const scaffold = scaffoldApi({
    framework: "express",
    name: "demo",
    features: ["auth", "rate_limit"],
    database: "postgres",
    deployment: "k8s",
  });
  const fileByPath = Object.fromEntries(scaffold.files.map((f) => [f.path, f.contents]));
  const pkg = JSON.parse(fileByPath["package.json"]);
  assert.equal(pkg.name, "demo");
  assert.equal(pkg.type, "module");
  assert.ok(pkg.dependencies.express);
  assert.ok(pkg.dependencies.jsonwebtoken);
  assert.ok(pkg.dependencies["express-rate-limit"]);
  assert.ok(fileByPath["src/index.js"].includes('import express from "express"'));
  assert.ok(fileByPath["src/routes/auth.js"].includes("jwt.sign"));
  assert.ok(fileByPath["k8s/deployment.yaml"].includes("kind: Deployment"));
});

test("nestjs scaffold compiles to a TS module", () => {
  const scaffold = scaffoldApi({ framework: "nestjs", name: "n", database: "sqlite" });
  const fileByPath = Object.fromEntries(scaffold.files.map((f) => [f.path, f.contents]));
  assert.ok(fileByPath["src/main.ts"].includes("NestFactory.create"));
  assert.ok(fileByPath["src/app.module.ts"].includes("@Module"));
  const pkg = JSON.parse(fileByPath["package.json"]);
  assert.ok(pkg.dependencies["@nestjs/core"]);
});

test("django scaffold has a working manage.py + urls", () => {
  const scaffold = scaffoldApi({ framework: "django", name: "d", database: "sqlite" });
  const fileByPath = Object.fromEntries(scaffold.files.map((f) => [f.path, f.contents]));
  assert.ok(fileByPath["manage.py"].includes("execute_from_command_line"));
  assert.ok(fileByPath["project/urls.py"].includes("urlpatterns"));
});

test("go-gin scaffold has a real handler", () => {
  const scaffold = scaffoldApi({ framework: "go-gin", name: "g", database: "postgres" });
  const fileByPath = Object.fromEntries(scaffold.files.map((f) => [f.path, f.contents]));
  assert.ok(fileByPath["main.go"].includes("gin.Default()"));
  assert.ok(fileByPath["main.go"].includes('"/health"'));
  assert.ok(fileByPath["go.mod"].includes("module g"));
});

test("go-fiber scaffold has a real handler", () => {
  const scaffold = scaffoldApi({ framework: "go-fiber", name: "f", database: "postgres" });
  const fileByPath = Object.fromEntries(scaffold.files.map((f) => [f.path, f.contents]));
  assert.ok(fileByPath["main.go"].includes("fiber.New()"));
  assert.ok(fileByPath["main.go"].includes("fiber.Map"));
});
