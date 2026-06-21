// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Unix-socket client for the Synapse daemon — the core of synapse-memory-mcp.
 *
 * Speaks the Synapse Protocol ({@link ./protocol.ts}) over the daemon's Unix
 * socket: one request line out, one response line in. Uses only `node:net`, so
 * it is testable against an in-process fake socket without the Rust daemon.
 */

import net from "node:net";

import {
  type MemoryTier,
  type SynapseMessage,
  encodeLine,
  health,
  memoryRead,
  memorySearch,
  memoryWrite,
  parseLine,
  ping,
} from "./protocol.ts";

/** Default daemon socket path (matches the daemon's default). */
export const DEFAULT_SOCKET_PATH = "/tmp/synapse.sock";

/** A one-request/one-response client for the Synapse daemon. */
export class SynapseClient {
  private socketPath: string;
  private sender: string;

  /** Create a client targeting `socketPath`, identifying as `sender`. */
  constructor(socketPath: string = DEFAULT_SOCKET_PATH, sender = "synapse-memory-mcp") {
    this.socketPath = socketPath;
    this.sender = sender;
  }

  /** Send one request and resolve with the daemon's response message. */
  request(message: SynapseMessage): Promise<SynapseMessage> {
    return new Promise((resolve, reject) => {
      const socket = net.createConnection(this.socketPath);
      let buffer = "";
      let settled = false;

      const fail = (error: Error) => {
        if (settled) return;
        settled = true;
        socket.destroy();
        reject(error);
      };

      socket.on("connect", () => socket.write(encodeLine(message)));
      socket.on("data", (chunk) => {
        buffer += chunk.toString("utf8");
        const newline = buffer.indexOf("\n");
        if (newline !== -1 && !settled) {
          settled = true;
          socket.end();
          try {
            resolve(parseLine(buffer.slice(0, newline)));
          } catch (error) {
            reject(error as Error);
          }
        }
      });
      socket.on("error", fail);
      socket.on("close", () => fail(new Error("connection closed before a response")));
    });
  }

  /** Liveness check. */
  ping(): Promise<SynapseMessage> {
    return this.request(ping(this.sender));
  }

  /** Daemon + memory health. */
  health(): Promise<SynapseMessage> {
    return this.request(health(this.sender));
  }

  /** Read a key from a memory tier. */
  readMemory(tier: MemoryTier, key: string): Promise<SynapseMessage> {
    return this.request(memoryRead(this.sender, tier, key));
  }

  /** Write a value to a memory tier. */
  writeMemory(tier: MemoryTier, key: string, value: string): Promise<SynapseMessage> {
    return this.request(memoryWrite(this.sender, tier, key, value));
  }

  /** Search a memory tier. */
  searchMemory(tier: MemoryTier, query: string): Promise<SynapseMessage> {
    return this.request(memorySearch(this.sender, tier, query));
  }
}
