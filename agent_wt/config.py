from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .errors import UserError
from .git_utils import inspect_worktree


def config_path(ctx) -> Path:
    return ctx.common_dir / "agent-wt" / "config.json"


def read_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        return {"version": 1, "worktrees": {}}
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("worktrees", {})
        return data
    except Exception as exc:  # noqa: BLE001
        return {"version": 1, "worktrees": {}}


def write_config(config_path: Path, data: Dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def serialize_worktree(name: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(entry.get("path", ""))
    exists = path.exists()
    git_state = {}
    try:
        git_state = inspect_worktree(path)
    except Exception:
        git_state = {}
    return {
        "name": name,
        "path": str(path),
        "branch": entry.get("branch", ""),
        "base": entry.get("base", ""),
        "agent": entry.get("agent", ""),
        "command": entry.get("command", ""),
        "env": entry.get("env", {}),
        "createdAt": entry.get("createdAt", ""),
        "status": "ready" if exists else "missing",
        "dirty": git_state.get("dirty"),
        "ahead": git_state.get("ahead"),
        "behind": git_state.get("behind"),
        "upstream": git_state.get("upstream"),
    }


def list_worktrees(ctx) -> List[Dict[str, Any]]:
    cfg = read_config(config_path(ctx))
    return [serialize_worktree(name, entry) for name, entry in cfg["worktrees"].items()]


def get_worktree_entry(ctx, name: str) -> Dict[str, Any]:
    cfg = read_config(config_path(ctx))
    entry = cfg["worktrees"].get(name)
    if not entry:
        raise UserError(f'Worktree "{name}" is not tracked. Use "agent-wt create {name}" first.')
    return entry
