# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Jai Sogani. Licensed under the Apache License, Version 2.0.
"""Cost-savings calculator for the Intelligent Router.

Given a workload (counts of task types), this computes the **real dollar cost**
of routing each task to the right model versus running everything on Opus, and
reports the savings. Prices are USD per million tokens and are configurable.

Illustrative headline (master spec): a 200-task "build a fintech app" workflow
costs ~\\$21 all-Opus but ~\\$3 routed — an ~85% saving. The exact percentage
depends on average task size; this module computes it from first principles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from synapse.router.intelligent_router import HAIKU, OLLAMA_FALLBACK, OPUS, SONNET, route

#: Typical task size assumptions (tokens) when not otherwise specified.
DEFAULT_AVG_INPUT_TOKENS = 2_000
DEFAULT_AVG_OUTPUT_TOKENS = 1_000


@dataclass(frozen=True)
class ModelPricing:
    """USD price per *million* tokens, split by input vs output."""

    input_per_mtok: float
    output_per_mtok: float


#: Representative pricing (USD / 1M tokens). Adjust to your contract.
MODEL_PRICING: dict[str, ModelPricing] = {
    OPUS: ModelPricing(15.0, 75.0),
    SONNET: ModelPricing(3.0, 15.0),
    HAIKU: ModelPricing(1.0, 5.0),
    OLLAMA_FALLBACK: ModelPricing(0.0, 0.0),  # local inference: no API cost
}


def cost_per_task(
    model: str,
    input_tokens: int = DEFAULT_AVG_INPUT_TOKENS,
    output_tokens: int = DEFAULT_AVG_OUTPUT_TOKENS,
) -> float:
    """Return the USD cost of one task on ``model``.

    Raises:
        KeyError: if ``model`` has no pricing entry.
    """
    pricing = MODEL_PRICING[model]
    return (
        input_tokens * pricing.input_per_mtok
        + output_tokens * pricing.output_per_mtok
    ) / 1_000_000


@dataclass(frozen=True)
class CostReport:
    """The result of costing a workload, routed vs all-Opus baseline."""

    task_count: int
    per_model_tasks: dict[str, int]
    routed_usd: float
    baseline_opus_usd: float
    savings_usd: float
    savings_pct: float
    notes: list[str] = field(default_factory=list)


def savings_report(
    workload: dict[str, int],
    *,
    avg_input_tokens: int = DEFAULT_AVG_INPUT_TOKENS,
    avg_output_tokens: int = DEFAULT_AVG_OUTPUT_TOKENS,
) -> CostReport:
    """Cost ``workload`` (``task_type -> count``) routed vs all-Opus.

    Returns a :class:`CostReport` with the per-model task distribution, both
    totals, and the savings (absolute and percentage).
    """
    per_model_tasks: dict[str, int] = {}
    routed_total = 0.0
    baseline_total = 0.0
    task_count = 0

    for task_type, count in workload.items():
        if count < 0:
            raise ValueError(f"negative count for task {task_type!r}")
        model = route(task_type)
        per_model_tasks[model] = per_model_tasks.get(model, 0) + count
        routed_total += count * cost_per_task(model, avg_input_tokens, avg_output_tokens)
        baseline_total += count * cost_per_task(OPUS, avg_input_tokens, avg_output_tokens)
        task_count += count

    savings = baseline_total - routed_total
    savings_pct = (savings / baseline_total * 100.0) if baseline_total > 0 else 0.0

    return CostReport(
        task_count=task_count,
        per_model_tasks=per_model_tasks,
        routed_usd=round(routed_total, 4),
        baseline_opus_usd=round(baseline_total, 4),
        savings_usd=round(savings, 4),
        savings_pct=round(savings_pct, 1),
        notes=[
            f"avg task: {avg_input_tokens} in / {avg_output_tokens} out tokens",
            "prices are USD per 1M tokens (configurable via MODEL_PRICING)",
        ],
    )


def headline_example() -> CostReport:
    """Reproduce the spec's 200-task workflow (10 Opus, 60 Sonnet, 130 Haiku)."""
    workload = {
        "architecture_decision": 10,  # -> Opus
        "documentation": 60,          # -> Sonnet
        "json_formatting": 130,       # -> Haiku
    }
    return savings_report(workload)
