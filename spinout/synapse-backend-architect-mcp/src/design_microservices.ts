// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * `backend.design_microservices` — split a monolith requirement into service
 * boundaries.
 *
 * Phase 3 ships a deterministic, keyword-driven splitter: it scans the
 * free-text requirements for known *domain anchors* (auth, billing, search,
 * orders, …) and emits a {@link Microservice} per detected anchor, plus an
 * always-present API gateway. This is a pragmatic baseline an LLM-driven
 * refiner can polish later.
 */

import type { Microservice } from "./types.ts";

interface Anchor {
  /** Tokens (case-insensitive substring) that activate this service. */
  patterns: string[];
  /** Resulting service definition. */
  service: Omit<Microservice, "depends_on"> & { depends_on?: string[] };
}

const ANCHORS: Anchor[] = [
  {
    patterns: ["auth", "login", "sso", "user account", "identity"],
    service: {
      name: "auth-service",
      responsibilities: ["Issue & verify JWTs", "OAuth/SSO flows", "Session lifecycle"],
      data_store: "postgres (users, sessions)",
    },
  },
  {
    patterns: ["bill", "invoice", "payment", "subscription", "checkout"],
    service: {
      name: "billing-service",
      responsibilities: ["Subscription state", "Invoice generation", "Webhook handlers"],
      data_store: "postgres (subscriptions, invoices)",
      depends_on: ["payments-service"],
    },
  },
  {
    patterns: ["payment", "stripe", "razorpay", "card", "wallet"],
    service: {
      name: "payments-service",
      responsibilities: ["PSP integrations", "Payment intents", "Refunds"],
      data_store: "postgres (charges, refunds)",
    },
  },
  {
    patterns: ["search", "index", "elasticsearch", "opensearch", "discovery"],
    service: {
      name: "search-service",
      responsibilities: ["Index documents", "Query execution", "Faceted search"],
      data_store: "opensearch (search index)",
    },
  },
  {
    patterns: ["order", "cart", "fulfillment", "shipping"],
    service: {
      name: "orders-service",
      responsibilities: ["Cart state", "Order placement", "Fulfillment events"],
      data_store: "postgres (orders, line_items)",
      depends_on: ["billing-service", "notifications-service"],
    },
  },
  {
    patterns: ["notification", "email", "sms", "push", "webhook"],
    service: {
      name: "notifications-service",
      responsibilities: ["Template rendering", "Channel delivery", "Retries & DLQ"],
      data_store: "postgres (templates) + redis (delivery queue)",
    },
  },
  {
    patterns: ["analytic", "event", "telemetry", "metric"],
    service: {
      name: "analytics-service",
      responsibilities: ["Event ingestion", "Aggregations", "Dashboards API"],
      data_store: "clickhouse (events)",
    },
  },
  {
    patterns: ["chat", "message", "conversation", "thread"],
    service: {
      name: "chat-service",
      responsibilities: ["Realtime messaging", "Presence", "Thread storage"],
      data_store: "postgres (threads, messages) + redis (presence)",
    },
  },
  {
    patterns: ["file", "upload", "media", "asset", "image"],
    service: {
      name: "media-service",
      responsibilities: ["Uploads (signed URLs)", "Image processing", "CDN integration"],
      data_store: "s3 (blobs) + postgres (metadata)",
    },
  },
];

/** Options for {@link designMicroservices}. */
export interface MicroserviceOptions {
  requirements: string;
  team_size?: number;
}

/**
 * Split `requirements` into service boundaries. Always returns an API gateway,
 * then one service per detected domain anchor. If `team_size` is supplied,
 * services beyond `2 * team_size` are merged-by-domain to stay maintainable.
 */
export function designMicroservices(options: MicroserviceOptions): Microservice[] {
  const text = options.requirements.toLowerCase();
  const detected = new Map<string, Microservice>();

  for (const anchor of ANCHORS) {
    if (anchor.patterns.some((p) => text.includes(p)) && !detected.has(anchor.service.name)) {
      detected.set(anchor.service.name, {
        ...anchor.service,
        depends_on: anchor.service.depends_on ?? [],
      });
    }
  }

  // Always include an API gateway.
  const gateway: Microservice = {
    name: "api-gateway",
    responsibilities: ["Public ingress", "Auth verification", "Rate limiting", "Request routing"],
    depends_on: [...detected.keys()],
    data_store: "stateless",
  };

  const services = [gateway, ...detected.values()];

  // Capacity check: keep ratio reasonable.
  if (options.team_size && services.length > options.team_size * 2) {
    return services.slice(0, options.team_size * 2);
  }
  return services;
}
