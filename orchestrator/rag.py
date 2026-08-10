"""Minimal, dependency-free retrieval: ranks candidate documents by keyword overlap with a query
and returns the top matches. This is RAG_BACKEND=keyword, the only backend implemented — a
deliberate scoping call, not an oversight. The corpus here (a handful of markdown files per
scenario, plus a few recent run reports) is small enough that an embeddings pipeline would add
dependency weight without improving retrieval quality. RAG_BACKEND=none skips retrieval entirely
and lets the reasoning node work from the raw artifact text it already reads directly. Swap in an
embeddings backend behind the same retrieve() signature if the corpus ever grows past what
keyword ranking handles well.
"""

from __future__ import annotations

import glob
import os
import re
from collections import Counter

from config import Config

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{2,}")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _load_corpus(scenario_dir: str, state_dir: str, scenario_id: str) -> list[tuple[str, str]]:
    """(source_label, content) pairs: the current scenario's artifacts + request, plus its most
    recent past run reports — so a reasoning node can ground itself in prior real runs, not just
    the current request text."""
    docs: list[tuple[str, str]] = []
    for path in sorted(glob.glob(os.path.join(scenario_dir, "artifacts", "*.md"))):
        with open(path, encoding="utf-8") as f:
            docs.append((os.path.basename(path), f.read()))
    for path in sorted(glob.glob(os.path.join(scenario_dir, "*.md"))):
        with open(path, encoding="utf-8") as f:
            docs.append((os.path.basename(path), f.read()))
    report_pattern = os.path.join(state_dir, "runs", f"{scenario_id}-*.report.md")
    for path in sorted(glob.glob(report_pattern))[-3:]:
        with open(path, encoding="utf-8") as f:
            docs.append((os.path.basename(path), f.read()))
    return docs


def retrieve(query: str, scenario_dir: str, state_dir: str, scenario_id: str,
             config: Config, top_k: int = 3, max_chars_per_doc: int = 1200) -> str:
    """Returns a formatted context block ready to interpolate into a prompt, or '' if retrieval is
    disabled or the corpus is empty."""
    if config.rag_backend == "none":
        return ""
    if config.rag_backend != "keyword":
        raise ValueError(f"unknown rag_backend '{config.rag_backend}', expected 'keyword' or 'none'")

    docs = _load_corpus(scenario_dir, state_dir, scenario_id)
    if not docs:
        return ""

    query_terms = set(_tokenize(query))
    scored = []
    for label, content in docs:
        if query_terms:
            term_counts = Counter(_tokenize(content))
            score = sum(term_counts[t] for t in query_terms)
        else:
            score = 0
        scored.append((score, label, content))
    scored.sort(key=lambda t: t[0], reverse=True)

    blocks = [f"--- {label} ---\n{content[:max_chars_per_doc]}" for _, label, content in scored[:top_k]]
    return "\n\n".join(blocks)
