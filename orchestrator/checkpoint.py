"""The durable-execution backbone: a LangGraph SqliteSaver checkpointer. This is what makes the
interrupt()-based approval gate survive across separate CLI invocations — `run` blocks at
interrupt(), the process exits, and a later `approve` + `run --run-id` in a brand-new process
reconnects to the same sqlite file and resumes exactly where it paused. Replaces the original
orchestrator's hand-rolled file-based ApprovalStore with a native LangGraph primitive.
"""

from __future__ import annotations

import os
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver


def get_checkpointer(state_dir: str) -> SqliteSaver:
    os.makedirs(state_dir, exist_ok=True)
    conn = sqlite3.connect(os.path.join(state_dir, "checkpoints.sqlite"), check_same_thread=False)
    return SqliteSaver(conn)
