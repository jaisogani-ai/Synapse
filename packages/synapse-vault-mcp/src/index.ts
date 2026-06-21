#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Entry point for synapse-secret-vault-mcp. Starts the vault MCP server over
 * stdio so any MCP client (Claude Code, Cursor, …) can use it.
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { createVaultServer } from "./server.ts";

const server = createVaultServer();
const transport = new StdioServerTransport();
await server.connect(transport);
