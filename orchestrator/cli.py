#!/usr/bin/env python3
"""CLI for the zyp SDLC orchestrator — builds and gates zyp/service itself via a LangGraph
StateGraph + SqliteSaver checkpointer.

    python3 cli.py run --scenario greenfield
    python3 cli.py approve <run_id> --by "Jane Doe" --decision approve
    python3 cli.py status <run_id>
    python3 cli.py list
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

from langgraph.types import Command

from checkpoint import get_checkpointer
from config import load_config
from graph import build_graph

ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(ORCH_DIR)
SERVICE_DIR = os.path.join(REPO_ROOT, "service")
STATE_DIR = os.path.join(ORCH_DIR, "state")
SCENARIOS_DIR = os.path.join(REPO_ROOT, "scenarios")
APPROVALS_DIR = os.path.join(STATE_DIR, "approvals")

VALID_SCENARIOS = ("greenfield", "brownfield")


def _initial_state(run_id: str, scenario_id: str, scenario_dir: str) -> dict:
    return {
        "run_id": run_id, "scenario_id": scenario_id,
        "scenario_dir": scenario_dir, "repo_root": REPO_ROOT, "service_dir": SERVICE_DIR,
        "context": {}, "stage_statuses": {}, "retry_counts": {}, "messages": [],
    }


def _print_progress(chunk: dict) -> None:
    for node_name, delta in chunk.items():
        if node_name == "__interrupt__":
            continue
        for m in (delta or {}).get("messages", []):
            stage = m.get("stage", node_name)
            if m.get("kind") == "llm_reasoning":
                print(f"  [{stage}] llm reasoning:")
                for line in m["detail"].splitlines():
                    print(f"    {line}")
            elif m.get("kind") == "approval":
                print(f"  [{stage}] {m['detail']}")
            else:
                status = "PASSED" if m.get("success") else "FAILED"
                print(f"  [{stage}] {status}: {m['detail']}")


def _decision_path(run_id: str) -> str:
    return os.path.join(APPROVALS_DIR, f"{run_id}.json")


def _load_decision(run_id: str) -> dict | None:
    path = _decision_path(run_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_run(args: argparse.Namespace) -> int:
    if args.scenario not in VALID_SCENARIOS:
        print(f"unknown scenario '{args.scenario}', expected one of {VALID_SCENARIOS}", file=sys.stderr)
        return 2

    config = load_config(os.path.join(ORCH_DIR, "config.yaml"))
    run_id = args.run_id or f"{args.scenario}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    scenario_dir = os.path.join(SCENARIOS_DIR, args.scenario)
    graph_config = {"configurable": {"thread_id": run_id}}

    compiled = build_graph(config).compile(checkpointer=get_checkpointer(STATE_DIR))
    print(f"run_id={run_id} scenario={args.scenario} model={config.model_provider}/{config.resolved_model_name}")

    existing = compiled.get_state(graph_config)
    if existing.next:
        decision = _load_decision(run_id)
        if decision is None:
            pending = existing.tasks[0].interrupts[0].value if existing.tasks else {}
            print(f"status=BLOCKED stage={pending.get('stage_id', existing.next)}")
            print(f"  -> python3 cli.py approve {run_id} --by \"<name>\" --decision approve")
            return 0
        stream_input = Command(resume=decision["decision"])
    elif existing.values.get("stage_statuses"):
        print("status=already completed; use 'python3 cli.py status " + run_id + "' to inspect")
        return 0
    else:
        stream_input = _initial_state(run_id, args.scenario, scenario_dir)

    for chunk in compiled.stream(stream_input, graph_config):
        _print_progress(chunk)

    final = compiled.get_state(graph_config)
    if final.next:
        pending = final.tasks[0].interrupts[0].value if final.tasks else {}
        print(f"status=BLOCKED stage={pending.get('stage_id', final.next)}")
        print(f"  -> python3 cli.py approve {run_id} --by \"<name>\" --decision approve")
        return 0

    statuses = final.values.get("stage_statuses", {})
    overall = "COMPLETED" if statuses.get("release_readiness") == "PASSED" else "FAILED"
    print(f"status={overall}")
    _write_run_summary(run_id, args.scenario, overall, statuses)
    return 0 if overall == "COMPLETED" else 1


def _write_run_summary(run_id: str, scenario_id: str, status: str, statuses: dict) -> None:
    os.makedirs(os.path.join(STATE_DIR, "runs"), exist_ok=True)
    payload = {"run_id": run_id, "scenario_id": scenario_id, "status": status,
               "stage_statuses": statuses, "updated_at": datetime.now(timezone.utc).isoformat()}
    with open(os.path.join(STATE_DIR, "runs", f"{run_id}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def cmd_approve(args: argparse.Namespace) -> int:
    os.makedirs(APPROVALS_DIR, exist_ok=True)
    payload = {"decision": args.decision, "by": args.by, "comment": args.comment or "",
               "decided_at": datetime.now(timezone.utc).isoformat()}
    with open(_decision_path(args.run_id), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"recorded {args.decision} for {args.run_id} by {args.by}")
    print(f"re-run to continue: python3 cli.py run --scenario greenfield --run-id {args.run_id}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config(os.path.join(ORCH_DIR, "config.yaml"))
    compiled = build_graph(config).compile(checkpointer=get_checkpointer(STATE_DIR))
    snap = compiled.get_state({"configurable": {"thread_id": args.run_id}})
    if not snap.values:
        print(f"no such run: {args.run_id}", file=sys.stderr)
        return 1
    print(json.dumps({
        "run_id": args.run_id,
        "stage_statuses": snap.values.get("stage_statuses", {}),
        "blocked_on": snap.next or None,
    }, indent=2))
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    for path in sorted(glob.glob(os.path.join(STATE_DIR, "runs", "*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"{data['run_id']:40s} {data['scenario_id']:12s} {data['status']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="zyp SDLC orchestrator (LangGraph)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run (or resume) a scenario")
    p_run.add_argument("--scenario", required=True, choices=VALID_SCENARIOS)
    p_run.add_argument("--run-id", default=None, help="resume an existing run instead of starting a new one")
    p_run.set_defaults(func=cmd_run)

    p_approve = sub.add_parser("approve", help="record a human approval decision")
    p_approve.add_argument("run_id")
    p_approve.add_argument("--by", required=True, help="approver name/identity")
    p_approve.add_argument("--decision", required=True, choices=["approve", "reject"])
    p_approve.add_argument("--comment", default="")
    p_approve.set_defaults(func=cmd_approve)

    p_status = sub.add_parser("status", help="print run state")
    p_status.add_argument("run_id")
    p_status.set_defaults(func=cmd_status)

    p_list = sub.add_parser("list", help="list all runs")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
