"""Adds orchestrator/ itself to sys.path once, so every node module in this package can
`import stages`, `from config import Config`, etc. regardless of how the process was launched."""

import os
import sys

_ORCH_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ORCH_DIR not in sys.path:
    sys.path.insert(0, _ORCH_DIR)
