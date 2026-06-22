# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Patch review workflow — unified diff generation, application, and the
comment → revise → resubmit loop.

The applier's safety property is the headline: a mismatched patch is refused,
never half-applied. These tests pin that, plus the round-trip and threading.
"""

from __future__ import annotations

import pytest

from synapse_cli.patch import (
    ApplyResult,
    PatchThread,
    apply_patch,
    make_patch,
    summarize_patch,
)

ORIGINAL = """def login(user):
    if user:
        return True
    return False
"""

MODIFIED = """def login(user):
    if user and user.is_active:
        return True
    return False
"""


# ── generate ────────────────────────────────────────────────────────────────


def test_make_patch_produces_unified_diff() -> None:
    patch = make_patch(ORIGINAL, MODIFIED, "auth.py")
    assert "--- a/auth.py" in patch
    assert "+++ b/auth.py" in patch
    assert "@@" in patch
    assert "+    if user and user.is_active:" in patch
    assert "-    if user:" in patch


def test_make_patch_empty_when_identical() -> None:
    assert make_patch(ORIGINAL, ORIGINAL, "auth.py") == ""


# ── summarize ─────────────────────────────────────────────────────────────


def test_summarize_patch_counts() -> None:
    patch = make_patch(ORIGINAL, MODIFIED, "auth.py")
    summary = summarize_patch(patch)
    assert summary.filename == "auth.py"
    assert summary.added == 1
    assert summary.removed == 1
    assert summary.hunks == 1


# ── apply (happy path) ─────────────────────────────────────────────────────


def test_apply_patch_round_trip() -> None:
    patch = make_patch(ORIGINAL, MODIFIED, "auth.py")
    result = apply_patch(ORIGINAL, patch)
    assert isinstance(result, ApplyResult)
    assert result.ok, result.reason
    assert result.applied_text == MODIFIED


def test_apply_patch_multi_hunk() -> None:
    old = "\n".join(f"line{i}" for i in range(1, 21)) + "\n"
    new_lines = [f"line{i}" for i in range(1, 21)]
    new_lines[2] = "line3-CHANGED"
    new_lines[17] = "line18-CHANGED"
    new = "\n".join(new_lines) + "\n"
    patch = make_patch(old, new, "big.txt")
    result = apply_patch(old, patch)
    assert result.ok, result.reason
    assert "line3-CHANGED" in result.applied_text
    assert "line18-CHANGED" in result.applied_text


# ── apply (safety / failure paths) ─────────────────────────────────────────


def test_apply_patch_refuses_on_context_mismatch() -> None:
    """A patch built against a different original must be refused, not half-applied."""
    patch = make_patch(ORIGINAL, MODIFIED, "auth.py")
    drifted = ORIGINAL.replace("return False", "return None")  # file changed since
    result = apply_patch(drifted, patch)
    assert not result.ok
    assert "mismatch" in result.reason
    assert result.applied_text == ""  # nothing applied


def test_apply_patch_empty_patch_is_refused() -> None:
    result = apply_patch(ORIGINAL, "")
    assert not result.ok
    assert "no hunks" in result.reason


def test_apply_patch_does_not_mutate_on_failure() -> None:
    patch = make_patch(ORIGINAL, MODIFIED, "auth.py")
    drifted = "totally different content\n"
    result = apply_patch(drifted, patch)
    assert not result.ok
    # original input string is obviously unchanged (immutable), but assert the
    # result carries nothing partial
    assert result.applied_text == ""


# ── comment → revise → resubmit loop ───────────────────────────────────────


def test_patch_thread_submit_comment_revise_accept() -> None:
    thread = PatchThread(context_id="ctx-1", filename="auth.py")

    # round 1: reviewer submits a patch
    p1 = make_patch(ORIGINAL, MODIFIED, "auth.py")
    thread.submit("bob", p1)
    assert thread.status == "submitted"
    assert thread.head_patch == p1

    # round 2: requester comments → wants a revision
    thread.comment("alice", "also guard against None user")
    assert thread.status == "commented"

    # round 3: reviewer revises and resubmits
    revised_src = MODIFIED.replace(
        "if user and user.is_active:",
        "if user is not None and user.is_active:",
    )
    p2 = make_patch(ORIGINAL, revised_src, "auth.py")
    thread.submit("bob", p2)
    assert thread.status == "submitted"
    assert thread.head_patch == p2  # head advances to the revision

    # round 4: requester accepts
    thread.accept("alice")
    assert thread.status == "accepted"
    assert len(thread.rounds) == 4
    assert [r.decision for r in thread.rounds] == [
        "submitted", "commented", "submitted", "accepted",
    ]


def test_patch_thread_reject() -> None:
    thread = PatchThread(context_id="ctx-2", filename="x.py")
    thread.submit("bob", make_patch("a\n", "b\n", "x.py"))
    thread.reject("alice", reason="out of scope")
    assert thread.status == "rejected"


def test_patch_thread_comment_on_empty_raises() -> None:
    thread = PatchThread(context_id="ctx-3", filename="x.py")
    with pytest.raises(ValueError):
        thread.comment("alice", "nothing to comment on")


def test_revised_patch_applies_cleanly() -> None:
    """The whole point: the accepted revision actually applies to the original."""
    thread = PatchThread(context_id="ctx-4", filename="auth.py")
    thread.submit("bob", make_patch(ORIGINAL, MODIFIED, "auth.py"))
    thread.comment("alice", "tighten the None check")
    revised = MODIFIED.replace(
        "if user and user.is_active:",
        "if user is not None and user.is_active:",
    )
    thread.submit("bob", make_patch(ORIGINAL, revised, "auth.py"))
    thread.accept("alice")

    result = apply_patch(ORIGINAL, thread.head_patch)
    assert result.ok, result.reason
    assert "user is not None and user.is_active" in result.applied_text
