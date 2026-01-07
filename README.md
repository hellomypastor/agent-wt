# agent-wt
agent-wt is a macOS-first CLI that treats each Git worktree as an isolated execution sandbox for AI agents. It enables safe, parallel AI workflows by mapping one agent to one worktree—eliminating context conflicts, file collisions, and branch interference.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.8-blue)](#install)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](#what-this-build-does)
[![CLI](https://img.shields.io/badge/agent--wt-CLI-brightgreen)](#usage)

[中文版 README](README.zh.md)

## What this build does
- Targets macOS and refuses to run elsewhere (macOS-first).
- Works inside any git repo and writes metadata into `.git/agent-wt/config.json` so all worktrees share the same registry.
- Creates a new worktree per agent, wiring it to an agent command (Codex by default; also accepts `claude` and `gemini` labels).
- Runs your chosen agent CLI from inside the worktree so context never collides with other agents/branches.
- Can launch agents in-place or in macOS Terminal/iTerm tabs, keeping sessions separate. Default agent commands can be overridden via env (e.g., `AGENT_WT_CMD_CODEX="codex --profile myprofile"`).
- Includes a minimal GUI (Tkinter) for listing, creating, launching, editing commands/env, and untracking agent worktrees on macOS, showing dirty/ahead/behind status.

## Install
Use the Python CLI directly (requires Python 3.8+). From the repo root:
```bash
./install.sh   # links agent-wt into /usr/local/bin or ~/.local/bin
agent-wt --help
```

## Tests
```bash
pytest
```

## Usage
Common flow:
```bash
# create a new worktree for an agent, auto-start in Terminal
agent-wt create story-mode --agent codex --base main --start --cmd "codex" --launch terminal

# later, jump back in
agent-wt run story-mode --cmd "codex" --launch terminal

# list tracked sandboxes
agent-wt list

# remove tracking (non-destructive by default)
agent-wt remove story-mode
```

Default commands per agent label (overridable via env):
```
codex   -> codex        (env: AGENT_WT_CMD_CODEX)
claude  -> claude       (env: AGENT_WT_CMD_CLAUDE)
gemini  -> gemini       (env: AGENT_WT_CMD_GEMINI)
```

### Example: two existing feature branches in parallel
Assume current branch is `master`, and you already have branches `feat/a` and `feat/b`:
```bash
# attach to existing branches without creating new ones
agent-wt create feat-a --agent codex --branch feat/a --use-existing-branch --launch terminal --cmd "codex"
agent-wt create feat-b --agent claude --branch feat/b --use-existing-branch --launch terminal --cmd "claude"

# work inside each Terminal tab (auto-cd), edit code, then inspect status/diff
agent-wt git feat-a -- status
agent-wt diff feat-a

# commit per worktree
agent-wt commit feat-a -m "feat: implement A" --all
agent-wt commit feat-b -m "feat: implement B" --all

# push using tracked branches (wt/feat-a, wt/feat-b) to origin
agent-wt push feat-a
agent-wt push feat-b
```
Reopen later with `agent-wt run feat-a --launch terminal` (or via GUI buttons).

### Commands
- `agent-wt create <name> [--agent codex|claude|gemini] [--base <ref>] [--branch <branch>] [--path <dir>] [--start] [--cmd "<command>"] [--launch spawn|terminal|iterm]`  
  - Creates a git worktree (branch defaults to `wt/<name>`; path defaults to a sibling folder `<repo>-<name>`).
  - Records the sandbox in `.git/agent-wt/config.json`.
  - `--start` immediately launches the agent command inside the new worktree using the selected launcher (`spawn`, `terminal`, or `iterm`). Use `--allow-dirty` to bypass the dirty guard.
- `agent-wt run <name> [--cmd "<command>"] [--agent <agent>] [--launch spawn|terminal|iterm] [--allow-dirty]`  
  - Starts the configured agent CLI in the tracked worktree (cwd is set to the worktree).
  - If no `--cmd` is given, uses the command remembered from creation or the default for the agent (`codex`, `claude`, `gemini`).
- `agent-wt list [--json]`  
  - Shows tracked worktrees, path presence, dirty state, and ahead/behind if an upstream is set.
- `agent-wt info <name> [--json]`  
  - Prints a single entry with its config.
- `agent-wt set <name> [--agent <agent>] [--cmd "<command>"] [--path <path>]`  
  - Updates tracked metadata, e.g., change the agent label or command.
- `agent-wt set-env <name> KEY=VAL ... [--unset KEY ...]`  
  - Adds/updates/removes per-worktree environment variables (merged when launching).
- `agent-wt remove <name> [--delete-path] [--delete-branch] [--prune]`  
  - Untracks the worktree. Optional flags remove the worktree path (`git worktree remove --force`), delete the branch, or both (`--prune`).
- `agent-wt prune [--delete-branch] [--orphaned-branch] [--json] [--dry-run]`  
  - Cleans the registry by removing entries whose paths are missing (and optionally those whose branches are gone). Can delete orphaned branches too; use `--dry-run` to preview.
- `agent-wt git <name> -- <git args>`  
  - Run git commands inside the worktree (e.g., `agent-wt git story -- status`).
- `agent-wt diff <name> [-- <git diff args>]`  
  - Show git diff for that worktree.
- `agent-wt commit <name> -m "msg" [-a|--all]`  
  - Add (default `.`; or `-a` for `-A`) and commit.
- `agent-wt push <name> [--remote origin] [--branch <branch>]`  
  - Push using the tracked branch by default.
- `agent-wt open <name> [--launch terminal|iterm]`  
  - Open a shell in Terminal/iTerm at the worktree path.
- `agent-wt gui`  
  - Opens a simple macOS Tkinter GUI to list worktrees, run selected ones, or create new ones.
- `agent-wt help` / `agent-wt version`

### Defaults and paths
- Worktree path default: `<repo-parent>/<repo-name>-<worktree-name>`.
- Config lives in the git common dir: `.git/agent-wt/config.json` (shared by all worktrees).
- Default agent command per label: `codex`, `claude`, `gemini`. Override with `--cmd`.

## GUI notes
- Requires Tkinter (bundled with most macOS Python installs).
- GUI uses the same registry; actions mirror CLI behavior. You can choose launch mode (spawn/Terminal/iTerm), opt into `Allow dirty`, edit commands, untrack entries, open Terminal/iTerm, and run Git status/diff/commit/push. Dirty/ahead/behind are displayed when available.

## Roadmap to next step
- Expand provider adapters so `--agent claude` / `--agent gemini` map to real CLIs and options.
- Add a small GUI frontend that reads the same config and launches agents from a menu.
- Enrich status (git status, branch ahead/behind) and safety checks (dirty tree guard rails, branch reuse).
