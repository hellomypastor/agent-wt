from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import UserError
from .core import (
    SUPPORTED_AGENTS,
    Ctx,
    ensure_git_repo,
    ensure_macos,
    handle_commit,
    handle_create,
    handle_diff,
    handle_git,
    handle_info,
    handle_list,
    handle_open,
    handle_prune,
    handle_push,
    handle_remove,
    handle_run,
    handle_set,
    handle_set_env,
    log,
    log_error,
)

VERSION = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-wt", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="Show help and exit.")
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create", help="Create a git worktree for an agent.")
    create.add_argument("name", help="Worktree label.")
    create.add_argument("--agent", default="codex", help="Agent label (codex|claude|gemini).")
    create.add_argument("--base", default="main", help="Base ref for the worktree.")
    create.add_argument("--branch", help="Branch name to create (default: wt/<name>).")
    create.add_argument("--use-existing-branch", action="store_true", help="Attach to an existing branch instead of creating a new one.")
    create.add_argument("--path", help="Target directory for the worktree.")
    create.add_argument("--cmd", help="Command to start the agent (default: agent label).")
    create.add_argument("--start", action="store_true", help="Start the agent immediately after creation.")
    create.add_argument("--allow-dirty", action="store_true", help="Permit launching when the worktree is dirty.")
    create.add_argument(
        "--launch",
        choices=["spawn", "terminal", "iterm"],
        default="spawn",
        help="How to launch the agent when using --start (spawn in-place, Terminal, or iTerm).",
    )

    run = sub.add_parser("run", help="Start the agent inside its worktree.")
    run.add_argument("name", help="Worktree label.")
    run.add_argument("--agent", help="Agent label (codex|claude|gemini).")
    run.add_argument("--cmd", help="Command to start the agent.")
    run.add_argument("--allow-dirty", action="store_true", help="Permit launching when the worktree is dirty.")
    run.add_argument(
        "--launch",
        choices=["spawn", "terminal", "iterm"],
        default="spawn",
        help="Launch via current process (spawn), Terminal, or iTerm.",
    )

    list_cmd = sub.add_parser("list", help="List tracked worktrees.")
    list_cmd.add_argument("--json", dest="json_output", action="store_true", help="Output JSON.")

    info = sub.add_parser("info", help="Show one tracked worktree.")
    info.add_argument("name", help="Worktree label.")
    info.add_argument("--json", dest="json_output", action="store_true", help="Output JSON.")

    set_cmd = sub.add_parser("set", help="Update tracked metadata (agent/command/path).")
    set_cmd.add_argument("name", help="Worktree label to update.")
    set_cmd.add_argument("--agent", help="New agent label (codex|claude|gemini).")
    set_cmd.add_argument("--cmd", help="New command to launch the agent.")
    set_cmd.add_argument("--path", help="Override path if moved.")

    set_env = sub.add_parser("set-env", help="Update per-worktree environment variables.")
    set_env.add_argument("name", help="Worktree label to update.")
    set_env.add_argument("env", nargs="*", help="KEY=VALUE pairs to set/update.")
    set_env.add_argument("--unset", nargs="*", default=[], help="Keys to remove.")

    remove = sub.add_parser("remove", help="Untrack a worktree (optionally delete path/branch).")
    remove.add_argument("name", help="Worktree label to remove.")
    remove.add_argument("--delete-path", action="store_true", help="Delete the worktree path via git worktree remove --force.")
    remove.add_argument("--delete-branch", action="store_true", help="Delete the worktree branch.")
    remove.add_argument("--prune", action="store_true", help="Delete both path and branch (shorthand).")
    remove.add_argument("--force", action="store_true", help="Ignore missing paths/branches and continue.")

    prune = sub.add_parser("prune", help="Prune config entries with missing paths (optionally delete orphaned branches).")
    prune.add_argument("--delete-branch", action="store_true", help="Delete branches when pruning.")
    prune.add_argument("--orphaned-branch", action="store_true", help="Remove entries whose branch is missing (even if path exists).")
    prune.add_argument("--force", action="store_true", help="Keep going on branch delete failures.")
    prune.add_argument("--json", dest="json_output", action="store_true", help="Output JSON.")
    prune.add_argument("--dry-run", action="store_true", help="Do not write changes; just report.")

    git_cmd = sub.add_parser("git", help="Run git inside a tracked worktree.")
    git_cmd.add_argument("name", help="Worktree label.")
    git_cmd.add_argument("git_args", nargs=argparse.REMAINDER, help="Args after -- passed to git.")

    open_cmd = sub.add_parser("open", help="Open a shell in Terminal/iTerm at the worktree path.")
    open_cmd.add_argument("name", help="Worktree label.")
    open_cmd.add_argument(
        "--launch",
        choices=["terminal", "iterm"],
        default="terminal",
        help="Which app to open.",
    )

    diff_cmd = sub.add_parser("diff", help="Show git diff inside a worktree.")
    diff_cmd.add_argument("name", help="Worktree label.")
    diff_cmd.add_argument("git_args", nargs=argparse.REMAINDER, help="Extra args for git diff.")

    commit_cmd = sub.add_parser("commit", help="Add and commit inside a worktree.")
    commit_cmd.add_argument("name", help="Worktree label.")
    commit_cmd.add_argument("-m", "--message", required=True, help="Commit message.")
    commit_cmd.add_argument("-a", "--all", action="store_true", help="git add -A before commit.")

    push_cmd = sub.add_parser("push", help="Push a worktree branch.")
    push_cmd.add_argument("name", help="Worktree label.")
    push_cmd.add_argument("--remote", default="origin", help="Remote name (default origin).")
    push_cmd.add_argument("--branch", help="Branch name (default: tracked branch).")

    sub.add_parser("gui", help="Start a minimal GUI launcher (macOS).")
    sub.add_parser("version", help="Show version.")
    return parser


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    if not argv:
        parser.print_help()
        return

    args = parser.parse_args(argv)

    try:
        if args.command == "version":
            log(VERSION)
            return

        ensure_macos()
        ctx = ensure_git_repo(Path.cwd())

        if args.command == "create":
            handle_create(args, ctx)
        elif args.command == "run":
            handle_run(args, ctx)
        elif args.command == "list":
            handle_list(args, ctx)
        elif args.command == "info":
            handle_info(args, ctx)
        elif args.command == "set":
            handle_set(args, ctx)
        elif args.command == "set-env":
            handle_set_env(args, ctx)
        elif args.command == "remove":
            handle_remove(args, ctx)
        elif args.command == "prune":
            handle_prune(args, ctx)
        elif args.command == "git":
            handle_git(args, ctx)
        elif args.command == "open":
            handle_open(args, ctx)
        elif args.command == "diff":
            handle_diff(args, ctx)
        elif args.command == "commit":
            handle_commit(args, ctx)
        elif args.command == "push":
            handle_push(args, ctx)
        elif args.command == "gui":
            from .gui import run_gui  # late import to avoid tkinter dependency when unused
            run_gui(ctx)
        else:
            parser.print_help()
            sys.exit(1)
    except UserError as exc:
        log_error(str(exc))
        sys.exit(1)


__all__ = ["main", "build_parser", "VERSION"]
