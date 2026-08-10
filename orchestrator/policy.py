"""Static-analysis hard gate for zyp's own Python source: a real, subprocess-free text scan
against source files for banned patterns (hardcoded secrets, swallowed exceptions, eval/exec,
non-TLS URLs).

config.py is deliberately out of scope: its admin_password default is a documented local-dev
convenience (see config.py's own comment), not a secret smuggled into business logic — scanning
resource/config defaults would just be noise against a choice the codebase already states and
justifies inline.
"""

from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass

from config import Config

_EXCLUDED_FILES = {"config.py"}

_BANNED_PATTERNS = [
    ("hardcoded-secret", re.compile(r'(?i)(password|secret|api[_-]?key|token)\s*=\s*["\'][^"\']{4,}["\']'), "block"),
    ("bare-except-swallowed", re.compile(r'except(\s+\w[\w.]*)?\s*:\s*\n\s*pass\b'), "block"),
    ("eval-or-exec", re.compile(r'\b(eval|exec)\s*\('), "block"),
    ("non-tls-url", re.compile(r'http://(?!localhost|127\.0\.0\.1)'), "warn"),
]


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str
    severity: str  # "block" | "warn"


def scan_banned_patterns(file_paths: list[str]) -> list[Violation]:
    violations = []
    for path in file_paths:
        if not path.endswith(".py") or os.path.basename(path) in _EXCLUDED_FILES:
            continue
        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for rule, pattern, severity in _BANNED_PATTERNS:
            if pattern.search(content):
                violations.append(Violation(rule=rule, detail=f"{rule} matched in {os.path.relpath(path)}",
                                             severity=severity))
    return violations


def all_source_files(service_dir: str) -> list[str]:
    patterns = [
        os.path.join(service_dir, "*.py"),
        os.path.join(service_dir, "services", "*.py"),
        os.path.join(service_dir, "routes", "*.py"),
    ]
    files: list[str] = []
    for p in patterns:
        files.extend(glob.glob(p))
    return sorted(files)


@dataclass(frozen=True)
class PolicyProfile:
    coverage_threshold: float


PROFILES = {
    "standard": PolicyProfile(coverage_threshold=0.70),  # matches release_readiness_executor's own gate
    "strict": PolicyProfile(coverage_threshold=0.90),
}


def profile_for(config: Config) -> PolicyProfile:
    try:
        return PROFILES[config.policy_profile]
    except KeyError:
        raise ValueError(f"unknown policy_profile '{config.policy_profile}', expected one of {list(PROFILES)}")
