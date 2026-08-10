"""Graph state for the LangGraph orchestrator. A TypedDict rather than a class: LangGraph merges
partial updates a node returns into this dict via reducers, so plain fields are enough — no
behavior lives on the state itself (mirrors the same "state is data, engine is code" split as
orchestrator/engine/run.py's WorkflowRun)."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


def _merge(a: dict, b: dict) -> dict:
    """Shallow-merge reducer. Three stages (implementation_core/storage/analytics) fan out from
    architecture_design and run concurrently in the same LangGraph superstep, each writing only its
    own keys into context/stage_statuses/retry_counts — without a reducer, LangGraph rejects two
    nodes touching the same state field in one step as a conflicting concurrent write."""
    return {**a, **b}


class SDLCState(TypedDict):
    run_id: str
    scenario_id: str
    scenario_dir: str
    repo_root: str
    service_dir: str

    # Cross-stage shared data — same role as WorkflowRun.context in the original orchestrator:
    # one stage's output (e.g. "design_ready") becomes a later stage's entry-gate input.
    context: Annotated[dict, _merge]

    # PENDING | RUNNING | PASSED | FAILED | BLOCKED_ON_APPROVAL | ROLLED_BACK, keyed by stage id.
    stage_statuses: Annotated[dict, _merge]

    # Bounded-retry bookkeeping, keyed by stage id.
    retry_counts: Annotated[dict, _merge]

    # Reasoning trace from the LLM nodes (ambiguity analysis, advisory code review) — appended to,
    # never overwritten, via the `operator.add` reducer so parallel branches don't clobber it.
    messages: Annotated[list[dict], operator.add]
