#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Entry point for synapse-memory-mcp. Serves the 8-tier memory access tools
 * over stdio, bridging to the daemon at `SYNAPSE_SOCKET` (default
 * `/tmp/synapse.sock`).
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { createMemoryServer } from "./server.ts";

const server = createMemoryServer();
const transport = new StdioServerTransport();
await server.connect(transport);
