"""Lightweight, dependency-free progress indicator for long-running stage steps (LLM calls,
subprocess-backed test/lint runs). Prints an elapsing-seconds spinner on a TTY only; stays quiet
when stdout isn't a TTY (piped to a file, captured by another process) so a carriage-return
animation never corrupts a log."""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager

_FRAMES = "|/-\\"


@contextmanager
def spinner(label: str):
    if not sys.stdout.isatty():
        yield
        return

    stop = threading.Event()

    def _run() -> None:
        start = time.monotonic()
        i = 0
        while not stop.wait(0.15):
            elapsed = time.monotonic() - start
            sys.stdout.write(f"\r  {label} {_FRAMES[i % len(_FRAMES)]} {elapsed:.0f}s")
            sys.stdout.flush()
            i += 1

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)
        sys.stdout.write("\r" + " " * (len(label) + 12) + "\r")
        sys.stdout.flush()
