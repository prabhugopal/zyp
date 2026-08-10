"""The ambiguous-scenario SDLC topology — the same shape as graph.py's build_graph, with two
differences that exercise the assessment's ambiguous-scenario requirements for real:

1. `architecture_design` also requires human approval — the interpreted scope (not just the
   design artifact's presence) needs sign-off before implementation starts, since the request
   itself ("protect analytics access") doesn't say which of two reasonable readings is meant.
2. `implementation_core` uses a dynamic scope check (stages.implementation_core_auth_executor)
   that reads scenarios/ambiguous/clarification.md's presence at *execution* time. A first run
   with no clarification file checks the broader (approved) interpretation; if the actual code
   doesn't match it, the stage fails for real and exhausts its retries within that run. A
   clarification file appearing before a fresh run narrows what's checked — the same retry
   mechanism graph.py already has, now sensitive to real external state instead of only to
   command exit codes.

Everything else (fan-out/fan-in, defer=True joins, the release approval gate) is identical to
graph.py; see that module's docstring for why the joins need defer=True.
"""

from __future__ import annotations

import time

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

import stages
from config import Config
from graph import _all_passed, _passthrough, approval_node
from nodes.deterministic import make_node, should_retry, stage_passed
from nodes.reasoning import code_review_node, requirements_node
from state import SDLCState

_IMPLEMENTATION_STAGES = ("implementation_core", "implementation_storage", "implementation_analytics")


def architecture_approval_node(state: dict) -> dict:
    decision = interrupt({
        "stage_id": "architecture_design",
        "risk_level": "high",
        "reason": "The request is ambiguous about scope; the interpreted design needs sign-off "
                  "before implementation starts",
    })
    approved = decision == "approve"
    return {
        "context": {"__architecture_decision__": decision},
        "stage_statuses": {"architecture_design": "PASSED" if approved else "FAILED"},
        "messages": [{"stage": "architecture_design", "kind": "approval", "success": approved,
                      "detail": f"human decision on interpreted scope: {decision}"}],
    }


def _make_implementation_core_auth_node(config: Config):
    def node(state: dict) -> dict:
        attempt = state["retry_counts"].get("implementation_core", 0) + 1
        start = time.monotonic()
        result = stages.implementation_core_auth_executor(state["service_dir"], state["scenario_dir"])
        marker = {"__last_result__implementation_core": {"success": result.success, "transient": result.transient}}
        message = {"stage": "implementation_core", "kind": "deterministic", "success": result.success,
                   "detail": result.detail, "duration_s": round(time.monotonic() - start, 3)}
        return {
            "context": marker,
            "stage_statuses": {"implementation_core": "PASSED" if result.success else "FAILED"},
            "retry_counts": {"implementation_core": attempt},
            "messages": [message],
        }

    return node


def build_ambiguous_graph(config: Config) -> StateGraph:
    g = StateGraph(SDLCState)

    g.add_node("requirements", requirements_node(config))
    g.add_node("architecture_design", make_node("architecture_design", config))
    g.add_node("architecture_approval", architecture_approval_node)
    g.add_node("implementation_core", _make_implementation_core_auth_node(config))
    g.add_node("implementation_storage", make_node("implementation_storage", config))
    g.add_node("implementation_analytics", make_node("implementation_analytics", config))
    g.add_node("implementation_join", _passthrough, defer=True)
    g.add_node("unit_testing", make_node("unit_testing", config))
    g.add_node("static_analysis", make_node("static_analysis", config))
    g.add_node("code_review", code_review_node(config))
    g.add_node("integration_testing_join", _passthrough, defer=True)
    g.add_node("integration_testing", make_node("integration_testing", config))
    g.add_node("documentation", make_node("documentation", config))
    g.add_node("release_join", _passthrough, defer=True)
    g.add_node("approval", approval_node)
    g.add_node("release_readiness", make_node("release_readiness", config))

    g.add_edge(START, "requirements")
    g.add_conditional_edges("requirements",
        lambda s: "architecture_design" if stage_passed(s, "requirements") else "__end__",
        {"architecture_design": "architecture_design", "__end__": END})

    g.add_conditional_edges("architecture_design",
        lambda s: "architecture_approval" if stage_passed(s, "architecture_design") else "__end__",
        {"architecture_approval": "architecture_approval", "__end__": END})

    fan_out_targets = [*_IMPLEMENTATION_STAGES, "documentation"]
    g.add_conditional_edges("architecture_approval",
        lambda s: fan_out_targets if stage_passed(s, "architecture_design") else "__end__",
        {**{t: t for t in fan_out_targets}, "__end__": END})

    g.add_conditional_edges("implementation_core",
        lambda s: "implementation_core" if should_retry(s, "implementation_core") else "implementation_join",
        {"implementation_core": "implementation_core", "implementation_join": "implementation_join"})
    g.add_edge("implementation_storage", "implementation_join")
    g.add_edge("implementation_analytics", "implementation_join")

    g.add_conditional_edges("implementation_join",
        lambda s: ["unit_testing", "static_analysis"] if _all_passed(s, *_IMPLEMENTATION_STAGES) else "__end__",
        {"unit_testing": "unit_testing", "static_analysis": "static_analysis", "__end__": END})

    g.add_conditional_edges("unit_testing",
        lambda s: "unit_testing" if should_retry(s, "unit_testing") else "integration_testing_join",
        {"unit_testing": "unit_testing", "integration_testing_join": "integration_testing_join"})

    def _static_analysis_router(state: dict) -> str:
        if should_retry(state, "static_analysis"):
            return "static_analysis"
        return "code_review" if stage_passed(state, "static_analysis") else "integration_testing_join"

    g.add_conditional_edges("static_analysis", _static_analysis_router,
        {"static_analysis": "static_analysis", "code_review": "code_review",
         "integration_testing_join": "integration_testing_join"})
    g.add_edge("code_review", "integration_testing_join")

    g.add_conditional_edges("integration_testing_join",
        lambda s: "integration_testing" if _all_passed(s, "unit_testing", "static_analysis") else "__end__",
        {"integration_testing": "integration_testing", "__end__": END})

    g.add_edge("integration_testing", "release_join")
    g.add_edge("documentation", "release_join")

    g.add_conditional_edges("release_join",
        lambda s: "approval" if _all_passed(s, "integration_testing", "documentation") else "__end__",
        {"approval": "approval", "__end__": END})

    g.add_conditional_edges("approval",
        lambda s: "release_readiness" if s["context"].get("__approval_decision__") == "approve" else "__end__",
        {"release_readiness": "release_readiness", "__end__": END})

    g.add_edge("release_readiness", END)

    return g
