"""Renders a single run's checkpointed state into a self-contained HTML report — a human-readable
reference alongside the machine-readable state/runs/{run_id}.json summary. No template engine
dependency: the orchestrator project doesn't otherwise need Jinja2, so this stays plain string
building with html.escape at every insertion point.
"""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone

_STATUS_COLOR = {
    "COMPLETED": "#16a34a", "PASSED": "#16a34a",
    "FAILED": "#dc2626", "ROLLED_BACK": "#d97706",
    "BLOCKED_ON_APPROVAL": "#2563eb",
}

_STYLE = """
  body { font-family: -apple-system, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
  h1 { font-size: 1.3rem; margin-bottom: 0.25rem; }
  .badge { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; color: white; font-size: 0.8rem; font-weight: 600; }
  .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem;
             border: 1px solid #e5e5e5; border-radius: 10px; padding: 1rem 1.2rem; margin: 1rem 0 1.5rem; background: #fafafa; }
  .summary .item .label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; color: #888; }
  .summary .item .value { font-size: 0.95rem; font-weight: 600; margin-top: 0.1rem; }
  .stages { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0 1.5rem; }
  .stage { border: 1px solid #e5e5e5; border-radius: 6px; padding: 0.4rem 0.7rem; font-size: 0.85rem; }
  .stage .name { font-weight: 600; }
  h2 { font-size: 1.05rem; margin-top: 2rem; }
  .entry { border-left: 3px solid #e5e5e5; padding: 0.5rem 0 0.5rem 0.9rem; margin-bottom: 0.6rem; }
  .entry.pass { border-color: #16a34a; }
  .entry.fail { border-color: #dc2626; }
  .entry .stage-label { font-weight: 600; font-size: 0.85rem; }
  .entry .kind { color: #888; font-size: 0.75rem; margin-left: 0.4rem; }
  .entry .duration { color: #888; font-size: 0.75rem; float: right; }
  .entry .detail { white-space: pre-wrap; font-size: 0.85rem; margin-top: 0.2rem; }
  code { background: #f2f2f2; padding: 0.1rem 0.35rem; border-radius: 3px; }
"""


def _summary_item(label: str, value: str) -> str:
    return (f'<div class="item"><div class="label">{html.escape(label)}</div>'
            f'<div class="value">{value}</div></div>')


def _badge(status: str) -> str:
    color = _STATUS_COLOR.get(status, "#666")
    return f'<span class="badge" style="background:{color}">{html.escape(status)}</span>'


def write_html_report(run_id: str, scenario_id: str, model_label: str, overall: str,
                       final_values: dict, out_dir: str) -> str:
    stage_statuses = final_values.get("stage_statuses", {})
    messages = final_values.get("messages", [])

    passed = sum(1 for s in stage_statuses.values() if s == "PASSED")
    failed = sum(1 for s in stage_statuses.values() if s in ("FAILED", "ROLLED_BACK"))
    total_duration = sum(m.get("duration_s") or 0 for m in messages)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    summary = "".join([
        _summary_item("Scenario", html.escape(scenario_id)),
        _summary_item("Status", _badge(overall)),
        _summary_item("Model", html.escape(model_label)),
        _summary_item("Stages", f"{passed} passed / {failed} failed of {len(stage_statuses)}"),
        _summary_item("Total time", f"{total_duration:.1f}s"),
        _summary_item("Generated", generated_at),
    ])

    stage_cards = "\n".join(
        f'<div class="stage"><span class="name">{html.escape(stage)}</span><br>{_badge(status)}</div>'
        for stage, status in stage_statuses.items()
    )

    entries = []
    for m in messages:
        stage = html.escape(str(m.get("stage", "")))
        kind = html.escape(str(m.get("kind", "")))
        success = m.get("success")
        css = "pass" if success else ("fail" if success is False else "")
        duration = m.get("duration_s")
        duration_html = f'<span class="duration">{duration:.1f}s</span>' if duration is not None else ""
        detail = html.escape(str(m.get("detail", "")))
        entries.append(
            f'<div class="entry {css}">{duration_html}'
            f'<span class="stage-label">{stage}</span><span class="kind">{kind}</span>'
            f'<div class="detail">{detail}</div></div>'
        )

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>zyp orchestrator run {html.escape(run_id)}</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>{html.escape(run_id)}</h1>
<div class="summary">{summary}</div>
<div class="stages">{stage_cards}</div>
<h2>Run trace</h2>
{"".join(entries) or "<p>No stages ran.</p>"}
</body>
</html>
"""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{run_id}.report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
