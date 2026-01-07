from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict


def run_git(args, cwd: Path, allow_fail: bool = False) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        if allow_fail:
            return ""
        output = result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed"
        raise RuntimeError(output)
    return result.stdout.strip()


def git_branch_exists(branch: str, cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=cwd,
    )
    return result.returncode == 0


def inspect_worktree(path: Path) -> Dict[str, int | bool | str]:
    if not path.exists():
        return {}
    dirty = bool(run_git(["status", "--porcelain"], path, allow_fail=True))
    ahead = behind = 0
    upstream = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], path, allow_fail=True)
    if upstream:
        counts = run_git(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"], path, allow_fail=True)
        try:
            behind_str, ahead_str = counts.split()
            behind = int(behind_str)
            ahead = int(ahead_str)
        except Exception:
            ahead = behind = 0
    return {"dirty": dirty, "ahead": ahead, "behind": behind, "upstream": upstream}
