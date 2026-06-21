// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * AES-256-GCM secret vault — the dependency-free core of synapse-secret-vault-mcp.
 *
 * Agents NEVER receive raw API keys. They request a scoped, time-limited
 * *credential proxy*; only the daemon resolves a proxy back to the real secret
 * at the network layer. Secrets are encrypted at rest with AES-256-GCM
 * (authenticated encryption — tampering is detected on decrypt). Every access
 * is recorded in an append-only audit log; secret values are never logged.
 *
 * This module uses only Node's built-in `node:crypto`, so it has zero runtime
 * dependencies and is fully unit-testable without the MCP SDK.
 */

import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

const ALGORITHM = "aes-256-gcm";
const KEY_BYTES = 32;
const IV_BYTES = 12;
/** Maximum lifetime of a credential proxy (seconds). */
export const MAX_PROXY_SECONDS = 3600;

/** Arbitrary string metadata stored alongside a secret. */
export type SecretMetadata = Record<string, string>;

/** A secret encrypted at rest. */
export interface StoredSecret {
  name: string;
  ciphertext: string; // base64
  iv: string; // base64
  authTag: string; // base64
  metadata: SecretMetadata;
  createdAt: string;
  version: number;
}

/** A scoped, time-limited credential proxy handed to an agent. */
export interface CredentialProxy {
  proxyUrl: string;
  proxyToken: string;
  service: string;
  expiresAt: string; // ISO-8601
}

/** One audit-log entry. Never contains a secret value. */
export interface AuditEntry {
  action: string;
  name: string;
  at: string;
  purpose?: string;
}

/** A detected (redacted) secret exposure. */
export interface ExposureFinding {
  name: string;
  provider: string;
  preview: string;
}

interface ExposurePattern {
  name: string;
  provider: string;
  regex: RegExp;
}

const EXPOSURE_PATTERNS: ExposurePattern[] = [
  { name: "AWS Access Key ID", provider: "AWS", regex: /\bAKIA[0-9A-Z]{16}\b/ },
  { name: "GitHub PAT", provider: "GitHub", regex: /\bghp_[0-9A-Za-z]{36}\b/ },
  { name: "Anthropic API Key", provider: "Anthropic", regex: /\bsk-ant-[A-Za-z0-9-]{20,}\b/ },
  { name: "OpenAI API Key", provider: "OpenAI", regex: /\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}\b/ },
  { name: "Stripe Live Secret", provider: "Stripe", regex: /\bsk_live_[0-9A-Za-z]{24,}\b/ },
  { name: "Slack Token", provider: "Slack", regex: /\bxox[baprs]-[0-9A-Za-z-]{10,48}\b/ },
  { name: "Google API Key", provider: "GCP", regex: /\bAIza[0-9A-Za-z\-_]{35}\b/ },
  { name: "Private Key", provider: "Crypto", regex: /-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----/ },
];

/** Redact a secret to a safe preview (never the full value). */
export function redact(secret: string): string {
  if (secret.length <= 8) return "*".repeat(secret.length);
  return `${secret.slice(0, 4)}…[redacted:${secret.length} chars]`;
}

/** An in-memory AES-256-GCM secret vault. */
export class SecretVault {
  private key: Buffer;
  private store: Map<string, StoredSecret> = new Map();
  private previous: Map<string, { secret: StoredSecret; expiresAt: number }> = new Map();
  private proxies: Map<string, { name: string; expiresAt: number }> = new Map();
  private auditEntries: AuditEntry[] = [];

  /** Create a vault. A random 256-bit master key is generated if none is given. */
  constructor(masterKey?: Buffer) {
    if (masterKey && masterKey.length !== KEY_BYTES) {
      throw new Error(`master key must be ${KEY_BYTES} bytes`);
    }
    this.key = masterKey ?? randomBytes(KEY_BYTES);
  }

  /** Store (or overwrite) a secret, encrypted at rest. */
  storeSecret(name: string, value: string, metadata: SecretMetadata = {}): void {
    if (!name) throw new Error("secret name is required");
    const existing = this.store.get(name);
    const encrypted = this.encrypt(value);
    this.store.set(name, {
      name,
      ...encrypted,
      metadata,
      createdAt: new Date().toISOString(),
      version: (existing?.version ?? 0) + 1,
    });
    this.log("store", name);
  }

  /** Decrypt and return a secret value. Throws if missing or tampered. */
  retrieve(name: string): string {
    const secret = this.store.get(name);
    if (!secret) throw new Error(`secret not found: ${name}`);
    this.log("retrieve", name);
    return this.decrypt(secret);
  }

  /** Whether a secret exists. */
  has(name: string): boolean {
    return this.store.has(name);
  }

  /** Rotate a secret; the previous version stays valid for `graceSeconds`. */
  rotate(name: string, newValue: string, graceSeconds = 300): void {
    const old = this.store.get(name);
    if (old) {
      this.previous.set(name, { secret: old, expiresAt: Date.now() + graceSeconds * 1000 });
    }
    this.storeSecret(name, newValue, old?.metadata ?? {});
    this.log("rotate", name);
  }

  /** Read the pre-rotation value, if still within its grace window. */
  peekPrevious(name: string, now: number = Date.now()): string | null {
    const prior = this.previous.get(name);
    if (!prior || now >= prior.expiresAt) return null;
    return this.decrypt(prior.secret);
  }

  /** Issue a scoped, time-limited proxy for a service's secret. */
  requestCredential(opts: {
    service: string;
    purpose: string;
    durationSeconds?: number;
    scope?: string;
  }): CredentialProxy {
    if (!opts.purpose) throw new Error("purpose is required (it is audited)");
    if (!this.store.has(opts.service)) {
      throw new Error(`no secret for service: ${opts.service}`);
    }
    const ttl = Math.min(opts.durationSeconds ?? MAX_PROXY_SECONDS, MAX_PROXY_SECONDS);
    const token = randomBytes(24).toString("hex");
    const expiresAt = Date.now() + ttl * 1000;
    this.proxies.set(token, { name: opts.service, expiresAt });
    this.log("issue_proxy", opts.service, opts.purpose);
    return {
      proxyUrl: `synapse+vault://proxy/${token}`,
      proxyToken: token,
      service: opts.service,
      expiresAt: new Date(expiresAt).toISOString(),
    };
  }

  /** Resolve a proxy token to its secret (daemon-side only). `null` if expired. */
  resolveProxy(token: string, now: number = Date.now()): string | null {
    const proxy = this.proxies.get(token);
    if (!proxy || now >= proxy.expiresAt) return null;
    this.log("resolve_proxy", proxy.name);
    return this.decrypt(this.store.get(proxy.name)!);
  }

  /** Immediately revoke a secret; all active proxies for it die. */
  revoke(name: string, reason: string): void {
    this.store.delete(name);
    this.previous.delete(name);
    for (const [token, proxy] of this.proxies) {
      if (proxy.name === name) this.proxies.delete(token);
    }
    this.auditEntries.push({ action: "revoke", name, at: new Date().toISOString(), purpose: reason });
  }

  /** Return audit entries, optionally filtered to one secret. */
  auditLog(name?: string): AuditEntry[] {
    return name ? this.auditEntries.filter((e) => e.name === name) : [...this.auditEntries];
  }

  /** Scan content for leaked secrets before it is committed. */
  detectExposure(content: string): ExposureFinding[] {
    const findings: ExposureFinding[] = [];
    for (const pattern of EXPOSURE_PATTERNS) {
      const match = pattern.regex.exec(content);
      if (match) {
        findings.push({ name: pattern.name, provider: pattern.provider, preview: redact(match[0]) });
      }
    }
    return findings;
  }

  private encrypt(value: string): { ciphertext: string; iv: string; authTag: string } {
    const iv = randomBytes(IV_BYTES);
    const cipher = createCipheriv(ALGORITHM, this.key, iv);
    const ciphertext = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
    return {
      ciphertext: ciphertext.toString("base64"),
      iv: iv.toString("base64"),
      authTag: cipher.getAuthTag().toString("base64"),
    };
  }

  private decrypt(secret: StoredSecret): string {
    const decipher = createDecipheriv(ALGORITHM, this.key, Buffer.from(secret.iv, "base64"));
    decipher.setAuthTag(Buffer.from(secret.authTag, "base64"));
    const plaintext = Buffer.concat([
      decipher.update(Buffer.from(secret.ciphertext, "base64")),
      decipher.final(),
    ]);
    return plaintext.toString("utf8");
  }

  private log(action: string, name: string, purpose?: string): void {
    this.auditEntries.push({ action, name, at: new Date().toISOString(), purpose });
  }
}
