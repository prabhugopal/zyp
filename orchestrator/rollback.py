"""Git-snapshot-based rollback for a stage's declared paths — used when a retryable stage
exhausts its retries. A targeted `git checkout <snapshot> -- <paths>`, not a blanket
`reset --hard`, so it can only touch what the stage was ever allowed to change.
"""

from __future__ import annotations

import subprocess


def git_head(repo_root: str) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root,
                             capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def rollback_paths(repo_root: str, snapshot: str, paths: list[str]) -> bool:
    if not snapshot or not paths:
        return False
    result = subprocess.run(["git", "checkout", snapshot, "--", *paths], cwd=repo_root,
                             capture_output=True, text=True, check=False)
    return result.returncode == 0
