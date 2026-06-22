# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Patch review workflow — unified diffs as A2A artifacts.

A reviewing agent (Cursor, Codex, Claude Code, …) produces a code change.
Synapse carries that change as a **unified diff** so the sender can:

  1. *see* the proposed change as a standard diff (review),
  2. *apply* it locally with context validation (never blindly), or
  3. *comment* and request a revision, looping until accepted.

Diff generation uses the stdlib :mod:`difflib` (no new dependencies). The
applier is intentionally strict: every context and removed line must match
the current file content exactly, or the apply is refused — a patch never
silently corrupts a file. Because we both generate and apply, the formats
are guaranteed compatible.

This module is pure functions over strings. Threading state (the
comment → revise → resubmit loop) lives in :class:`PatchThread`.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PatchSummary:
    """Human-review summary of a unified diff."""

    filename: str
    added: int
    removed: int
    hunks: int


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of :func:`apply_patch`."""

    ok: bool
    applied_text: str = ""
    reason: str = ""


def make_patch(
    old_text: str,
    new_text: str,
    filename: str = "file",
    *,
    context: int = 3,
) -> str:
    """Return a unified diff turning ``old_text`` into ``new_text``.

    The diff uses ``a/<filename>`` / ``b/<filename>`` headers so it reads like
    a ``git diff`` and is recognised by standard tooling.
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=context,
    )
    return "".join(diff)


def summarize_patch(patch_text: str) -> PatchSummary:
    """Count added / removed lines and hunks in a unified diff."""
    added = removed = hunks = 0
    filename = "file"
    for line in patch_text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            filename = target[2:] if target.startswith("b/") else target
        elif line.startswith("@@"):
            hunks += 1
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return PatchSummary(filename=filename, added=added, removed=removed, hunks=hunks)


def _parse_hunks(patch_text: str) -> list[tuple[int, int, list[str]]]:
    """Parse a unified diff into ``(old_start, old_count, body_lines)`` hunks.

    ``old_start`` is 1-based as in the diff header. ``body_lines`` are the raw
    hunk lines (prefixed with ' ', '-', or '+').
    """
    hunks: list[tuple[int, int, list[str]]] = []
    lines = patch_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("@@"):
            # @@ -old_start,old_count +new_start,new_count @@
            try:
                header = line.split("@@")[1].strip()
                old_part = header.split(" ")[0]  # -old_start,old_count
                old_spec = old_part[1:]  # drop leading '-'
                if "," in old_spec:
                    os_s, oc_s = old_spec.split(",", 1)
                    old_start, old_count = int(os_s), int(oc_s)
                else:
                    old_start, old_count = int(old_spec), 1
            except (IndexError, ValueError) as exc:
                raise ValueError(f"malformed hunk header: {line!r}") from exc
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("@@"):
                # Stop if we hit a new file header.
                if lines[i].startswith("--- ") or lines[i].startswith("+++ "):
                    break
                body.append(lines[i])
                i += 1
            hunks.append((old_start, old_count, body))
        else:
            i += 1
    return hunks


def apply_patch(original_text: str, patch_text: str) -> ApplyResult:
    """Apply a unified diff to ``original_text``. Context-validated.

    Returns ``ApplyResult(ok=False, reason=…)`` without modifying anything if
    any context or removed line does not match the original exactly. This is
    the safety property: a stale or mismatched patch is refused, never
    half-applied.

    Matching is newline-aware: lines are compared with their trailing newline
    (``splitlines(keepends=True)``), exactly as :func:`difflib.unified_diff`
    emits them, so trailing-newline edge cases round-trip correctly.
    """
    try:
        hunks = _parse_hunks(patch_text)
    except ValueError as exc:
        return ApplyResult(ok=False, reason=str(exc))
    if not hunks:
        return ApplyResult(ok=False, reason="no hunks found in patch")

    # Compare on lines WITH their newline, matching difflib's emission.
    src = original_text.splitlines(keepends=True)
    result: list[str] = []
    cursor = 0  # 0-based index into src

    def _norm(s: str) -> str:
        # The diff body lines come from .splitlines() of the patch text, so
        # they have lost their own trailing newline. Compare ignoring the
        # single trailing newline difference.
        return s[:-1] if s.endswith("\n") else s

    for old_start, _old_count, body in hunks:
        hunk_start = old_start - 1
        if hunk_start < 0 or hunk_start > len(src):
            return ApplyResult(
                ok=False, reason=f"hunk start {old_start} out of range"
            )
        if hunk_start < cursor:
            return ApplyResult(ok=False, reason="overlapping or out-of-order hunks")
        result.extend(src[cursor:hunk_start])
        cursor = hunk_start

        for bline in body:
            tag = bline[0] if bline else " "
            content = bline[1:] if bline else ""
            if tag == " ":
                if cursor >= len(src) or _norm(src[cursor]) != content:
                    return ApplyResult(
                        ok=False,
                        reason=(
                            f"context mismatch at line {cursor + 1}: "
                            f"expected {content!r}, found "
                            f"{_norm(src[cursor]) if cursor < len(src) else '<EOF>'!r}"
                        ),
                    )
                result.append(src[cursor])
                cursor += 1
            elif tag == "-":
                if cursor >= len(src) or _norm(src[cursor]) != content:
                    return ApplyResult(
                        ok=False,
                        reason=(
                            f"removed-line mismatch at line {cursor + 1}: "
                            f"expected {content!r}"
                        ),
                    )
                cursor += 1  # delete
            elif tag == "+":
                result.append(content + "\n")  # insert (restore newline)
            elif tag == "\\":
                # "\ No newline at end of file" — strip the newline we just added.
                if result and result[-1].endswith("\n"):
                    result[-1] = result[-1][:-1]
                continue
            else:
                return ApplyResult(ok=False, reason=f"bad hunk line: {bline!r}")

    result.extend(src[cursor:])
    return ApplyResult(ok=True, applied_text="".join(result))


# ── comment → revise → resubmit loop state ─────────────────────────────────


@dataclass
class PatchRound:
    """One round in a patch-review thread."""

    round_no: int
    author: str
    patch: str
    comment: str = ""
    decision: str = "submitted"  # submitted | commented | accepted | rejected


@dataclass
class PatchThread:
    """The state of a comment → revise → resubmit review thread.

    A thread is keyed by the A2A ``context_id`` so revisions stay linked
    across devices. Each ``PatchRound`` records who did what; the head is the
    latest patch under review.
    """

    context_id: str
    filename: str
    rounds: list[PatchRound] = field(default_factory=list)

    def submit(self, author: str, patch: str) -> PatchRound:
        """Reviewer submits (or resubmits) a patch."""
        rnd = PatchRound(
            round_no=len(self.rounds) + 1,
            author=author,
            patch=patch,
            decision="submitted",
        )
        self.rounds.append(rnd)
        return rnd

    def comment(self, author: str, comment: str) -> PatchRound:
        """Requester comments → asks for a revision (loops back to submit)."""
        if not self.rounds:
            raise ValueError("cannot comment on an empty thread")
        rnd = PatchRound(
            round_no=len(self.rounds) + 1,
            author=author,
            patch=self.rounds[-1].patch,
            comment=comment,
            decision="commented",
        )
        self.rounds.append(rnd)
        return rnd

    def accept(self, author: str) -> PatchRound:
        rnd = PatchRound(
            round_no=len(self.rounds) + 1,
            author=author,
            patch=self.rounds[-1].patch if self.rounds else "",
            decision="accepted",
        )
        self.rounds.append(rnd)
        return rnd

    def reject(self, author: str, reason: str = "") -> PatchRound:
        rnd = PatchRound(
            round_no=len(self.rounds) + 1,
            author=author,
            patch="",
            comment=reason,
            decision="rejected",
        )
        self.rounds.append(rnd)
        return rnd

    @property
    def head_patch(self) -> str:
        """The latest submitted patch, or '' if none."""
        for rnd in reversed(self.rounds):
            if rnd.decision == "submitted" and rnd.patch:
                return rnd.patch
        return ""

    @property
    def status(self) -> str:
        return self.rounds[-1].decision if self.rounds else "empty"
