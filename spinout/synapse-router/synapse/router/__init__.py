# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Synapse Intelligent Router package.

``synapse`` is a PEP 420 namespace package shared with ``synapse-core``;
``synapse.router`` is this regular package.
"""

from synapse.router.cost import (
    MODEL_PRICING,
    CostReport,
    cost_per_task,
    headline_example,
    savings_report,
)
from synapse.router.intelligent_router import (
    HAIKU,
    OLLAMA_FALLBACK,
    OPUS,
    ROUTING_TABLE,
    SONNET,
    TASK_MODEL,
    all_task_types,
    route,
)

__all__ = [
    "OPUS",
    "SONNET",
    "HAIKU",
    "OLLAMA_FALLBACK",
    "ROUTING_TABLE",
    "TASK_MODEL",
    "route",
    "all_task_types",
    "MODEL_PRICING",
    "CostReport",
    "cost_per_task",
    "savings_report",
    "headline_example",
]
