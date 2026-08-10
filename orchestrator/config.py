"""Declarative run configuration: one frozen dataclass, loaded from config.yaml with env-var
overrides, passed by reference through the graph instead of threading dict.get() calls everywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

import yaml

DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"


@dataclass(frozen=True)
class Config:
    model_provider: str = "ollama"    # "ollama" | "anthropic"
    model_name: str | None = None     # defaults per-provider below if unset
    rag_backend: str = "keyword"      # "keyword" | "none" — see rag.py
    policy_profile: str = "standard"  # "standard" | "strict" — see policy.py

    @property
    def resolved_model_name(self) -> str:
        if self.model_name:
            return self.model_name
        return DEFAULT_ANTHROPIC_MODEL if self.model_provider == "anthropic" else DEFAULT_OLLAMA_MODEL


def load_config(path: str = "config.yaml") -> Config:
    values: dict = {}
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            values.update(yaml.safe_load(f) or {})
    known = {f.name for f in fields(Config)}
    for key in known:
        env_val = os.environ.get(key.upper())
        if env_val:
            values[key] = env_val
    return Config(**{k: v for k, v in values.items() if k in known})
