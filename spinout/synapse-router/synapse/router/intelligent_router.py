# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""The Synapse Intelligent Router.

Routes each task to the cheapest model that can do it well: deep reasoning to
**Opus**, medium work to **Sonnet**, fast/cheap work to **Haiku**, with an
optional local **Ollama** fallback for offline or cost-capped operation.

This is one of Synapse's strongest selling points — for a real "build a fintech
app" workflow, intelligent routing cuts cost by ~85–91% versus running every
task on Opus (see :mod:`synapse.router.cost`).
"""

from __future__ import annotations

#: Deep reasoning / complex work.
OPUS = "claude-opus-4-8"
#: Medium-complexity work.
SONNET = "claude-sonnet-4-6"
#: Fast, cheap, high-volume work.
HAIKU = "claude-haiku-4-5-20251001"
#: Local fallback when offline or over a cost cap.
OLLAMA_FALLBACK = "ollama:llama-3.3-70b"

#: The routing table (mirrors the master spec). Order matters: the first entry
#: whose ``task_types`` contains the task wins. The final entry is the fallback.
ROUTING_TABLE: list[dict] = [
    {
        "task_types": [
            "architecture_decision",
            "security_audit",
            "complex_codegen",
            "strategic_planning",
            "temporal_reasoning",
            "reputation_analysis",
        ],
        "model": OPUS,
    },
    {
        "task_types": [
            "feature_spec",
            "research_synthesis",
            "documentation",
            "code_review",
            "api_design",
        ],
        "model": SONNET,
    },
    {
        "task_types": [
            "json_formatting",
            "data_extraction",
            "classification",
            "string_ops",
            "schema_validation",
            "secret_scan",
            "supply_chain_check",
        ],
        "model": HAIKU,
    },
    {
        "task_types": ["any"],
        "fallback": OLLAMA_FALLBACK,
        "condition": "offline_mode or cost_limit_exceeded",
    },
]


def _build_lookup() -> dict[str, str]:
    """Flatten the routing table into a ``task_type -> model`` map."""
    lookup: dict[str, str] = {}
    for entry in ROUTING_TABLE:
        model = entry.get("model")
        if model is None:
            continue
        for task_type in entry["task_types"]:
            lookup[task_type] = model
    return lookup


#: Fast ``task_type -> model`` lookup derived from :data:`ROUTING_TABLE`.
TASK_MODEL: dict[str, str] = _build_lookup()


def route(
    task_type: str,
    *,
    offline_mode: bool = False,
    cost_limit_exceeded: bool = False,
) -> str:
    """Return the model id to use for ``task_type``.

    The local fallback wins when ``offline_mode`` or ``cost_limit_exceeded`` is
    set. Otherwise the routing table is consulted; **unknown task types default
    to Opus**, because guessing cheap on an unrecognised task is the costly
    mistake (a bad answer is more expensive than a few extra cents).
    """
    if offline_mode or cost_limit_exceeded:
        return OLLAMA_FALLBACK
    return TASK_MODEL.get(task_type, OPUS)


def all_task_types() -> list[str]:
    """Return every explicitly-routed task type."""
    return sorted(TASK_MODEL)
