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

`./zypit` is a thin wrapper around `uv run python cli.py` — same commands, shorter to type:

```bash
./zypit run --scenario <name>              # start or resume a run
./zypit approve <run_id> --by "<name>" --decision approve|reject
./zypit status <run_id>                    # or: ./zypit status --scenario <name>  (latest run)
./zypit list
```

`status --scenario <name>` looks up the most recent run of that scenario without needing its exact
`run_id`; add `--open` to either `run` or `status` to open the run's HTML report in a browser.

(equivalently: `uv run python cli.py run --scenario <name>`, etc.)

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

## Progress output and reports

Each stage prints a `running...` line as soon as it starts (not just its result), and the two
LLM-backed steps additionally print which model they're calling before the request goes out — this
matters for the local Ollama path, where a single `llama3.2:3b` call can take a minute or more.
On an interactive terminal, a spinner shows elapsed seconds while a stage is in flight; it's
suppressed automatically when stdout isn't a TTY (piped output, log files) so it never corrupts a
captured transcript. Ctrl-C during a run is caught and prints the exact resume command instead of a
raw traceback — the run is checkpointed up to its last completed stage either way.

At the end of every run, `cli.py` writes `state/runs/<run_id>.report.html` — a self-contained
summary (status, model, per-stage pass/fail, and the full trace of deterministic results and LLM
reasoning text) alongside the existing `<run_id>.json`. Pass `--open` to `run` to open it in a
browser automatically once the run finishes.

## Example runs

All three scenarios below are real, checked-in runs — `state/runs/<run_id>.json` and
`.report.html` are the actual output, not authored examples. Output is trimmed to the
stage-result lines; full LLM reasoning text is in the HTML report for each run.

### Greenfield — full build, clean pass

```
$ uv run python cli.py run --scenario greenfield
run_id=greenfield-20260810T191325Z scenario=greenfield model=ollama/llama3.2:3b
  [requirements] PASSED (0.0s): artifact 'requirements.md' present (2725 chars) and well-formed
  [architecture_design] PASSED (0.0s): artifact 'design.md' present (2657 chars) and well-formed
  [documentation] PASSED (0.0s): artifact 'documentation.md' present (2029 chars) and well-formed
  [implementation_analytics] PASSED (0.1s): analytics service imports cleanly
  [implementation_storage] PASSED (0.5s): redis_client + rate_limit import cleanly
  [implementation_core] PASSED (1.5s): core link service + routes import cleanly
  [static_analysis] PASSED (0.0s): scanned 13 source files, no banned patterns
  [unit_testing] PASSED (2.7s): 49 tests passed
  [integration_testing] PASSED (2.2s): 21 integration tests passed
status=BLOCKED stage=release_readiness
  -> python3 cli.py approve greenfield-20260810T191325Z --by "<name>" --decision approve

$ uv run python cli.py approve greenfield-20260810T191325Z --by "Prabhu Gopal" --decision approve
$ uv run python cli.py run --scenario greenfield --run-id greenfield-20260810T191325Z
  [release_readiness] human decision: approve
  [release_readiness] PASSED (2.7s): full verification (tests + 70% coverage gate) passed; ready to release
status=COMPLETED
```

Every stage above ran a real command against `../service`: real imports, a real `pytest` run twice
(unit, then integration), a real coverage check. Nothing here is templated output.

### Brownfield — real fault, exhausted retries, real rollback

The feature (analytics CSV export) is real and already shipped in `../service`. This run replays
the fault that was hit while building it: an uncommitted edit to `routes/links.py` importing a
function (`format_csv_row`) that was never defined, seeded deliberately to demonstrate the retry
and rollback path against a real, deterministic break rather than a flaky one.

```
$ uv run python cli.py run --scenario brownfield
run_id=brownfield-20260810T184703Z scenario=brownfield model=ollama/llama3.2:3b
  [requirements] PASSED (0.0s): artifact 'requirements.md' present (1835 chars) and well-formed
  [architecture_design] PASSED (0.0s): artifact 'design.md' present (1344 chars) and well-formed
  [documentation] PASSED (0.0s): artifact 'documentation.md' present (881 chars) and well-formed
  [implementation_analytics] PASSED (0.0s): analytics service imports cleanly
  [implementation_storage] PASSED (0.0s): redis_client + rate_limit import cleanly
  [implementation_core] FAILED (attempt 1): routes.links failed to import: ImportError: cannot
    import name 'format_csv_row' from 'services.analytics_service'
  [implementation_core] FAILED (attempt 2): routes.links failed to import: ImportError: cannot
    import name 'format_csv_row' from 'services.analytics_service'
  [implementation_core] rolled back service/routes, service/services to 84cbbf7a0cb7 after
    exhausting retries
status=FAILED
```

`implementation_core` retried once (its configured max), failed identically both times against the
real broken import, and — because it exhausted retries rather than passing — the rollback node
reverted exactly the two paths (`service/routes`, `service/services`) it's declared to own, to the
git commit captured before the stage's first attempt. `git status` on `../service` after this run
shows nothing dirty: the rollback, not a manual `git checkout`, is what cleaned it up. The run
correctly ends `status=FAILED`, not `COMPLETED` — a caught fault with a clean rollback is still a
failed run, not a disguised success.

### Ambiguous — approval-gated interpretation, real mismatch, real clarification, real re-verification

"Make link analytics access more secure" doesn't say whether that means the aggregated summary
endpoint, the raw export endpoint, or both. The broader reading (both endpoints) is proposed for
approval; approving it commits the run to verifying *that* scope, not the narrower one that turns
out to be correct.

```
$ uv run python cli.py run --scenario ambiguous
run_id=ambiguous-20260810T185620Z scenario=ambiguous model=ollama/llama3.2:3b
  [requirements] PASSED (0.0s): artifact 'requirements.md' present (2063 chars) and well-formed
  [architecture_design] PASSED (0.0s): artifact 'design.md' present (1592 chars) and well-formed
status=BLOCKED stage=architecture_design
  -> python3 cli.py approve ambiguous-20260810T185620Z --by "<name>" --decision approve

$ uv run python cli.py approve ambiguous-20260810T185620Z --by "Prabhu Gopal" --decision approve
$ uv run python cli.py run --scenario ambiguous --run-id ambiguous-20260810T185620Z
  [architecture_design] human decision on interpreted scope: approve
  [documentation] PASSED (0.0s): artifact 'documentation.md' present (1477 chars) and well-formed
  [implementation_core] FAILED: approved (broad) scope requires auth on GET .../analytics too, not
    just .../export
  [implementation_analytics] PASSED (0.1s): analytics service imports cleanly
  [implementation_storage] PASSED (0.4s): redis_client + rate_limit import cleanly
  [implementation_core] FAILED: approved (broad) scope requires auth on GET .../analytics too, not
    just .../export
status=FAILED
```

The approved (broad) scope required auth on both endpoints; the actual code only had it on
`/export`. This is a genuine mismatch, not a scripted failure — `implementation_core_auth_executor`
re-reads `service/routes/links.py` on every attempt and reports exactly what it finds. Once a
clarification narrowing the scope to export-only arrived (`scenarios/ambiguous/clarification.md`),
a **fresh** run against the same unchanged code passed cleanly:

```
$ uv run python cli.py run --scenario ambiguous
run_id=ambiguous-20260810T190351Z scenario=ambiguous model=ollama/llama3.2:3b
  [architecture_design] human decision on interpreted scope: approve
  ...
  [implementation_core] PASSED (0.0s): auth scoped to .../analytics/export only, matching the
    clarified scope
  ...
  [release_readiness] PASSED (3.6s): full verification (tests + 70% coverage gate) passed; ready to release
status=COMPLETED
```

Same executor, same file on disk, different verdict — because the check reads
`clarification.md`'s presence at execution time rather than baking the interpretation into the
graph at build time. That's what lets a clarification change what the *next* run verifies without a
special-cased "replan" step.

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
