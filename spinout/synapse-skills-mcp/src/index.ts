#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Entry point for synapse-skills-mcp. Serves the skill registry + invoker
 * tools over stdio.
 */

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { createSkillsServer } from "./server.ts";

const server = createSkillsServer();
const transport = new StdioServerTransport();
await server.connect(transport);
