"""LangGraph nodes wrapping the real stage executors in stages.py — the same functions that run
actual `uv run pytest` / real module imports / the real static-analysis scan. Adapts their simple
(path) -> StageResult signature to LangGraph's (state) -> state-delta signature, and layers on the
one exit-gate check (coverage threshold) that's genuinely configurable per policy profile here.
"""

from __future__ import annotations

import time

import stages
from config import Config
from policy import profile_for

MAX_ATTEMPTS = {"implementation_core": 2, "unit_testing": 2, "static_analysis": 2}
DEFAULT_MAX_ATTEMPTS = 1

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
        start = time.monotonic()
        result = executor(state[path_key])

        if result.success and stage_id == "unit_testing":
            coverage = stages.parse_coverage(state["service_dir"])
            threshold = profile_for(config).coverage_threshold
            if coverage is None or coverage < threshold:
                pct = f"{coverage:.1%}" if coverage is not None else "unknown"
                result = stages.StageResult(False, f"instruction coverage {pct} below the {threshold:.0%} "
                                                     f"gate ({config.policy_profile} profile)", transient=False)

        marker = {f"__last_result__{stage_id}": {"success": result.success, "transient": result.transient}}
        message = {"stage": stage_id, "kind": "deterministic", "success": result.success,
                   "detail": result.detail, "duration_s": round(time.monotonic() - start, 3)}
        return {
            "context": {**(result.data if result.success else {}), **marker},
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


def stage_passed(state: dict, stage_id: str) -> bool:
    last = state["context"].get(f"__last_result__{stage_id}")
    return bool(last and last["success"])
