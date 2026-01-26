from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    config_path,
    get_worktree_entry,
    list_worktrees,
    read_config,
    serialize_worktree,
    write_config,
)
from .errors import UserError
from .git_utils import git_branch_exists, inspect_worktree, run_git

SUPPORTED_AGENTS = ["codex", "claude", "gemini"]


def log(msg: str = "") -> None:
    sys.stdout.write(f"{msg}\n")


def log_error(msg: str) -> None:
    sys.stderr.write(f"[agent-wt] {msg}\n")


@dataclass
class Ctx:
    root: Path
    common_dir: Path


def ensure_macos() -> None:
    if platform.system().lower() != "darwin":
        raise UserError("This build is macOS-first; current platform is not macOS (darwin).")


def ensure_git_repo(cwd: Path) -> Ctx:
    try:
        root = Path(run_git(["rev-parse", "--show-toplevel"], cwd))
        common_dir = Path(run_git(["rev-parse", "--git-common-dir"], cwd))
        return Ctx(root=root, common_dir=common_dir)
    except Exception as exc:  # noqa: BLE001
        raise UserError(f"agent-wt must be run inside a git repository with worktree support. {exc}")


def default_worktree_path(repo_root: Path, name: str) -> Path:
    repo_base = repo_root.name
    parent = repo_root.parent
    return (parent / f"{repo_base}-{name}").resolve()


def default_agent_command(agent: str) -> str:
    if agent not in SUPPORTED_AGENTS:
        return ""
    env_key = f"AGENT_WT_CMD_{agent.upper()}"
    from_env = os.environ.get(env_key)
    if from_env:
        return from_env
    defaults = {
        "codex": "codex",
        "claude": "claude",
        "gemini": "gemini",
    }
    return defaults.get(agent, agent)


def escape_for_applescript(cmd: str) -> str:
    return cmd.replace("\\", "\\\\").replace('"', '\\"')


def merged_env(entry: Dict[str, Any]) -> Dict[str, str]:
    merged = dict(os.environ)
    extra = entry.get("env") or {}
    for key, val in extra.items():
        merged[str(key)] = str(val)
    return merged


def normalize_sandbox_entry(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    write_paths = raw.get("write")
    if not isinstance(write_paths, list):
        write_paths = []
    return {
        "enabled": bool(raw.get("enabled", False)),
        "profile": str(raw.get("profile", "")) if raw.get("profile") else "",
        "deny_network": bool(raw.get("deny_network", False)),
        "write": [str(path) for path in write_paths if path],
    }


def normalize_write_paths(paths: List[str]) -> List[str]:
    normalized = []
    for item in paths:
        if not item:
            continue
        normalized.append(str(Path(item).expanduser().resolve()))
    return normalized


def apply_sandbox_args(base: Dict[str, Any], ns) -> Dict[str, Any]:
    sandbox = normalize_sandbox_entry(base)
    if getattr(ns, "no_sandbox", False):
        return {"enabled": False, "profile": "", "deny_network": False, "write": []}
    if getattr(ns, "sandbox", False):
        sandbox["enabled"] = True
    if getattr(ns, "sandbox_profile", None):
        sandbox["profile"] = ns.sandbox_profile
        sandbox["enabled"] = True
    if getattr(ns, "sandbox_write", None) is not None:
        sandbox["write"] = normalize_write_paths(list(ns.sandbox_write))
        sandbox["enabled"] = True
    if getattr(ns, "sandbox_no_network", False):
        sandbox["deny_network"] = True
        sandbox["enabled"] = True
    if getattr(ns, "sandbox_network", False):
        sandbox["deny_network"] = False
        sandbox["enabled"] = True
    return sandbox


def escape_sbpl_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_sandbox_profile(
    worktree_path: Path,
    common_dir: Path,
    *,
    deny_network: bool,
    extra_writes: List[str],
) -> str:
    allow_writes = [
        worktree_path,
        common_dir,
        Path("/tmp"),
        Path("/private/tmp"),
        Path("/var/folders"),
        Path("/private/var/folders"),
    ]
    allow_writes += [Path(path) for path in extra_writes]

    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process*)",
        "(allow mach-lookup)",
        "(allow ipc-posix*)",
        "(allow sysctl-read)",
        "(allow file-read*)",
    ]
    if not deny_network:
        lines.append("(allow network*)")
    for path in allow_writes:
        escaped = escape_sbpl_string(str(path))
        lines.append(f'(allow file-write* (subpath "{escaped}"))')
    return "\n".join(lines) + "\n"


def ensure_sandbox_profile(ctx: Ctx, name: str, worktree_path: Path, sandbox: Dict[str, Any]) -> Path | None:
    sandbox = normalize_sandbox_entry(sandbox)
    if not sandbox.get("enabled"):
        return None
    if shutil.which("sandbox-exec") is None:
        raise UserError("sandbox-exec is required for --sandbox.")
    common_dir = ctx.common_dir
    if not common_dir.is_absolute():
        common_dir = (ctx.root / common_dir).resolve()
    profile_override = sandbox.get("profile") or ""
    if profile_override:
        profile_path = Path(profile_override).expanduser().resolve()
        if not profile_path.exists():
            raise UserError(f"sandbox profile does not exist: {profile_path}")
        return profile_path
    profile_dir = common_dir / "agent-wt" / "sandbox"
    profile_path = profile_dir / f"{name}.sb"
    profile_body = build_sandbox_profile(
        worktree_path,
        common_dir,
        deny_network=bool(sandbox.get("deny_network", False)),
        extra_writes=sandbox.get("write") or [],
    )
    profile_dir.mkdir(parents=True, exist_ok=True)
    if profile_path.exists():
        existing = profile_path.read_text(encoding="utf-8")
        if existing == profile_body:
            return profile_path
    profile_path.write_text(profile_body, encoding="utf-8")
    return profile_path


def wrap_command_with_sandbox(command: str, profile_path: Path) -> str:
    quoted_cmd = shlex.quote(command)
    return f"sandbox-exec -f {shlex.quote(str(profile_path))} /bin/sh -c {quoted_cmd}"


def run_in_macos_app(
    worktree_path: Path,
    command: str,
    app: str,
    *,
    entry: Dict[str, Any],
    sandbox_profile: Path | None = None,
) -> None:
    app = app.lower()
    if app == "spawn":
        return
    if app not in {"terminal", "iterm"}:
        raise UserError(f'Unsupported launch target "{app}". Use spawn, terminal, or iterm.')
    if shutil.which("osascript") is None:
        raise UserError("osascript is required to open Terminal/iTerm sessions.")

    env_parts = " ".join([f"{shlex.quote(k)}={shlex.quote(v)}" for k, v in (entry.get("env") or {}).items()])
    prefix = f"{env_parts} " if env_parts else ""
    shell_cmd = f"cd {shlex.quote(str(worktree_path))} && {prefix}{command}"
    if sandbox_profile:
        shell_cmd = wrap_command_with_sandbox(shell_cmd, sandbox_profile)
    quoted = escape_for_applescript(shell_cmd)

    if app == "terminal":
        script = f'tell application "Terminal"\\n activate\\n do script "{quoted}"\\nend tell'
    else:
        script = (
            'tell application "iTerm2"\\n'
            "  activate\\n"
            "  tell current window\\n"
            "    create tab with default profile\\n"
            f'    tell current session to write text "{quoted}"\\n'
            "  end tell\\n"
            "end tell"
        )
    result = subprocess.run(["osascript", "-e", script])
    if result.returncode != 0:
        raise UserError(f"Failed to launch {app} session (osascript exit {result.returncode}).")


def render_table(items, headers):
    rows = [[str(item.get(h, "")) for h in headers] for item in items]
    widths = [max(len(h), *(len(row[idx]) for row in rows)) for idx, h in enumerate(headers)]

    def fmt(row):
        return "  ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row))

    yield fmt(headers)
    yield fmt(["-" * w for w in widths])
    for row in rows:
        yield fmt(row)


def handle_create(ns, ctx: Ctx):
    name = ns.name
    agent = ns.agent.lower()
    if agent not in SUPPORTED_AGENTS:
        raise UserError(f'Unknown agent "{agent}". Supported: {", ".join(SUPPORTED_AGENTS)}')

    base = ns.base
    branch = ns.branch or (ns.use_existing_branch and name) or f"wt/{name}"
    target_path = Path(ns.path).expanduser().resolve() if ns.path else default_worktree_path(ctx.root, name)
    command = ns.cmd or default_agent_command(agent)

    if ns.use_existing_branch:
        if not git_branch_exists(branch, ctx.root):
            raise UserError(f"Branch {branch} does not exist; provide --branch pointing to an existing branch.")
        log(f"Creating git worktree at {target_path} using existing branch {branch}...")
        result = subprocess.run(
            ["git", "worktree", "add", str(target_path), branch],
            cwd=ctx.root,
        )
        if result.returncode != 0:
            raise UserError("git worktree add failed.")
        base_for_config = branch
    else:
        if git_branch_exists(branch, ctx.root):
            raise UserError(f"Branch {branch} already exists. Provide a different --branch or delete the branch first, or use --use-existing-branch.")
        log(f"Creating git worktree at {target_path} from {base} using branch {branch}...")
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(target_path), base],
            cwd=ctx.root,
        )
        if result.returncode != 0:
            raise UserError("git worktree add failed.")
        base_for_config = base

    cfg_path = config_path(ctx)
    config = read_config(cfg_path)
    sandbox = apply_sandbox_args({}, ns)
    config["worktrees"][name] = {
        "path": str(target_path),
        "branch": branch,
        "base": base_for_config,
        "agent": agent,
        "command": command,
        "env": {},
        "sandbox": sandbox,
        "createdAt": subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True, capture_output=True).stdout.strip(),
    }
    write_config(cfg_path, config)
    log(f'Worktree "{name}" ready at {target_path}.')

    if ns.start:
        handle_run(
            argparse.Namespace(  # type: ignore[arg-type]
                name=name,
                agent=agent,
                cmd=command,
                wait=True,
                launch=getattr(ns, "launch", "spawn"),
                allow_dirty=ns.allow_dirty,
            ),
            ctx,
        )


def handle_run(ns, ctx: Ctx, *, wait: Optional[bool] = None):
    name = ns.name
    wait = ns.wait if hasattr(ns, "wait") else wait
    launch = getattr(ns, "launch", "spawn")
    allow_dirty = getattr(ns, "allow_dirty", False)
    entry = get_worktree_entry(ctx, name)

    agent = (ns.agent or entry.get("agent") or "codex").lower()
    if agent not in SUPPORTED_AGENTS:
        raise UserError(f'Unknown agent "{agent}". Supported: {", ".join(SUPPORTED_AGENTS)}')

    worktree_path = Path(entry.get("path", ""))
    if not worktree_path.exists():
        raise UserError(f"Configured worktree path does not exist: {worktree_path}")

    command = ns.cmd or entry.get("command") or default_agent_command(agent)
    if not command:
        raise UserError('No command specified for this agent. Provide one with --cmd "<your agent command>".')

    if not allow_dirty:
        state = inspect_worktree(worktree_path)
        if state.get("dirty"):
            raise UserError("Worktree is dirty. Commit/stash or re-run with --allow-dirty.")

    sandbox = apply_sandbox_args(entry.get("sandbox", {}), ns)
    sandbox_profile = ensure_sandbox_profile(ctx, name, worktree_path, sandbox)

    if launch != "spawn":
        log(f'Starting {agent} in {worktree_path} via {launch} using "{command}"...')
        run_in_macos_app(worktree_path, command, launch, entry=entry, sandbox_profile=sandbox_profile)
        return

    log(f'Starting {agent} in {worktree_path} using "{command}"...')
    if sandbox_profile:
        command = wrap_command_with_sandbox(command, sandbox_profile)
    env = merged_env(entry)
    proc = subprocess.Popen(command, cwd=worktree_path, shell=True, env=env)  # noqa: S602
    if wait is None:
        wait = True
    if wait:
        proc.wait()
        raise SystemExit(proc.returncode or 0)
    return proc


def handle_list(ns, ctx: Ctx):
    items = list_worktrees(ctx)
    if ns.json_output:
        log(json.dumps({"worktrees": items}, indent=2))
        return
    if not items:
        log("No agent worktrees are tracked yet. Use `agent-wt create <name>` to add one.")
        return
    headers = ["name", "branch", "agent", "status", "dirty", "ahead", "behind", "path"]
    for line in render_table(items, headers):
        log(line)


def handle_info(ns, ctx: Ctx):
    name = ns.name
    entry = get_worktree_entry(ctx, name)
    data = serialize_worktree(name, entry)
    if ns.json_output:
        log(json.dumps(data, indent=2))
        return
    log(f"name:    {data['name']}")
    log(f"agent:   {data['agent']}")
    log(f"branch:  {data['branch']}")
    log(f"base:    {data['base']}")
    log(f"path:    {data['path']}")
    log(f"status:  {data['status']}")
    log(f"dirty:   {data.get('dirty')}")
    log(f"ahead:   {data.get('ahead')}, behind: {data.get('behind')}, upstream: {data.get('upstream')}")
    log(f"command: {data['command'] or '(not set)'}")
    if data.get("sandbox"):
        log(f"sandbox: {data['sandbox']}")
    log(f"created: {data['createdAt'] or '(unknown)'}")


def handle_set(ns, ctx: Ctx):
    name = ns.name
    cfg_path = config_path(ctx)
    cfg = read_config(cfg_path)
    entry = cfg["worktrees"].get(name)
    if not entry:
        raise UserError(f'Worktree "{name}" is not tracked.')

    changed = False
    if ns.agent:
        agent = ns.agent.lower()
        if agent not in SUPPORTED_AGENTS:
            raise UserError(f'Unknown agent "{agent}". Supported: {", ".join(SUPPORTED_AGENTS)}')
        entry["agent"] = agent
        changed = True
    if ns.cmd is not None:
        entry["command"] = ns.cmd
        changed = True
    if ns.path:
        entry["path"] = str(Path(ns.path).expanduser().resolve())
        changed = True
    sandbox = apply_sandbox_args(entry.get("sandbox", {}), ns)
    if sandbox != normalize_sandbox_entry(entry.get("sandbox", {})):
        entry["sandbox"] = sandbox
        changed = True
    if not changed:
        raise UserError("Nothing to update. Provide --agent, --cmd, --path, or --sandbox options.")

    cfg["worktrees"][name] = entry
    write_config(cfg_path, cfg)
    log(f'Updated "{name}".')


def handle_set_env(ns, ctx: Ctx):
    name = ns.name
    cfg_path = config_path(ctx)
    cfg = read_config(cfg_path)
    entry = cfg["worktrees"].get(name)
    if not entry:
        raise UserError(f'Worktree "{name}" is not tracked.')
    env = entry.get("env") or {}
    updates = ns.env or []
    removals = ns.unset or []
    for pair in updates:
        if "=" not in pair:
            raise UserError(f'Invalid env pair "{pair}", expected KEY=VALUE.')
        key, val = pair.split("=", 1)
        env[key] = val
    for key in removals:
        env.pop(key, None)
    entry["env"] = env
    cfg["worktrees"][name] = entry
    write_config(cfg_path, cfg)
    log(f'Updated env for "{name}".')


def handle_remove(ns, ctx: Ctx):
    name = ns.name
    cfg_path = config_path(ctx)
    cfg = read_config(cfg_path)
    entry = cfg["worktrees"].get(name)
    if not entry:
        raise UserError(f'Worktree "{name}" is not tracked.')

    delete_path = ns.delete_path or ns.prune
    delete_branch = ns.delete_branch or ns.prune

    worktree_path = Path(entry.get("path", ""))
    branch = entry.get("branch", "")

    if delete_path and worktree_path.exists():
        log(f"Removing worktree path {worktree_path} via git...")
        result = subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=ctx.root)
        if result.returncode != 0:
            if ns.force:
                log_error(f"Failed to remove worktree at {worktree_path} (git exit {result.returncode}), continuing (--force).")
            else:
                raise UserError(f"Failed to remove worktree at {worktree_path} (git exit {result.returncode}).")
    elif delete_path:
        log(f"Worktree path {worktree_path} missing; skipping path removal.")

    if delete_branch and branch:
        if git_branch_exists(branch, ctx.root):
            log(f"Deleting branch {branch}...")
            result = subprocess.run(["git", "branch", "-D", branch], cwd=ctx.root)
            if result.returncode != 0:
                if ns.force:
                    log_error(f"Failed to delete branch {branch} (git exit {result.returncode}), continuing (--force).")
                else:
                    raise UserError(f"Failed to delete branch {branch} (git exit {result.returncode}).")
        else:
            log(f"Branch {branch} missing; skipping branch deletion.")

    del cfg["worktrees"][name]
    write_config(cfg_path, cfg)
    log(f'Removed tracking for "{name}".')


def handle_prune(ns, ctx: Ctx):
    cfg_path = config_path(ctx)
    cfg = read_config(cfg_path)
    removed = []
    kept = {}
    for name, entry in cfg["worktrees"].items():
        path = Path(entry.get("path", ""))
        branch = entry.get("branch", "")
        missing_path = not path.exists()
        missing_branch = branch and not git_branch_exists(branch, ctx.root)
        if missing_path or (ns.orphaned_branch and missing_branch):
            if ns.delete_branch and branch and git_branch_exists(branch, ctx.root):
                log(f"[prune] deleting branch {branch}")
                res = subprocess.run(["git", "branch", "-D", branch], cwd=ctx.root)
                if res.returncode != 0 and not ns.force:
                    raise UserError(f"Failed to delete branch {branch} (git exit {res.returncode}).")
            removed.append({"name": name, "missing_path": missing_path, "missing_branch": missing_branch, "branch": branch})
        else:
            kept[name] = entry
    if removed and not ns.dry_run:
        cfg["worktrees"] = kept
        write_config(cfg_path, cfg)
    if ns.json_output:
        log(json.dumps({"removed": removed, "kept": list(kept.keys())}, indent=2))
        return
    if not removed:
        log("No missing worktrees to prune.")
        return
    for item in removed:
        msg = f'[prune] removed "{item["name"]}" (missing_path={item["missing_path"]}, missing_branch={item["missing_branch"]})'
        log(msg)


def handle_git(ns, ctx: Ctx):
    name = ns.name
    git_args = ns.git_args or []
    entry = get_worktree_entry(ctx, name)
    worktree_path = Path(entry.get("path", ""))
    if not worktree_path.exists():
        raise UserError(f"Worktree path does not exist: {worktree_path}")
    cmd = ["git", *git_args]
    log(f"[{name}] git {' '.join(git_args)}")
    result = subprocess.run(cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise UserError(f"git exited with {result.returncode}")


def handle_open(ns, ctx: Ctx):
    name = ns.name
    entry = get_worktree_entry(ctx, name)
    worktree_path = Path(entry.get("path", ""))
    if not worktree_path.exists():
        raise UserError(f"Worktree path does not exist: {worktree_path}")
    launch = ns.launch
    command = "exec $SHELL"
    run_in_macos_app(worktree_path, command, launch, entry=entry)
    log(f'Opened {name} in {launch}.')


def handle_diff(ns, ctx: Ctx):
    name = ns.name
    entry = get_worktree_entry(ctx, name)
    worktree_path = Path(entry.get("path", ""))
    if not worktree_path.exists():
        raise UserError(f"Worktree path does not exist: {worktree_path}")
    extra = ns.git_args or []
    cmd = ["git", "diff", *extra]
    result = subprocess.run(cmd, cwd=worktree_path)
    if result.returncode != 0:
        raise UserError(f"git diff exited with {result.returncode}")


def handle_commit(ns, ctx: Ctx):
    name = ns.name
    entry = get_worktree_entry(ctx, name)
    worktree_path = Path(entry.get("path", ""))
    if not worktree_path.exists():
        raise UserError(f"Worktree path does not exist: {worktree_path}")
    msg = ns.message
    if not msg:
        raise UserError("Commit message is required (-m/--message).")
    add_args = ["git", "add"]
    add_args += ["-A"] if ns.all else ["."]
    log(f"[{name}] {' '.join(add_args)}")
    res_add = subprocess.run(add_args, cwd=worktree_path)
    if res_add.returncode != 0:
        raise UserError(f"git add failed with {res_add.returncode}")
    commit_cmd = ["git", "commit", "-m", msg]
    log(f"[{name}] {' '.join(commit_cmd)}")
    res_commit = subprocess.run(commit_cmd, cwd=worktree_path)
    if res_commit.returncode != 0:
        raise UserError(f"git commit failed with {res_commit.returncode}")
    log("Commit created.")


def handle_push(ns, ctx: Ctx):
    name = ns.name
    entry = get_worktree_entry(ctx, name)
    worktree_path = Path(entry.get("path", ""))
    if not worktree_path.exists():
        raise UserError(f"Worktree path does not exist: {worktree_path}")
    branch = ns.branch or entry.get("branch")
    if not branch:
        raise UserError("Branch is unknown; specify --branch.")
    remote = ns.remote or "origin"
    cmd = ["git", "push", remote, branch]
    log(f"[{name}] {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=worktree_path)
    if res.returncode != 0:
        raise UserError(f"git push failed with {res.returncode}")
