// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Skill model — the dependency-free core of synapse-skills-mcp.
 *
 * A *skill* is a parameterized runnable unit, mirroring the Universal SKILL.md
 * format that travels across Synapse adapters. Each skill declares an id,
 * version, capabilities it requires (see `synapse.security.capabilities`), an
 * input schema, and an in-process handler.
 *
 * Skills with `requiresSandbox: true` must be invoked via the daemon sandbox.
 * The registry will refuse to invoke them in-process (see {@link SkillRegistry.invoke}).
 */

/** A skill's input schema (loose JSON Schema subset; validation is structural). */
export interface SkillSchema {
  /** Required input keys, all typed as strings or numbers at this layer. */
  required?: string[];
  /** Optional input keys, same constraint. */
  optional?: string[];
}

/** A skill definition. */
export interface Skill {
  id: string;
  name: string;
  version: string;
  description: string;
  /** Capability strings the caller must have granted (e.g. `"memory.read"`). */
  capabilities: string[];
  /** Free-form tags for search. */
  tags: string[];
  /** Input schema for {@link invoke}. */
  inputSchema: SkillSchema;
  /** Whether this skill must run in the sandbox (refused in-process). */
  requiresSandbox: boolean;
  /** In-process handler. Called only when `requiresSandbox` is false. */
  handler: (input: Record<string, unknown>) => Promise<SkillResult> | SkillResult;
}

/** The result of invoking a skill. */
export interface SkillResult {
  ok: boolean;
  data?: unknown;
  error?: string;
}

/** A search result. */
export interface SkillSummary {
  id: string;
  name: string;
  version: string;
  description: string;
  tags: string[];
  capabilities: string[];
  requiresSandbox: boolean;
}

function toSummary(skill: Skill): SkillSummary {
  return {
    id: skill.id,
    name: skill.name,
    version: skill.version,
    description: skill.description,
    tags: skill.tags,
    capabilities: skill.capabilities,
    requiresSandbox: skill.requiresSandbox,
  };
}

/**
 * Pure JSON-Schema-lite validation: enforces that every required key is
 * present. Returns a list of missing keys, or `[]` if all required are present.
 */
export function validateInput(schema: SkillSchema, input: Record<string, unknown>): string[] {
  const required = schema.required ?? [];
  return required.filter((key) => !(key in input));
}

/** An in-memory skill registry with search + invocation. */
export class SkillRegistry {
  private skills: Map<string, Skill> = new Map();

  /** Register (or replace) a skill. */
  register(skill: Skill): void {
    if (!skill.id) throw new Error("skill id is required");
    if (!skill.version) throw new Error("skill version is required");
    this.skills.set(skill.id, skill);
  }

  /** Whether a skill is registered. */
  has(id: string): boolean {
    return this.skills.has(id);
  }

  /** Look up a skill by id. */
  get(id: string): Skill | undefined {
    return this.skills.get(id);
  }

  /** Number of registered skills. */
  size(): number {
    return this.skills.size;
  }

  /** Summaries of all registered skills, sorted by id. */
  list(): SkillSummary[] {
    return [...this.skills.values()]
      .map(toSummary)
      .sort((a, b) => a.id.localeCompare(b.id));
  }

  /**
   * Search skills by free text. Matches against id, name, description, and
   * tags (case-insensitive substring). Empty `query` returns everything.
   */
  search(query: string): SkillSummary[] {
    const needle = query.trim().toLowerCase();
    if (needle === "") return this.list();
    return this.list().filter((skill) => {
      const haystack = [skill.id, skill.name, skill.description, ...skill.tags]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }

  /**
   * Invoke a skill in-process.
   *
   * Returns `{ ok: false, error }` on missing skill, missing required input,
   * or sandbox-required violation. Otherwise calls the skill's handler.
   */
  async invoke(id: string, input: Record<string, unknown>): Promise<SkillResult> {
    const skill = this.skills.get(id);
    if (!skill) return { ok: false, error: `skill not found: ${id}` };
    if (skill.requiresSandbox) {
      return { ok: false, error: `skill '${id}' requires sandbox; invoke via daemon` };
    }
    const missing = validateInput(skill.inputSchema, input);
    if (missing.length > 0) {
      return { ok: false, error: `missing required input: ${missing.join(", ")}` };
    }
    try {
      return await skill.handler(input);
    } catch (error) {
      return { ok: false, error: (error as Error).message };
    }
  }
}

/** Construct the registry pre-loaded with the built-in skill catalog. */
export function createDefaultRegistry(): SkillRegistry {
  const registry = new SkillRegistry();
  for (const skill of BUILTIN_SKILLS) registry.register(skill);
  return registry;
}

// ---- Built-in skill catalog -----------------------------------------------
//
// Real handlers (not stubs). Each is small, dependency-free, and useful on its
// own — they double as examples of what a Synapse skill looks like.

const slugify: Skill = {
  id: "text.slugify",
  name: "Slugify text",
  version: "1.0.0",
  description: "Convert text into a URL-safe slug (lowercase, dashes).",
  capabilities: [],
  tags: ["text", "url", "transform"],
  inputSchema: { required: ["text"] },
  requiresSandbox: false,
  handler: ({ text }) => {
    const slug = String(text)
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[^\w\s-]/g, "")
      .trim()
      .replace(/[\s_-]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return { ok: true, data: { slug } };
  },
};

const titleCase: Skill = {
  id: "text.title_case",
  name: "Title case",
  version: "1.0.0",
  description: "Capitalize each word of the input text.",
  capabilities: [],
  tags: ["text", "transform"],
  inputSchema: { required: ["text"] },
  requiresSandbox: false,
  handler: ({ text }) => {
    const out = String(text)
      .split(/\s+/)
      .map((word) => (word.length ? word[0].toUpperCase() + word.slice(1).toLowerCase() : word))
      .join(" ");
    return { ok: true, data: { text: out } };
  },
};

const jsonFormat: Skill = {
  id: "json.format",
  name: "Format JSON",
  version: "1.0.0",
  description: "Pretty-print a JSON document with a given indent (default 2).",
  capabilities: [],
  tags: ["json", "format"],
  inputSchema: { required: ["json"], optional: ["indent"] },
  requiresSandbox: false,
  handler: ({ json, indent }) => {
    const parsed = JSON.parse(String(json));
    const spaces = typeof indent === "number" ? indent : 2;
    return { ok: true, data: { formatted: JSON.stringify(parsed, null, spaces) } };
  },
};

const wordCount: Skill = {
  id: "text.word_count",
  name: "Word count",
  version: "1.0.0",
  description: "Count words, lines, and characters in the input.",
  capabilities: [],
  tags: ["text", "metrics"],
  inputSchema: { required: ["text"] },
  requiresSandbox: false,
  handler: ({ text }) => {
    const t = String(text);
    return {
      ok: true,
      data: {
        words: (t.trim().match(/\S+/g) ?? []).length,
        lines: t.split("\n").length,
        chars: [...t].length,
      },
    };
  },
};

const sandboxedShell: Skill = {
  id: "shell.exec",
  name: "Execute shell command",
  version: "1.0.0",
  description: "Run a whitelisted shell command. Always sandbox-only.",
  capabilities: ["shell.exec"],
  tags: ["shell", "sandbox"],
  inputSchema: { required: ["command"] },
  requiresSandbox: true,
  handler: () => ({ ok: false, error: "must route through sandbox" }),
};

/** The built-in skill catalog. */
export const BUILTIN_SKILLS: Skill[] = [slugify, titleCase, jsonFormat, wordCount, sandboxedShell];
