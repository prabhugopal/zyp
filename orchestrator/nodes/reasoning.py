"""LLM-driven reasoning nodes — genuinely agentic on top of the same real deterministic gates.
Neither node here can flip a PASSED/FAILED decision: the requirements node's pass/fail still comes
from the real artifact-gate check in stages.py, and the code-review node runs strictly after the
real static_analysis scan and only adds advisory commentary. An LLM proposes context and judgment;
real tool output remains the source of truth for whether a stage passed.
"""

from __future__ import annotations

import glob
import os
import time

import stages
from config import Config
from llm import get_chat_model
import rag

REQUIREMENTS_PROMPT = """You are reviewing a software requirements document for ambiguity before \
implementation begins. Read the requirements below and list, in a few bullet points, anything \
genuinely ambiguous or underspecified — a scope boundary that isn't clear, a term used without \
definition, a decision the document defers without saying to whom. If the requirements are \
genuinely unambiguous, say so plainly in one sentence. Do not restate the requirements; only \
report ambiguity.

{context}

Requirements document:
{requirements}
"""

CODE_REVIEW_PROMPT = """You are giving a second, qualitative opinion on a Python codebase that has \
already passed an automated static-analysis scan for banned patterns (hardcoded secrets, \
swallowed exceptions, eval/exec, non-TLS URLs). Your job is different: look for design and \
maintainability concerns the automated scan wouldn't catch — unclear naming, a function doing too \
much, a missing test for an edge case implied by the requirements. Keep it to 3-5 bullet points, \
or state plainly that nothing stood out. This is advisory only; it does not gate the build.

{context}

Source files (truncated):
{source_excerpt}
"""

_STATE_SUBDIR = "state"


def requirements_node(config: Config):
    def node(state: dict) -> dict:
        attempt = state["retry_counts"].get("requirements", 0) + 1
        start = time.monotonic()
        result = stages.requirements_executor(state["scenario_dir"])

        messages = [{"stage": "requirements", "kind": "deterministic", "success": result.success,
                     "detail": result.detail, "duration_s": round(time.monotonic() - start, 3)}]

        if result.success:
            req_path = os.path.join(state["scenario_dir"], "artifacts", "requirements.md")
            with open(req_path, encoding="utf-8") as f:
                requirements_text = f.read()
            state_dir = os.path.join(state["repo_root"], "orchestrator", _STATE_SUBDIR)
            rag_context = rag.retrieve("requirements ambiguity assumptions scope", state["scenario_dir"],
                                        state_dir, state["scenario_id"], config)
            llm_start = time.monotonic()
            llm = get_chat_model(config)
            prompt = REQUIREMENTS_PROMPT.format(
                context=f"Related context from prior runs/artifacts:\n{rag_context}\n" if rag_context else "",
                requirements=requirements_text,
            )
            response = llm.invoke(prompt)
            messages.append({"stage": "requirements", "kind": "llm_reasoning", "success": True,
                              "detail": response.content, "duration_s": round(time.monotonic() - llm_start, 3)})

        marker = {"__last_result__requirements": {"success": result.success, "transient": result.transient}}
        return {
            "context": {**(result.data if result.success else {}), **marker},
            "stage_statuses": {"requirements": "PASSED" if result.success else "FAILED"},
            "retry_counts": {"requirements": attempt},
            "messages": messages,
        }

    return node


def code_review_node(config: Config):
    """Runs after static_analysis; strictly advisory — never touches static_analysis's own
    stage_statuses entry, which was already set by the real deterministic scan."""

    def node(state: dict) -> dict:
        if not state["context"].get("__last_result__static_analysis", {}).get("success"):
            return {"messages": []}

        service_dir = state["service_dir"]
        py_files = sorted(glob.glob(os.path.join(service_dir, "**", "*.py"), recursive=True))
        py_files = [f for f in py_files if ".venv" not in f and "/tests/" not in f][:6]
        excerpt_parts = []
        for path in py_files:
            with open(path, encoding="utf-8", errors="ignore") as f:
                excerpt_parts.append(f"# {os.path.relpath(path, service_dir)}\n{f.read()[:800]}")
        source_excerpt = "\n\n".join(excerpt_parts) or "(no source files found)"

        start = time.monotonic()
        llm = get_chat_model(config)
        prompt = CODE_REVIEW_PROMPT.format(
            context="This is a real-time advisory review, not a gate.",
            source_excerpt=source_excerpt,
        )
        response = llm.invoke(prompt)
        message = {"stage": "static_analysis", "kind": "llm_reasoning", "success": True,
                   "detail": response.content, "duration_s": round(time.monotonic() - start, 3)}
        return {"messages": [message]}

    return node
