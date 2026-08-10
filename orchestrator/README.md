# zyp orchestrator

A LangGraph `StateGraph` that builds and gates `../service` end to end. See the
[top-level README](../README.md) for the architecture, control flow, and key decisions — this
document covers configuration, the CLI, and what a completed run demonstrates.

## Configuration

`config.yaml` (env vars override, uppercased field name):

| Key | Values | Default | Effect |
|---|---|---|---|
| `model_provider` | `ollama`, `anthropic` | `ollama` | Backend for the two LLM reasoning nodes |
| `model_name` | any model id | provider default (`llama3.2:3b` / `claude-haiku-4-5`) | Overrides the default model |
| `rag_backend` | `keyword`, `none` | `keyword` | Retrieval grounding for the requirements node |
| `policy_profile` | `standard`, `strict` | `standard` | Coverage-gate threshold: 70% or 90% |

Using `model_provider: anthropic` requires `ANTHROPIC_API_KEY` in the environment; there is no
other credential requirement to run the orchestrator.

## CLI

```bash
uv run python cli.py run --scenario <name>              # start or resume a run
uv run python cli.py approve <run_id> --by "<name>" --decision approve|reject
uv run python cli.py status <run_id>
uv run python cli.py list
```

Each `run` invocation prints its `run_id`. A run that reaches the approval gate exits with
`status=BLOCKED` and the exact `approve` command to run next. Approval decisions are written to
`state/approvals/<run_id>.json`; re-running `run --run-id <run_id>` after an approval resumes the
graph from the checkpoint that captured the `interrupt()`.

## What a completed greenfield run verifies

A `run --scenario greenfield` executes real commands against `../service`:

- `requirements` and `architecture_design` check the scenario's artifact files for required
  content, then the requirements node runs a live LLM call against the requirements text for an
  ambiguity analysis, attached to the run's output as advisory text.
- The three `implementation_*` stages import the corresponding service modules; an import error
  fails the stage.
- `unit_testing` runs `uv run pytest tests/ --junitxml=... --cov=. --cov-report=json=...` inside
  `../service` and parses the resulting JUnit XML and coverage JSON. A coverage figure below the
  configured threshold fails the stage even if every test passed.
- `static_analysis` scans the service source for banned patterns (hardcoded secrets, swallowed
  exceptions, `eval`/`exec`, non-TLS URLs); on success, a second LLM call reviews a sample of the
  source for design and maintainability concerns, attached as advisory text.
- `integration_testing` runs `uv run pytest tests/integration` as an independent second test
  invocation.
- `approval` halts the graph via `interrupt()`. The state persists in
  `state/checkpoints.sqlite`; a separate process reconnecting to that file and issuing the
  matching `approve` + `run --run-id` resumes execution from that exact point — this was verified
  by running `approve` and the resuming `run` as genuinely separate process invocations, not by
  simulating a pause within one process.
- `release_readiness` runs a full coverage-gated `pytest` pass as the terminal check.

## A bug found while building this

The three fan-in nodes (`implementation_join`, `integration_testing_join`, `release_join`) were
initially built without `defer=True`. LangGraph schedules nodes in supersteps keyed by graph
distance from the fork point, not by completion order; a join whose incoming paths differ in hop
count — `static_analysis -> code_review -> join` is one hop longer than `unit_testing -> join` on
a pass, and a retry loop adds a variable number of further hops — fires once per arriving
superstep rather than once total. This was caught because it re-ran a real, expensive step twice:
`integration_testing`, a live `pytest` invocation, executed twice in a single run before the fix.
Adding `defer=True` to each join node makes it wait until every pending task in the run has
settled, regardless of path length or retry count, and resolved it. See `graph.py`'s module
docstring for the fix in context.
