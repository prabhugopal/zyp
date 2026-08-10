"""The greenfield SDLC topology for zyp itself, as a LangGraph StateGraph, gating zyp's own real
pytest-based stages.

Fan-in pattern: a stage that depends on several parallel predecessors (unit_testing and
static_analysis both depend on all three implementation_* stages) doesn't gate itself — instead
every predecessor unconditionally routes into a "*_join" node once it's truly done (passed, or
permanently failed after retries), and the join node is the single place that inspects
stage_statuses and decides whether to fan out further or end the run.

Every join node is built with `defer=True`. LangGraph's Pregel executor schedules nodes in
supersteps keyed by graph *distance* from the fork point, not by real completion order — so a join
whose incoming paths have different hop-counts (e.g. static_analysis -> code_review -> join is one
hop longer than unit_testing -> join on a pass, and any retry loop adds a dynamic, unpredictable
number of extra hops) fires once per arriving superstep instead of once total, silently re-running
every downstream stage. `defer=True` makes the node wait until every other pending task in the run
has settled before executing, which is the only fix that also covers a *variable* number of retry
hops — a fixed padding node cannot, since the retry count isn't known until runtime. Verified
directly: without `defer`, a two-branch join with a retry loop on one branch fired twice for real
(a real `pytest` subprocess ran twice); with `defer=True` on the same graph it fires exactly once.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from config import Config
from nodes.deterministic import make_node, should_retry, stage_passed
from nodes.reasoning import code_review_node, requirements_node
from state import SDLCState

_IMPLEMENTATION_STAGES = ("implementation_core", "implementation_storage", "implementation_analytics")


def _passthrough(_state: dict) -> dict:
    return {}


def approval_node(state: dict) -> dict:
    decision = interrupt({
        "stage_id": "release_readiness",
        "risk_level": "high",
        "reason": "High-impact release gate requires human sign-off",
    })
    approved = decision == "approve"
    return {
        "context": {"__approval_decision__": decision},
        "messages": [{"stage": "release_readiness", "kind": "approval", "success": approved,
                      "detail": f"human decision: {decision}"}],
    }


def _all_passed(state: dict, *stage_ids: str) -> bool:
    return all(stage_passed(state, s) for s in stage_ids)


def build_graph(config: Config) -> StateGraph:
    g = StateGraph(SDLCState)

    g.add_node("requirements", requirements_node(config))
    g.add_node("architecture_design", make_node("architecture_design", config))
    for stage_id in _IMPLEMENTATION_STAGES:
        g.add_node(stage_id, make_node(stage_id, config))
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

    fan_out_targets = [*_IMPLEMENTATION_STAGES, "documentation"]
    g.add_conditional_edges("architecture_design",
        lambda s: fan_out_targets if stage_passed(s, "architecture_design") else "__end__",
        {**{t: t for t in fan_out_targets}, "__end__": END})

    # implementation_core is the only one of the three with a retry policy (matches stages.py);
    # all three unconditionally reach the join once truly done, pass or fail — the join decides.
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
