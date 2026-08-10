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
import webbrowser
from datetime import datetime, timezone

from langgraph.types import Command

from checkpoint import get_checkpointer
from config import Config, load_config
from graph import build_graph
from graph_ambiguous import build_ambiguous_graph
from report import write_html_report

ORCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(ORCH_DIR)
SERVICE_DIR = os.path.join(REPO_ROOT, "service")
STATE_DIR = os.path.join(ORCH_DIR, "state")
SCENARIOS_DIR = os.path.join(REPO_ROOT, "scenarios")
APPROVALS_DIR = os.path.join(STATE_DIR, "approvals")

VALID_SCENARIOS = ("greenfield", "brownfield", "ambiguous")


def _build_graph(scenario_id: str, config: Config):
    if scenario_id == "ambiguous":
        return build_ambiguous_graph(config)
    return build_graph(config)


def _scenario_from_run_id(run_id: str) -> str:
    """run_id is always f"{scenario}-{timestamp}" (see cmd_run) and none of the scenario names
    contain a hyphen, so splitting on the last one recovers it without needing a separate lookup
    file for commands (approve, status) that only take the run_id."""
    return run_id.rsplit("-", 1)[0]


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
                duration = m.get("duration_s")
                suffix = f" ({duration:.1f}s)" if duration is not None else ""
                print(f"  [{stage}] {status}{suffix}: {m['detail']}")


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

    compiled = _build_graph(args.scenario, config).compile(checkpointer=get_checkpointer(STATE_DIR))
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

    try:
        for chunk in compiled.stream(stream_input, graph_config):
            _print_progress(chunk)
    except KeyboardInterrupt:
        print(f"\ninterrupted — progress up to the last completed stage is checkpointed.")
        print(f"  -> resume: python3 cli.py run --scenario {args.scenario} --run-id {run_id}")
        return 130

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
    model_label = f"{config.model_provider}/{config.resolved_model_name}"
    report_path = write_html_report(run_id, args.scenario, model_label, overall, final.values,
                                     os.path.join(STATE_DIR, "runs"))
    print(f"report: {report_path}")
    if args.open_report:
        webbrowser.open(f"file://{os.path.abspath(report_path)}")
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
    scenario_id = _scenario_from_run_id(args.run_id)
    print(f"re-run to continue: python3 cli.py run --scenario {scenario_id} --run-id {args.run_id}")
    return 0


def _latest_run_id(scenario_id: str) -> str | None:
    """run_id is f'{scenario}-{timestamp}' with a sortable UTC timestamp (see cmd_run), so the
    lexicographically-last matching state/runs/*.json is the most recent run of that scenario."""
    matches = sorted(glob.glob(os.path.join(STATE_DIR, "runs", f"{scenario_id}-*.json")))
    return os.path.basename(matches[-1])[: -len(".json")] if matches else None


def cmd_status(args: argparse.Namespace) -> int:
    if (args.run_id is None) == (args.scenario is None):
        print("pass exactly one of a run_id or --scenario <name>", file=sys.stderr)
        return 2

    run_id = args.run_id
    if run_id is None:
        run_id = _latest_run_id(args.scenario)
        if run_id is None:
            print(f"no runs found for scenario '{args.scenario}'", file=sys.stderr)
            return 1

    config = load_config(os.path.join(ORCH_DIR, "config.yaml"))
    scenario_id = _scenario_from_run_id(run_id)
    compiled = _build_graph(scenario_id, config).compile(checkpointer=get_checkpointer(STATE_DIR))
    snap = compiled.get_state({"configurable": {"thread_id": run_id}})
    if not snap.values:
        print(f"no such run: {run_id}", file=sys.stderr)
        return 1
    print(json.dumps({
        "run_id": run_id,
        "stage_statuses": snap.values.get("stage_statuses", {}),
        "blocked_on": snap.next or None,
    }, indent=2))

    if args.open_report:
        report_path = os.path.join(STATE_DIR, "runs", f"{run_id}.report.html")
        if os.path.exists(report_path):
            webbrowser.open(f"file://{os.path.abspath(report_path)}")
        else:
            print(f"no report found at {report_path} (run hasn't finished, or was interrupted "
                  f"before completion)", file=sys.stderr)
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    for path in sorted(glob.glob(os.path.join(STATE_DIR, "runs", "*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        print(f"{data['run_id']:40s} {data['scenario_id']:12s} {data['status']}")
    return 0


_EPILOG = """\
examples:
  ./zypit run --scenario greenfield              start a new run
  ./zypit run --scenario greenfield --open       ...and open its HTML report when done
  ./zypit approve <run_id> --by "Jane" --decision approve
                                                  record an approval, then re-run to resume it:
  ./zypit run --scenario greenfield --run-id <run_id>
  ./zypit status <run_id>                        inspect one run's stage statuses
  ./zypit status --scenario greenfield --open    latest greenfield run; open its HTML report
  ./zypit list                                   list every run and its final status

scenarios: greenfield, brownfield, ambiguous — see ../README.md and ./README.md for what each
one demonstrates and real example output from a full run of each.
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="zypit",
        description="zyp SDLC orchestrator — a LangGraph StateGraph that builds and gates ../service.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run (or resume) a scenario")
    p_run.add_argument("--scenario", required=True, choices=VALID_SCENARIOS)
    p_run.add_argument("--run-id", default=None, help="resume an existing run instead of starting a new one")
    p_run.add_argument("--open", dest="open_report", action="store_true",
                        help="open the HTML report in a browser once the run finishes")
    p_run.set_defaults(func=cmd_run)

    p_approve = sub.add_parser("approve", help="record a human approval decision")
    p_approve.add_argument("run_id")
    p_approve.add_argument("--by", required=True, help="approver name/identity")
    p_approve.add_argument("--decision", required=True, choices=["approve", "reject"])
    p_approve.add_argument("--comment", default="")
    p_approve.set_defaults(func=cmd_approve)

    p_status = sub.add_parser("status", help="print run state")
    p_status.add_argument("run_id", nargs="?", default=None,
                           help="omit and pass --scenario instead to inspect the latest run")
    p_status.add_argument("--scenario", choices=VALID_SCENARIOS, default=None,
                           help="look up the latest run of this scenario instead of a specific run_id")
    p_status.add_argument("--open", dest="open_report", action="store_true",
                           help="open the run's HTML report in a browser")
    p_status.set_defaults(func=cmd_status)

    p_list = sub.add_parser("list", help="list all runs")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
