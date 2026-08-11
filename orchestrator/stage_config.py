"""Loads per-stage retry/rollback metadata from stages.yaml. See that file's header comment for
why only this data — not graph topology — is declarative."""

from __future__ import annotations

import os

import yaml

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stages.yaml")


def _load() -> dict:
    with open(_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


_RAW = _load()
_STAGES = _RAW.get("stages", {})

DEFAULT_MAX_ATTEMPTS: int = _RAW.get("default_max_attempts", 1)
MAX_ATTEMPTS: dict[str, int] = {
    stage_id: cfg["max_attempts"] for stage_id, cfg in _STAGES.items() if "max_attempts" in cfg
}
ROLLBACK_PATHS: dict[str, list[str]] = {
    stage_id: cfg["rollback_paths"] for stage_id, cfg in _STAGES.items() if "rollback_paths" in cfg
}
