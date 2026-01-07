#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_SOURCE="$SCRIPT_DIR/bin/agent-wt"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[agent-wt] This installer is macOS-first; aborting." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[agent-wt] python3 is required." >&2
  exit 1
fi

PYV=$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
if [[ "${PYV%%.*}" -lt 3 || "${PYV#*.}" -lt 8 ]]; then
  echo "[agent-wt] Python >=3.8 required, found $PYV" >&2
  exit 1
fi

if [[ ! -x "$BIN_SOURCE" ]]; then
  chmod +x "$BIN_SOURCE"
fi

# Prefer /usr/local/bin if writable, else ~/.local/bin
TARGET_DIR="/usr/local/bin"
if [[ ! -w "$TARGET_DIR" ]]; then
  TARGET_DIR="$HOME/.local/bin"
  mkdir -p "$TARGET_DIR"
fi

TARGET="$TARGET_DIR/agent-wt"
ln -sf "$BIN_SOURCE" "$TARGET"
echo "[agent-wt] Linked to $TARGET"

echo "[agent-wt] Verifying..."
"$TARGET" --help >/dev/null
echo "[agent-wt] Install complete. Ensure $TARGET_DIR is on your PATH."
