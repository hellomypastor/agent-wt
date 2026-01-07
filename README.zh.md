# agent-wt

agent-wt 是一个 macOS 优先的 CLI，将每个 Git worktree 映射为一个独立的 AI 代理工作区。这样做可以让多个代理并行运行，避免上下文冲突、文件覆盖和分支干扰。

## 当前功能
- 仅在 macOS 运行；确保在 Git 仓库中执行，并将注册信息写入 `.git/agent-wt/config.json`，所有 worktree 共享同一份注册表。
- 为每个代理创建独立 worktree，并绑定启动命令（默认支持 `codex`、`claude`、`gemini`，可用环境变量覆盖默认命令，例如 `AGENT_WT_CMD_CODEX="codex --profile myprofile"`）。
- 可以在当前进程、macOS Terminal 或 iTerm 中启动代理，会自动切换到对应 worktree 目录。
- GUI（Tkinter）可列出、创建、启动、修改命令/环境并取消跟踪 worktree，并显示脏状态/领先/落后信息，还能一键打开 Terminal/iTerm、执行 git status/diff/commit/push。

## 安装
需要 Python 3.8+。在仓库根目录执行：
```bash
./install.sh   # 将 agent-wt 链接到 /usr/local/bin 或 ~/.local/bin
agent-wt --help
```

## 测试
```bash
pytest
```

## 常用示例
```bash
# 创建并自动在 Terminal 中启动
agent-wt create story-mode --agent codex --base main --start --cmd "codex" --launch terminal

# 重新进入同一工作区
agent-wt run story-mode --cmd "codex" --launch terminal

# 查看
agent-wt list

# 仅取消跟踪（默认不删除路径/分支）
agent-wt remove story-mode
```

默认命令（可用环境变量覆盖）：
```
codex   -> codex        (env: AGENT_WT_CMD_CODEX)
claude  -> claude       (env: AGENT_WT_CMD_CLAUDE)
gemini  -> gemini       (env: AGENT_WT_CMD_GEMINI)
```

### 示例：并行开发两个已存在的特性分支
假设当前主分支是 `master`，且 `feat/a`、`feat/b` 已存在：
```bash
# 附加到已有分支（不新建分支）
agent-wt create feat-a --agent codex --branch feat/a --use-existing-branch --launch terminal --cmd "codex"
agent-wt create feat-b --agent claude --branch feat/b --use-existing-branch --launch terminal --cmd "claude"

# 在各自 Terminal 标签页中工作（自动 cd），然后查看状态/差异
agent-wt git feat-a -- status
agent-wt diff feat-a

# 分别提交
agent-wt commit feat-a -m "feat: implement A" --all
agent-wt commit feat-b -m "feat: implement B" --all

# 推送到 origin（使用默认跟踪分支 wt/feat-a、wt/feat-b）
agent-wt push feat-a
agent-wt push feat-b
```
之后可通过 `agent-wt run feat-a --launch terminal`（或 GUI 按钮）重新进入。

## 命令
- `agent-wt create <name> [--agent codex|claude|gemini] [--base <ref>] [--branch <branch>] [--path <dir>] [--start] [--cmd "<command>"] [--launch spawn|terminal|iterm] [--allow-dirty]`  
  - 创建 worktree（默认分支 `wt/<name>`，默认路径为 `<repo>-<name>` 的同级目录）。
  - 将配置写入 `.git/agent-wt/config.json`。
  - `--start` 会立即用指定启动方式运行；默认有脏树保护，使用 `--allow-dirty` 可跳过。
- `agent-wt run <name> [--cmd "<command>"] [--agent <agent>] [--launch spawn|terminal|iterm] [--allow-dirty]`  
  - 在对应 worktree 中启动代理命令。
- `agent-wt list [--json]`  
  - 展示所有条目、路径存在性、脏状态、领先/落后信息。
- `agent-wt info <name> [--json]`  
  - 查看单个条目的详细信息。
- `agent-wt set <name> [--agent <agent>] [--cmd "<command>"] [--path <path>]`  
  - 更新已跟踪条目的代理、命令或路径。
- `agent-wt set-env <name> KEY=VAL ... [--unset KEY ...]`  
  - 增删改工作区的环境变量（启动时合并）。
- `agent-wt remove <name> [--delete-path] [--delete-branch] [--prune] [--force]`  
  - 取消跟踪，可选删除 worktree 路径（`git worktree remove --force`）、删除分支或同时删除。
- `agent-wt prune [--delete-branch] [--orphaned-branch] [--json] [--dry-run]`  
  - 清理缺失路径的条目（可选清理缺失分支并删除孤立分支）。
- `agent-wt git <name> -- <git args>`  
  - 在对应 worktree 内执行 git。
- `agent-wt diff <name> [-- <git diff args>]`  
  - 查看 diff。
- `agent-wt commit <name> -m "msg" [-a|--all]`  
  - add 后提交。
- `agent-wt push <name> [--remote origin] [--branch <branch>]`  
  - 推送（默认使用记录的分支和 origin）。
- `agent-wt open <name> [--launch terminal|iterm]`  
  - 在 Terminal/iTerm 打开 shell 并切到该路径。
- `agent-wt gui`  
  - 启动 macOS Tkinter GUI，支持选择启动方式、允许脏树、编辑命令/环境、取消跟踪、打开终端、执行 git status/diff/commit/push。
- `agent-wt help` / `agent-wt version`

### 路径与配置
- 默认路径：`<repo-parent>/<repo-name>-<worktree-name>`。
- 配置位置：`.git/agent-wt/config.json`（所有 worktree 共享）。
- 默认命令可通过环境变量覆盖：`AGENT_WT_CMD_CODEX`、`AGENT_WT_CMD_CLAUDE`、`AGENT_WT_CMD_GEMINI`。

## GUI 说明
- 依赖 Tkinter（macOS Python 通常已自带）。
- 使用同一配置注册表，可选启动方式（spawn/Terminal/iTerm）、允许脏树、编辑命令/环境、取消跟踪、打开终端、执行 git status/diff/commit/push；显示脏状态与领先/落后信息。
