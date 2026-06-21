// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/** Tests for the schema designer. */

import { test } from "node:test";
import assert from "node:assert/strict";

import { designSchema, type Table } from "../src/design_schema.ts";

const USERS: Table = {
  name: "users",
  comment: "Application users",
  columns: [
    { name: "id", type: "uuid", primary: true },
    { name: "email", type: "string", unique: true },
    { name: "created_at", type: "timestamp", nullable: false },
  ],
};

const POSTS: Table = {
  name: "posts",
  columns: [
    { name: "id", type: "uuid", primary: true },
    { name: "author_id", type: "uuid", references: { table: "users", column: "id" } },
    { name: "body", type: "string" },
  ],
};

test("SQL output is valid PostgreSQL DDL", () => {
  const [file] = designSchema({ format: "sql", tables: [USERS, POSTS] });
  assert.equal(file.path, "schema.sql");
  assert.ok(file.contents.includes("CREATE TABLE IF NOT EXISTS users"));
  assert.ok(file.contents.includes("id UUID PRIMARY KEY"));
  assert.ok(file.contents.includes("email TEXT NOT NULL UNIQUE"));
  assert.ok(file.contents.includes("REFERENCES users(id)"));
});

test("Prisma output is a complete schema.prisma", () => {
  const [file] = designSchema({ format: "prisma", tables: [USERS] });
  assert.equal(file.path, "schema.prisma");
  assert.ok(file.contents.includes('provider = "prisma-client-js"'));
  assert.ok(file.contents.includes("model Users {"));
  assert.ok(file.contents.includes("id String @id"));
});

test("Django ORM output imports models and emits a class", () => {
  const [file] = designSchema({ format: "django_orm", tables: [USERS] });
  assert.equal(file.path, "models.py");
  assert.ok(file.contents.includes("from django.db import models"));
  assert.ok(file.contents.includes("class Users(models.Model):"));
  assert.ok(file.contents.includes("models.UUIDField(primary_key=True)"));
});

test("SQLAlchemy output uses a DeclarativeBase", () => {
  const [file] = designSchema({ format: "sqlalchemy", tables: [USERS, POSTS] });
  assert.equal(file.path, "models.py");
  assert.ok(file.contents.includes("DeclarativeBase"));
  assert.ok(file.contents.includes("class Posts(Base):"));
  assert.ok(file.contents.includes("ForeignKey('users.id')"));
});

test("empty tables list is rejected", () => {
  assert.throws(() => designSchema({ format: "sql", tables: [] }));
});
