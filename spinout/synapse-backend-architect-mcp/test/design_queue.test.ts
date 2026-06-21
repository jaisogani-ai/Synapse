// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/** Tests for the queue designer. */

import { test } from "node:test";
import assert from "node:assert/strict";

import { designQueue } from "../src/design_queue.ts";

test("redis queue has main + dead-letter queues and a worker entry", () => {
  const files = designQueue({ use_case: "image processing", backend: "redis" });
  const paths = files.map((f) => f.path);
  assert.ok(paths.includes("queue/redis_queue.py"));
  assert.ok(paths.includes("queue/worker.py"));
  const main = files[0].contents;
  assert.ok(main.includes("from rq import Queue, Retry"));
  assert.ok(main.includes('Queue("main"'));
  assert.ok(main.includes('Queue("dead-letter"'));
});

test("rabbitmq queue declares DLX + DLQ binding", () => {
  const [file] = designQueue({ use_case: "billing", backend: "rabbitmq" });
  assert.ok(file.contents.includes('exchange_declare(exchange="dlx"'));
  assert.ok(file.contents.includes("x-dead-letter-exchange"));
});

test("sqs queue uses boto3 with long polling", () => {
  const [file] = designQueue({ use_case: "ingest", backend: "sqs" });
  assert.ok(file.contents.includes('boto3.client("sqs"'));
  assert.ok(file.contents.includes("WaitTimeSeconds"));
});

test("kafka queue uses confluent_kafka producer + consumer", () => {
  const [file] = designQueue({ use_case: "events", backend: "kafka" });
  assert.ok(file.contents.includes("from confluent_kafka import"));
  assert.ok(file.contents.includes("Producer"));
  assert.ok(file.contents.includes("Consumer"));
});
