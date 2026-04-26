#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM="${HERMES_AGENT_SOURCE:-$HOME/.hermes/hermes-agent}"
RUNTIME="$ROOT/.runtime/hermes-agent"
WEB="$ROOT/web"
PORT="${PORT:-9119}"
PYTHON="$UPSTREAM/venv/bin/python"
WATCH=0
WATCH_INTERVAL="${WATCH_INTERVAL:-1}"

usage() {
  cat <<EOF
Usage: ./run-local.sh [--watch]

Options:
  --watch    Restart the Hermes dashboard when watched Python files change.

Environment:
  HERMES_AGENT_SOURCE  Path to the upstream Hermes checkout.
  PORT                 Dashboard port. Default: 9119.
  WATCH_INTERVAL       Poll interval in seconds in watch mode. Default: 1.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --watch)
      WATCH=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing Hermes venv python: $PYTHON" >&2
  exit 1
fi

if [[ ! -f "$UPSTREAM/hermes_cli/web_server.py" ]]; then
  echo "Missing Hermes source checkout: $UPSTREAM" >&2
  exit 1
fi

prepare_runtime() {
  echo "Preparing disposable Hermes runtime copy under: $RUNTIME"
  mkdir -p "$ROOT/.runtime"
  rsync -a --delete \
    --exclude '.git' \
    --exclude '.mypy_cache' \
    --exclude '.pytest_cache' \
    --exclude '__pycache__' \
    "$UPSTREAM/" "$RUNTIME/"

  cp "$ROOT/backend/hermes_cli/web_chat.py" "$RUNTIME/hermes_cli/web_chat.py"
  mkdir -p "$RUNTIME/tests/hermes_cli"
  cp "$ROOT/backend/tests/hermes_cli/test_web_chat.py" "$RUNTIME/tests/hermes_cli/test_web_chat.py"

  RUNTIME_WEB_SERVER="$RUNTIME/hermes_cli/web_server.py" RUNTIME_HERMES_STATE="$RUNTIME/hermes_state.py" "$PYTHON" - <<'PY'
from pathlib import Path
import os

path = Path(os.environ["RUNTIME_WEB_SERVER"])
text = path.read_text()

if "from hermes_cli.web_chat import router as web_chat_router" not in text:
    needle = 'WEB_DIST = Path(os.environ["HERMES_WEB_DIST"]) if "HERMES_WEB_DIST" in os.environ else Path(__file__).parent / "web_dist"'
    text = text.replace(needle, 'from hermes_cli.web_chat import router as web_chat_router\n\n' + needle, 1)

if "app.include_router(web_chat_router)" not in text:
    text = text.replace(
        "# Mount plugin API routes before the SPA catch-all.\n_mount_plugin_api_routes()",
        "# Mount built-in and plugin API routes before the SPA catch-all.\napp.include_router(web_chat_router)\n_mount_plugin_api_routes()",
        1,
    )

if 'request.query_params.get("session_token", "")' not in text:
    needle = """    if session_header and hmac.compare_digest(\n        session_header.encode(),\n        _SESSION_TOKEN.encode(),\n    ):\n        return True\n\n"""
    replacement = needle + """    if request.url.path.startswith("/api/web-chat/runs/") and request.url.path.endswith("/events"):\n        session_token = request.query_params.get("session_token", "")\n        if session_token and hmac.compare_digest(session_token.encode(), _SESSION_TOKEN.encode()):\n            return True\n\n"""
    text = text.replace(needle, replacement, 1)

path.write_text(text)

state_path = Path(os.environ["RUNTIME_HERMES_STATE"])
state_text = state_path.read_text()

if "def update_session_model_settings(" not in state_text:
    needle = """    def update_system_prompt(self, session_id: str, system_prompt: str) -> None:\n        \"\"\"Store the full assembled system prompt snapshot.\"\"\"\n        def _do(conn):\n            conn.execute(\n                \"UPDATE sessions SET system_prompt = ? WHERE id = ?\",\n                (system_prompt, session_id),\n            )\n        self._execute_write(_do)\n"""
    replacement = needle + '''

    def update_session_model_settings(
        self,
        session_id: str,
        *,
        model: Optional[str] = None,
        model_config_updates: Optional[Dict[str, Any]] = None,
    ) -> None:
        \"\"\"Update session-level model settings while preserving other config.\"\"\"

        def _do(conn):
            cursor = conn.execute(
                \"SELECT model_config FROM sessions WHERE id = ?\",
                (session_id,),
            )
            row = cursor.fetchone()
            model_config: Dict[str, Any] = {}
            if row and row[\"model_config\"]:
                try:
                    parsed = json.loads(row[\"model_config\"])
                except Exception:
                    parsed = None
                if isinstance(parsed, dict):
                    model_config = parsed

            if model_config_updates:
                for key, value in model_config_updates.items():
                    if value is None:
                        model_config.pop(key, None)
                    else:
                        model_config[key] = value

            conn.execute(
                \"\"\"UPDATE sessions
                   SET model = COALESCE(?, model),
                       model_config = ?
                   WHERE id = ?\"\"\",
                (
                    model,
                    json.dumps(model_config) if model_config else None,
                    session_id,
                ),
            )

        self._execute_write(_do)
'''
    state_text = state_text.replace(needle, replacement, 1)

state_path.write_text(state_text)
PY
}

ensure_web_build() {
  if [[ ! -d "$WEB/node_modules" ]]; then
    echo "Installing Nuxt dependencies..."
    (cd "$WEB" && pnpm install --frozen-lockfile)
  fi

  if [[ ! -d "$WEB/.output/public" ]]; then
    echo "Building Nuxt static app..."
    (cd "$WEB" && pnpm build)
  fi

  # Hermes' current SPA mount expects /assets to exist. Nuxt static output mainly uses /_nuxt.
  mkdir -p "$WEB/.output/public/assets"
}

watch_signature() {
  ROOT="$ROOT" UPSTREAM="$UPSTREAM" "$PYTHON" - <<'PY'
from __future__ import annotations

import hashlib
import os
from pathlib import Path

root = Path(os.environ["ROOT"])
upstream = Path(os.environ["UPSTREAM"])

watch_roots = [
    root / "backend",
    upstream,
]
skip_dirs = {".git", ".mypy_cache", ".pytest_cache", "__pycache__", "venv", "node_modules"}
items: list[str] = []

for base in watch_roots:
    if not base.exists():
        continue
    for path in sorted(base.rglob("*.py")):
        if any(part in skip_dirs for part in path.parts):
            continue
        stat = path.stat()
        items.append(f"{path}:{stat.st_mtime_ns}:{stat.st_size}")

print(hashlib.sha256("\n".join(items).encode()).hexdigest())
PY
}

CHILD_PID=""

start_dashboard() {
  echo "Starting Hermes dashboard with Nuxt prototype on http://127.0.0.1:$PORT"
  echo "Runtime copy: $RUNTIME"
  echo "Source checkout is only read/copied, not modified: $UPSTREAM"
  (
    cd "$RUNTIME"
    HERMES_WEB_DIST="$WEB/.output/public" "$PYTHON" -m hermes_cli.main dashboard --port "$PORT"
  ) &
  CHILD_PID=$!
}

stop_dashboard() {
  if [[ -n "${CHILD_PID:-}" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
    kill "$CHILD_PID" 2>/dev/null || true
    wait "$CHILD_PID" 2>/dev/null || true
  fi
  CHILD_PID=""
}

kill_existing_port_processes() {
  if ! command -v lsof >/dev/null 2>&1; then
    echo "Warning: lsof not found; cannot auto-stop existing process on port $PORT" >&2
    return
  fi

  local pids
  pids="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return
  fi

  echo "Stopping existing process(es) on port $PORT: $pids"
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
  done <<< "$pids"
}

cleanup() {
  stop_dashboard
}

run_once() {
  prepare_runtime
  ensure_web_build
  kill_existing_port_processes
  echo "Starting Hermes dashboard with Nuxt prototype on http://127.0.0.1:$PORT"
  echo "Runtime copy: $RUNTIME"
  echo "Source checkout is only read/copied, not modified: $UPSTREAM"
  cd "$RUNTIME"
  HERMES_WEB_DIST="$WEB/.output/public" "$PYTHON" -m hermes_cli.main dashboard --port "$PORT"
}

run_watch() {
  trap cleanup EXIT INT TERM

  prepare_runtime
  ensure_web_build
  kill_existing_port_processes
  local current_sig
  current_sig="$(watch_signature)"
  start_dashboard

  while true; do
    sleep "$WATCH_INTERVAL"

    if [[ -n "${CHILD_PID:-}" ]] && ! kill -0 "$CHILD_PID" 2>/dev/null; then
      echo "Dashboard process exited; restarting..."
      prepare_runtime
      start_dashboard
      current_sig="$(watch_signature)"
      continue
    fi

    local next_sig
    next_sig="$(watch_signature)"
    if [[ "$next_sig" != "$current_sig" ]]; then
      echo "Detected Python change, restarting Hermes dashboard..."
      stop_dashboard
      prepare_runtime
      start_dashboard
      current_sig="$next_sig"
    fi
  done
}

if [[ "$WATCH" == "1" ]]; then
  run_watch
else
  run_once
fi
