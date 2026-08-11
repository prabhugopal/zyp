"""LangGraph nodes wrapping the real stage executors in stages.py — the same functions that run
actual `uv run pytest` / real module imports / the real static-analysis scan. Adapts their simple
(path) -> StageResult signature to LangGraph's (state) -> state-delta signature, and layers on the
one exit-gate check (coverage threshold) that's genuinely configurable per policy profile here.
"""

from __future__ import annotations

import time

import rollback
import stages
from config import Config
from policy import profile_for
from progress import spinner
from stage_config import DEFAULT_MAX_ATTEMPTS, MAX_ATTEMPTS, ROLLBACK_PATHS

_SCENARIO_STAGES = {
    "architecture_design": stages.architecture_design_executor,
    "documentation": stages.documentation_executor,
}
_SERVICE_STAGES = {
    "implementation_core": stages.implementation_core_executor,
    "implementation_storage": stages.implementation_storage_executor,
    "implementation_analytics": stages.implementation_analytics_executor,
    "unit_testing": stages.unit_testing_executor,
    "static_analysis": stages.static_analysis_executor,
    "integration_testing": stages.integration_testing_executor,
    "release_readiness": stages.release_readiness_executor,
}


def make_node(stage_id: str, config: Config):
    if stage_id in _SCENARIO_STAGES:
        executor, path_key = _SCENARIO_STAGES[stage_id], "scenario_dir"
    else:
        executor, path_key = _SERVICE_STAGES[stage_id], "service_dir"

    def node(state: dict) -> dict:
        attempt = state["retry_counts"].get(stage_id, 0) + 1
        context_delta: dict = {}
        if stage_id in ROLLBACK_PATHS and f"__snapshot__{stage_id}" not in state["context"]:
            context_delta[f"__snapshot__{stage_id}"] = rollback.git_head(state["repo_root"])

        attempt_note = f" (attempt {attempt})" if attempt > 1 else ""
        print(f"  [{stage_id}] running{attempt_note}...", flush=True)
        start = time.monotonic()
        with spinner(f"[{stage_id}]"):
            result = executor(state[path_key])

        if result.success and stage_id == "unit_testing":
            coverage = stages.parse_coverage(state["service_dir"])
            threshold = profile_for(config).coverage_threshold
            if coverage is None or coverage < threshold:
                pct = f"{coverage:.1%}" if coverage is not None else "unknown"
                result = stages.StageResult(False, f"instruction coverage {pct} below the {threshold:.0%} "
                                                     f"gate ({config.policy_profile} profile)", transient=False)

        marker = {f"__last_result__{stage_id}": {"success": result.success, "transient": result.transient}}
        context_delta.update(result.data if result.success else {})
        context_delta.update(marker)
        message = {"stage": stage_id, "kind": "deterministic", "success": result.success,
                   "detail": result.detail, "duration_s": round(time.monotonic() - start, 3)}
        return {
            "context": context_delta,
            "stage_statuses": {stage_id: "PASSED" if result.success else "FAILED"},
            "retry_counts": {stage_id: attempt},
            "messages": [message],
        }

    return node


def should_retry(state: dict, stage_id: str) -> bool:
    last = state["context"].get(f"__last_result__{stage_id}")
    if last is None or last["success"]:
        return False
    max_attempts = MAX_ATTEMPTS.get(stage_id, DEFAULT_MAX_ATTEMPTS)
    return last["transient"] and state["retry_counts"].get(stage_id, 0) < max_attempts


def retries_exhausted(state: dict, stage_id: str) -> bool:
    """True once a stage has failed and will never be retried again — the signal to roll back."""
    last = state["context"].get(f"__last_result__{stage_id}")
    return bool(last and not last["success"] and not should_retry(state, stage_id))


def stage_passed(state: dict, stage_id: str) -> bool:
    last = state["context"].get(f"__last_result__{stage_id}")
    return bool(last and last["success"])


def make_rollback_node(stage_id: str):
    """Runs when a retryable stage exhausts its retries: reverts its declared paths to the git
    snapshot recorded at stage entry, and marks the stage ROLLED_BACK instead of leaving it FAILED
    — a distinct status so a run report can tell "we caught it and safely reverted" apart from
    "it broke and nothing cleaned up after it".
    """
    paths = ROLLBACK_PATHS[stage_id]

    def node(state: dict) -> dict:
        snapshot = state["context"].get(f"__snapshot__{stage_id}", "")
        restored = rollback.rollback_paths(state["repo_root"], snapshot, paths)
        detail = (f"rolled back {', '.join(paths)} to {snapshot[:12]} after exhausting retries"
                   if restored else f"rollback of {', '.join(paths)} failed (snapshot={snapshot!r})")
        message = {"stage": stage_id, "kind": "rollback", "success": restored, "detail": detail}
        return {
            "stage_statuses": {stage_id: "ROLLED_BACK" if restored else "FAILED"},
            "messages": [message],
        }

    return node
