// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * `backend.design_queue` — async job queue scaffold with retries, DLQ, and
 * (where supported) scheduling.
 *
 * One backend per call. Output is runnable starter code, not pseudocode.
 */

import type { GeneratedFile, QueueBackend } from "./types.ts";

/** Options for {@link designQueue}. */
export interface QueueOptions {
  use_case: string;
  backend: QueueBackend;
}

/** Build the queue scaffold for `backend`. */
export function designQueue(options: QueueOptions): GeneratedFile[] {
  switch (options.backend) {
    case "redis": return redisQueue(options.use_case);
    case "rabbitmq": return rabbitQueue(options.use_case);
    case "sqs": return sqsQueue(options.use_case);
    case "kafka": return kafkaQueue(options.use_case);
  }
}

function redisQueue(useCase: string): GeneratedFile[] {
  return [
    {
      path: "queue/redis_queue.py",
      contents: `# SPDX-License-Identifier: Apache-2.0
"""Redis (RQ) job queue: ${useCase}."""
from __future__ import annotations

import redis
from rq import Queue, Retry
from rq.job import Job


_connection = redis.from_url("redis://localhost:6379/0")
main_queue: Queue = Queue("main", connection=_connection)
dlq: Queue = Queue("dead-letter", connection=_connection)


def enqueue(func, *args, max_retries: int = 3, **kwargs) -> str:
    """Enqueue 'func' with exponential-backoff retries."""
    job: Job = main_queue.enqueue(
        func,
        *args,
        retry=Retry(max=max_retries, interval=[10, 30, 90]),
        **kwargs,
    )
    return job.id


def move_to_dlq(job_id: str, reason: str) -> None:
    """Move a permanently-failed job to the dead-letter queue."""
    job = Job.fetch(job_id, connection=_connection)
    dlq.enqueue("noop", job.func_name, *job.args, meta={"reason": reason})
`,
    },
    {
      path: "queue/worker.py",
      contents: `# SPDX-License-Identifier: Apache-2.0
"""Worker entrypoint. Run with: python queue/worker.py"""
from rq import Worker

from queue.redis_queue import _connection, dlq, main_queue


if __name__ == "__main__":
    Worker([main_queue, dlq], connection=_connection).work()
`,
    },
  ];
}

function rabbitQueue(useCase: string): GeneratedFile[] {
  return [
    {
      path: "queue/rabbit_queue.py",
      contents: `# SPDX-License-Identifier: Apache-2.0
"""RabbitMQ producer/consumer: ${useCase}."""
import json
import pika

PARAMS = pika.URLParameters("amqp://guest:guest@localhost:5672/")
MAIN_QUEUE = "main"
DLQ = "main.dlq"


def declare(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    """Declare main queue + DLQ exchange + binding (idempotent)."""
    channel.exchange_declare(exchange="dlx", exchange_type="direct", durable=True)
    channel.queue_declare(queue=DLQ, durable=True)
    channel.queue_bind(queue=DLQ, exchange="dlx", routing_key=MAIN_QUEUE)
    channel.queue_declare(
        queue=MAIN_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": "dlx", "x-dead-letter-routing-key": MAIN_QUEUE},
    )


def publish(body: dict) -> None:
    """Publish a JSON message to the main queue."""
    with pika.BlockingConnection(PARAMS) as conn:
        channel = conn.channel()
        declare(channel)
        channel.basic_publish(
            exchange="",
            routing_key=MAIN_QUEUE,
            body=json.dumps(body).encode(),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
`,
    },
  ];
}

function sqsQueue(useCase: string): GeneratedFile[] {
  return [
    {
      path: "queue/sqs_queue.py",
      contents: `# SPDX-License-Identifier: Apache-2.0
"""AWS SQS producer/consumer with DLQ redrive: ${useCase}."""
import json
import os

import boto3

_sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
MAIN_URL = os.environ["SQS_MAIN_URL"]
DLQ_URL = os.environ.get("SQS_DLQ_URL", "")


def send(body: dict, delay_seconds: int = 0) -> str:
    """Send a JSON message to the main queue."""
    response = _sqs.send_message(
        QueueUrl=MAIN_URL,
        MessageBody=json.dumps(body),
        DelaySeconds=delay_seconds,
    )
    return response["MessageId"]


def poll(max_messages: int = 10, wait_seconds: int = 20) -> list[dict]:
    """Long-poll up to 'max_messages' messages."""
    response = _sqs.receive_message(
        QueueUrl=MAIN_URL,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_seconds,
    )
    return [json.loads(m["Body"]) for m in response.get("Messages", [])]
`,
    },
  ];
}

function kafkaQueue(useCase: string): GeneratedFile[] {
  return [
    {
      path: "queue/kafka_queue.py",
      contents: `# SPDX-License-Identifier: Apache-2.0
"""Kafka producer/consumer: ${useCase}."""
import json
from confluent_kafka import Consumer, Producer

BOOTSTRAP = "localhost:9092"
MAIN_TOPIC = "main"
DLQ_TOPIC = "main.dlq"


_producer = Producer({"bootstrap.servers": BOOTSTRAP})


def publish(body: dict, key: str | None = None) -> None:
    """Publish a JSON message to the main topic."""
    _producer.produce(MAIN_TOPIC, json.dumps(body).encode(), key=key)
    _producer.flush()


def consumer(group_id: str = "default") -> Consumer:
    """Build a consumer subscribed to the main topic."""
    c = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": group_id,
        "auto.offset.reset": "earliest",
    })
    c.subscribe([MAIN_TOPIC])
    return c
`,
    },
  ];
}
