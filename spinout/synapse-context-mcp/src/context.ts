// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.

/**
 * Context optimization — the dependency-free core of synapse-context-mcp.
 *
 * Every team hits the 200k-token-context wall. This module compresses, dedupes,
 * and summarizes conversation history as infrastructure: importance-ranked
 * compression, near-duplicate removal via Jaccard similarity, and tight
 * agent-to-agent handoff summaries. Pure functions, Node built-ins only.
 */

/** Compression strategy. */
export type Strategy = "semantic" | "decision_tree" | "hierarchical" | "auto";

/** Result of {@link compress}. */
export interface CompressionResult {
  content: string;
  tokensBefore: number;
  tokensAfter: number;
  reductionPct: number;
  strategy: Strategy;
}

/** Result of {@link dedupe}. */
export interface DedupeResult {
  content: string;
  keptLines: number;
  removedLines: number;
}

/** A shared-summary record produced by {@link shareSummary}. */
export interface SharedSummary {
  summary: string;
  scope: "team" | "project" | "global";
  sharedAt: string;
}

/** An item considered for {@link evict}. */
export interface EvictItem {
  key: string;
  importance: number;
  lastUsedAt: number;
}

const CHARS_PER_TOKEN = 4;
const IMPORTANCE_KEYWORDS = [
  "decision", "decided", "chose", "because", "error", "fail", "failed",
  "must", "todo", "fixme", "important", "warning", "bug", "->", "root cause",
];

/** Estimate the token count of `text` (~4 chars/token). */
export function estimateTokens(text: string): number {
  const chars = [...text].length;
  return chars === 0 ? 0 : Math.ceil(chars / CHARS_PER_TOKEN);
}

function isHeading(line: string): boolean {
  return /^\s{0,3}(#{1,6}\s|[-*]\s|\d+\.\s)/.test(line) || /:\s*$/.test(line.trim());
}

function normalize(line: string): string {
  return line.toLowerCase().replace(/\s+/g, " ").trim();
}

function tokenSet(line: string): Set<string> {
  return new Set(normalize(line).split(" ").filter(Boolean));
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 && b.size === 0) return 1;
  let intersection = 0;
  for (const token of a) if (b.has(token)) intersection += 1;
  const union = a.size + b.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

function scoreLine(line: string, strategy: Strategy): number {
  const lower = line.toLowerCase();
  let score = Math.min(line.trim().length, 40) / 40; // base: prefer substantive lines
  if (IMPORTANCE_KEYWORDS.some((kw) => lower.includes(kw))) score += 2;
  if (isHeading(line)) score += strategy === "hierarchical" ? 3 : 1;
  if (strategy === "decision_tree" && /decid|chose|because|->/.test(lower)) score += 2;
  return score;
}

/** Remove duplicate / near-duplicate lines (Jaccard >= `similarityThreshold`). */
export function dedupe(content: string, similarityThreshold = 0.9): DedupeResult {
  const lines = content.split("\n");
  const keptLines: string[] = [];
  const keptSets: Set<string>[] = [];
  let removed = 0;

  for (const line of lines) {
    if (line.trim() === "") {
      keptLines.push(line);
      continue;
    }
    const set = tokenSet(line);
    const isDuplicate = keptSets.some((kept) => jaccard(set, kept) >= similarityThreshold);
    if (isDuplicate) {
      removed += 1;
    } else {
      keptLines.push(line);
      keptSets.push(set);
    }
  }

  return {
    content: keptLines.join("\n"),
    keptLines: keptLines.filter((l) => l.trim() !== "").length,
    removedLines: removed,
  };
}

/** Compress `input` toward `targetTokens` by keeping the most important lines. */
export function compress(
  input: string | string[],
  targetTokens: number,
  strategy: Strategy = "auto",
): CompressionResult {
  const text = Array.isArray(input) ? input.join("\n") : input;
  const lines = text.split("\n");
  const tokensBefore = estimateTokens(text);

  const resolved: Strategy =
    strategy === "auto" ? (lines.some(isHeading) ? "hierarchical" : "semantic") : strategy;

  const ranked = lines
    .map((line, index) => ({ line, index, score: scoreLine(line, resolved) }))
    .filter((entry) => entry.line.trim() !== "")
    .sort((a, b) => b.score - a.score);

  const selected: typeof ranked = [];
  let budget = 0;
  for (const entry of ranked) {
    const cost = estimateTokens(entry.line) + 1; // +1 for the newline
    if (budget + cost > targetTokens && selected.length > 0) continue;
    selected.push(entry);
    budget += cost;
  }

  const content = selected
    .sort((a, b) => a.index - b.index)
    .map((entry) => entry.line)
    .join("\n");
  const tokensAfter = estimateTokens(content);

  return {
    content,
    tokensBefore,
    tokensAfter,
    reductionPct:
      tokensBefore === 0 ? 0 : Math.round(((tokensBefore - tokensAfter) / tokensBefore) * 1000) / 10,
    strategy: resolved,
  };
}

/** Produce a tight handoff summary of `context` for `targetAgent`. */
export function summarizeForHandoff(context: string, targetAgent: string): string {
  const important = context
    .split("\n")
    .map((line) => ({ line: line.trim(), score: scoreLine(line, "semantic") }))
    .filter((entry) => entry.line !== "")
    .sort((a, b) => b.score - a.score)
    .slice(0, 8)
    .map((entry) => `- ${entry.line}`);

  return [`Handoff to ${targetAgent}:`, ...important].join("\n");
}

/** Wrap a summary for sharing into a memory scope. */
export function shareSummary(
  summary: string,
  scope: "team" | "project" | "global",
): SharedSummary {
  return { summary, scope, sharedAt: new Date().toISOString() };
}

/** Evict items down to `keep`, choosing victims by `strategy`. */
export function evict(
  items: EvictItem[],
  strategy: "lru" | "importance" | "age",
  keep: number,
): { kept: EvictItem[]; evicted: EvictItem[] } {
  const sorted = [...items];
  if (strategy === "lru" || strategy === "age") {
    // Keep the most-recently-used; evict the oldest.
    sorted.sort((a, b) => b.lastUsedAt - a.lastUsedAt);
  } else {
    // Keep the most important.
    sorted.sort((a, b) => b.importance - a.importance);
  }
  return { kept: sorted.slice(0, keep), evicted: sorted.slice(keep) };
}
