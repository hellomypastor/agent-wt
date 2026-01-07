from pathlib import Path

from agent_wt.config import config_path, read_config, serialize_worktree, write_config
from agent_wt.core import Ctx


def test_read_write_config(tmp_path):
    ctx = Ctx(root=tmp_path, common_dir=tmp_path / ".git")
    cfg_file = config_path(ctx)
    data = {"version": 1, "worktrees": {"demo": {"path": str(tmp_path / "demo"), "branch": "wt/demo"}}}
    write_config(cfg_file, data)
    loaded = read_config(cfg_file)
    assert loaded["worktrees"]["demo"]["branch"] == "wt/demo"


def test_serialize_worktree_missing_path():
    entry = {"path": "/nonexistent/path", "branch": "wt/x", "agent": "codex"}
    data = serialize_worktree("x", entry)
    assert data["status"] == "missing"
