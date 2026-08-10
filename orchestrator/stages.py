"""Real stage executors for zyp's own SDLC — the Python/pytest analogue of sLink's
stages_sdlc.py. Every PASSED/FAILED here is backed by a real command's exit code or a real file's
content: implementation stages check the actual service modules import cleanly (the Python
analogue of `gradlew compileJava`), testing stages run real `uv run pytest` and parse the real
JUnit XML / coverage JSON output, static analysis runs the real scan in policy.py.

Mirrors sLink's stages_sdlc.py's own choice to have unit_testing run the *full* suite (for its
coverage figure and total pass count) and integration_testing separately re-run just its own
subset — two real, independent test invocations, not one run's output reused for both.
"""

from __future__ import annotations

import json
import os
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import policy

JUNIT_UNIT = ".zyp-junit-unit.xml"
JUNIT_INTEGRATION = ".zyp-junit-integration.xml"
COVERAGE_JSON = ".zyp-coverage.json"


@dataclass
class StageResult:
    success: bool
    detail: str
    data: dict = field(default_factory=dict)
    transient: bool = False


@dataclass
class GateResult:
    passed: bool
    detail: str


def _check_artifact(scenario_dir: str, filename: str, required_markers: list[str] | None = None,
                     min_length: int = 150) -> GateResult:
    path = os.path.join(scenario_dir, "artifacts", filename)
    if not os.path.exists(path):
        return GateResult(False, f"artifact '{filename}' does not exist")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if len(content) < min_length:
        return GateResult(False, f"artifact '{filename}' is only {len(content)} chars (min {min_length})")
    for marker in required_markers or []:
        if marker not in content:
            return GateResult(False, f"artifact '{filename}' is missing required content: '{marker}'")
    return GateResult(True, f"artifact '{filename}' present ({len(content)} chars) and well-formed")


def _run_uv(service_dir: str, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["uv", "run", *args], cwd=service_dir, capture_output=True, text=True, timeout=timeout)


def _module_imports(service_dir: str, module: str) -> tuple[bool, str]:
    result = _run_uv(service_dir, "python", "-c", f"import {module}")
    return result.returncode == 0, (result.stderr[-500:] if result.returncode != 0 else "")


def _parse_junit(service_dir: str, xml_name: str) -> tuple[int, int, int]:
    path = os.path.join(service_dir, xml_name)
    if not os.path.exists(path):
        return 0, 0, 0
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return 0, 0, 0
    return int(suite.get("tests", 0)), int(suite.get("failures", 0)), int(suite.get("errors", 0))


def parse_coverage(service_dir: str) -> float | None:
    path = os.path.join(service_dir, COVERAGE_JSON)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["totals"]["percent_covered"] / 100.0


# --------------------------------------------------------------------------- stage executors

def requirements_executor(scenario_dir: str) -> StageResult:
    gate = _check_artifact(scenario_dir, "requirements.md", required_markers=["## Assumptions"])
    return StageResult(gate.passed, gate.detail, data={"requirements_ready": gate.passed})


def architecture_design_executor(scenario_dir: str) -> StageResult:
    gate = _check_artifact(scenario_dir, "design.md", required_markers=["```mermaid"])
    return StageResult(gate.passed, gate.detail, data={"design_ready": gate.passed})


def documentation_executor(scenario_dir: str) -> StageResult:
    gate = _check_artifact(scenario_dir, "documentation.md", required_markers=["## What shipped"])
    return StageResult(gate.passed, gate.detail, data={"documentation_ready": gate.passed})


def implementation_core_executor(service_dir: str) -> StageResult:
    for module in ("services.link_service", "routes.links", "routes.redirect"):
        ok, err = _module_imports(service_dir, module)
        if not ok:
            return StageResult(False, f"{module} failed to import: {err}", transient=True)
    return StageResult(True, "core link service + routes import cleanly")


def implementation_storage_executor(service_dir: str) -> StageResult:
    for module in ("redis_client", "rate_limit"):
        ok, err = _module_imports(service_dir, module)
        if not ok:
            return StageResult(False, f"{module} failed to import: {err}", transient=True)
    return StageResult(True, "redis_client + rate_limit import cleanly")


def implementation_analytics_executor(service_dir: str) -> StageResult:
    ok, err = _module_imports(service_dir, "services.analytics_service")
    if not ok:
        return StageResult(False, f"services.analytics_service failed to import: {err}", transient=True)
    return StageResult(True, "analytics service imports cleanly")


def unit_testing_executor(service_dir: str) -> StageResult:
    result = _run_uv(service_dir, "pytest", "tests/", "-q", f"--junitxml={JUNIT_UNIT}",
                      "--cov=.", f"--cov-report=json:{COVERAGE_JSON}")
    tests, failures, errors = _parse_junit(service_dir, JUNIT_UNIT)
    if result.returncode != 0 or failures or errors:
        return StageResult(False, f"{failures} failing / {errors} erroring of {tests} tests", transient=True)
    return StageResult(True, f"{tests} tests passed", data={"unit_test_count": tests})


def static_analysis_executor(service_dir: str) -> StageResult:
    files = policy.all_source_files(service_dir)
    violations = policy.scan_banned_patterns(files)
    blocking = [v for v in violations if v.severity == "block"]
    if blocking:
        return StageResult(False, f"{len(blocking)} banned pattern(s) found, e.g. {blocking[0].detail}",
                            transient=False)
    return StageResult(True, f"scanned {len(files)} source files, no banned patterns")


def integration_testing_executor(service_dir: str) -> StageResult:
    result = _run_uv(service_dir, "pytest", "tests/integration", "-q", f"--junitxml={JUNIT_INTEGRATION}")
    tests, failures, errors = _parse_junit(service_dir, JUNIT_INTEGRATION)
    if result.returncode != 0 or failures or errors:
        return StageResult(False, f"{failures} failing / {errors} erroring of {tests} integration tests",
                            transient=True)
    return StageResult(True, f"{tests} integration tests passed", data={"integration_test_count": tests})


def release_readiness_executor(service_dir: str) -> StageResult:
    result = _run_uv(service_dir, "pytest", "tests/", "-q", "--cov=.", "--cov-fail-under=70")
    if result.returncode != 0:
        return StageResult(False, f"full verification (tests + coverage gate) failed: {result.stdout[-800:]}",
                            transient=False)
    return StageResult(True, "full verification (tests + 70% coverage gate) passed; ready to release")
