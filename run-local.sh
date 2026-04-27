#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM="${HERMES_AGENT_SOURCE:-$HOME/.hermes/hermes-agent}"
RUNTIME="$ROOT/.runtime/hermes-agent"
WEB="$ROOT/web"
PORT="${PORT:-9119}"
WEB_DEV_PORT="${WEB_DEV_PORT:-3019}"
PYTHON="$UPSTREAM/venv/bin/python"
WATCH=0
DEV=0
WATCH_INTERVAL="${WATCH_INTERVAL:-1}"
HERMES_SESSION_TOKEN_OVERRIDE="${HERMES_DEV_SESSION_TOKEN:-}"
WEB_DEV_PID=""
OPEN_BROWSER="${OPEN_BROWSER:-1}"
PORT_STOP_TIMEOUT="${PORT_STOP_TIMEOUT:-5}"
DASHBOARD_STARTED=0
WEB_DEV_STARTED=0

usage() {
  cat <<EOF
Usage: ./run-local.sh [--watch|--dev]

Options:
  --watch    Restart the Hermes dashboard when watched Python files change.
  --dev      Run Hermes backend with Python autorestart and Nuxt dev server with HMR.

Environment:
  HERMES_AGENT_SOURCE     Path to the upstream Hermes checkout.
  HERMES_DEV_SESSION_TOKEN Optional fixed dev auth token for --dev.
  PORT                    Dashboard port. Default: 9119.
  WEB_DEV_PORT            Nuxt dev server port for --dev. Default: 3019.
  WATCH_INTERVAL          Poll interval in seconds in watch mode. Default: 1.
  PORT_STOP_TIMEOUT       Seconds to wait before force-stopping stale listeners. Default: 5.
  OPEN_BROWSER            Open the UI once on initial startup. Default: 1. Set 0 to disable.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --watch)
      WATCH=1
      ;;
    --dev)
      DEV=1
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

if [[ "$WATCH" == "1" && "$DEV" == "1" ]]; then
  echo "Use either --watch or --dev, not both." >&2
  usage >&2
  exit 1
fi

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
    --exclude '.venv' \
    --exclude 'venv' \
    --exclude 'hermes_cli/web_chat_modules' \
    "$UPSTREAM/" "$RUNTIME/"

  cp "$ROOT/backend/hermes_cli/web_chat.py" "$RUNTIME/hermes_cli/web_chat.py"
  mkdir -p "$RUNTIME/hermes_cli/web_chat_modules"
  rsync -a --delete \
    --exclude '__pycache__' \
    "$ROOT/backend/hermes_cli/web_chat_modules/" "$RUNTIME/hermes_cli/web_chat_modules/"
  mkdir -p "$RUNTIME/tests/hermes_cli"
  cp "$ROOT/backend/tests/hermes_cli/test_web_chat.py" "$RUNTIME/tests/hermes_cli/test_web_chat.py"

  RUNTIME_WEB_SERVER="$RUNTIME/hermes_cli/web_server.py" RUNTIME_HERMES_STATE="$RUNTIME/hermes_state.py" "$PYTHON" - <<'PY'
from pathlib import Path
import os
import re

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

if "HERMES_DEV_WEB_ORIGIN" not in text:
    needle = 'app = FastAPI(title="Hermes Agent", version=__version__)'
    redirect_code = """

@app.middleware("http")
async def _redirect_static_requests_to_dev_server(request, call_next):
    dev_web_origin = os.environ.get("HERMES_DEV_WEB_ORIGIN")
    if dev_web_origin and not request.url.path.startswith(("/api", "/ws")):
        from fastapi.responses import RedirectResponse
        target = f"{dev_web_origin.rstrip('/')}{request.url.path}"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(target, status_code=307)
    return await call_next(request)
"""
    text = text.replace(needle, needle + redirect_code, 1)

if 'request.query_params.get("session_token", "")' not in text:
    needle = """    if session_header and hmac.compare_digest(\n        session_header.encode(),\n        _SESSION_TOKEN.encode(),\n    ):\n        return True\n\n"""
    replacement = needle + """    if request.url.path.startswith("/api/web-chat/runs/") and request.url.path.endswith("/events"):\n        session_token = request.query_params.get("session_token", "")\n        if session_token and hmac.compare_digest(session_token.encode(), _SESSION_TOKEN.encode()):\n            return True\n\n"""
    text = text.replace(needle, replacement, 1)

static_assets_mount = '    application.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")'
if static_assets_mount in text:
    text = text.replace(
        static_assets_mount,
        '''    assets_dir = WEB_DIST / "assets"
    if assets_dir.exists():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")''',
        1,
    )

env_name = "HERMES_" + "SESSION_" + "TOKEN"
if f'os.environ.get("{env_name}")' not in text:
    text, count = re.subn(
        r"_SESSION_TOKEN\s*=\s*secrets\.token_urlsafe\(\d+\)",
        f'_SESSION_TOKEN = os.environ.get("{env_name}") or secrets.token_urlsafe(32)',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not patch Hermes web session token override")

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

ensure_web_deps() {
  if [[ ! -d "$WEB/node_modules" ]]; then
    echo "Installing Nuxt dependencies..."
    (cd "$WEB" && pnpm install --frozen-lockfile)
  fi

  # The Hermes backend still receives HERMES_WEB_DIST in --dev, but the browser
  # is served by Nuxt. Keep the mount directory present without running a build.
  mkdir -p "$WEB/.output/public/assets"
}

generate_session_token() {
  "$PYTHON" - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
}

watch_signature() {
  ROOT="$ROOT" UPSTREAM="$UPSTREAM" "$PYTHON" - <<'PY'
from __future__ import annotations

import hashlib
import os
from pathlib import Path

root = Path(os.environ["ROOT"])
upstream = Path(os.environ["UPSTREAM"])

# In --dev, restart the backend only for backend runtime source changes.
# Do not watch tests or the whole upstream checkout: editor/test/tooling touches
# there are noisy and can cause the dev server to restart itself repeatedly.
watch_roots = [
    root / "backend" / "hermes_cli",
    upstream / "hermes_cli",
    upstream / "tools",
]
skip_dirs = {".git", ".mypy_cache", ".pytest_cache", "__pycache__", "venv", ".venv", "node_modules", ".runtime", "tests"}
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
  echo "Starting Hermes dashboard backend on http://127.0.0.1:$PORT"
  echo "Runtime copy: $RUNTIME"
  echo "Source checkout is only read/copied, not modified: $UPSTREAM"
  # Hermes' current SPA mount expects this directory even in dev mode, where
  # the browser is served by Nuxt and only API requests hit this backend.
  mkdir -p "$WEB/.output/public/assets"
  (
    cd "$RUNTIME"
    local env_args=("HERMES_WEB_DIST=$WEB/.output/public")
    if [[ "$DEV" == "1" ]]; then
      env_args+=("HERMES_DEV_WEB_ORIGIN=http://127.0.0.1:$WEB_DEV_PORT")
    fi
    if [[ -n "${HERMES_SESSION_TOKEN_OVERRIDE:-}" ]]; then
      env_args+=("HERMES_SESSION_TOKEN=$HERMES_SESSION_TOKEN_OVERRIDE")
    fi
    exec env "${env_args[@]}" "$PYTHON" -m hermes_cli.main dashboard --port "$PORT" --no-open
  ) &
  CHILD_PID=$!
  DASHBOARD_STARTED=1
}

stop_dashboard() {
  local should_cleanup_port="$DASHBOARD_STARTED"
  if [[ -n "${CHILD_PID:-}" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
    kill "$CHILD_PID" 2>/dev/null || true
    wait "$CHILD_PID" 2>/dev/null || true
  fi
  CHILD_PID=""
  DASHBOARD_STARTED=0
  if [[ "$should_cleanup_port" == "1" ]]; then
    kill_existing_port_processes "$PORT"
  fi
}

open_browser_once() {
  local url="$1"

  if [[ "$OPEN_BROWSER" == "0" ]]; then
    return
  fi

  if command -v open >/dev/null 2>&1; then
    echo "Opening $url"
    open "$url" >/dev/null 2>&1 || true
  else
    echo "Open manually: $url"
  fi
}

kill_existing_port_processes() {
  local target_port="${1:-$PORT}"
  if ! command -v lsof >/dev/null 2>&1; then
    echo "Warning: lsof not found; cannot auto-stop existing process on port $target_port" >&2
    return
  fi

  local pids
  pids="$(lsof -tiTCP:"$target_port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return
  fi

  echo "Stopping existing process(es) on port $target_port: $pids"
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
  done <<< "$pids"

  local deadline=$((SECONDS + PORT_STOP_TIMEOUT))
  while [[ "$SECONDS" -lt "$deadline" ]]; do
    pids="$(lsof -tiTCP:"$target_port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -z "$pids" ]]; then
      return
    fi
    sleep 0.2
  done

  pids="$(lsof -tiTCP:"$target_port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return
  fi

  echo "Force-stopping stubborn process(es) on port $target_port: $pids"
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill -KILL "$pid" 2>/dev/null || true
  done <<< "$pids"

  deadline=$((SECONDS + PORT_STOP_TIMEOUT))
  while [[ "$SECONDS" -lt "$deadline" ]]; do
    pids="$(lsof -tiTCP:"$target_port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -z "$pids" ]]; then
      return
    fi
    sleep 0.2
  done

  pids="$(lsof -tiTCP:"$target_port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "Warning: port $target_port is still in use by: $pids" >&2
  fi
}

start_nuxt_dev() {
  echo "Starting Nuxt dev server on http://127.0.0.1:$WEB_DEV_PORT"
  echo "Proxying /api to http://127.0.0.1:$PORT"
  (
    cd "$WEB"
    HERMES_API_ORIGIN="http://127.0.0.1:$PORT" \
      NUXT_PUBLIC_HERMES_SESSION_TOKEN="$HERMES_SESSION_TOKEN_OVERRIDE" \
      exec pnpm dev --host 127.0.0.1 --port "$WEB_DEV_PORT"
  ) &
  WEB_DEV_PID=$!
  WEB_DEV_STARTED=1
}

stop_nuxt_dev() {
  local should_cleanup_port="$WEB_DEV_STARTED"
  if [[ -n "${WEB_DEV_PID:-}" ]] && kill -0 "$WEB_DEV_PID" 2>/dev/null; then
    kill "$WEB_DEV_PID" 2>/dev/null || true
    wait "$WEB_DEV_PID" 2>/dev/null || true
  fi
  WEB_DEV_PID=""
  WEB_DEV_STARTED=0
  if [[ "$should_cleanup_port" == "1" ]]; then
    kill_existing_port_processes "$WEB_DEV_PORT"
  fi
}

cleanup() {
  stop_nuxt_dev
  stop_dashboard
}

cleanup_and_exit() {
  cleanup
  exit 130
}

run_once() {
  prepare_runtime
  ensure_web_build
  kill_existing_port_processes "$PORT"
  echo "Starting Hermes dashboard with Nuxt prototype on http://127.0.0.1:$PORT"
  echo "Runtime copy: $RUNTIME"
  echo "Source checkout is only read/copied, not modified: $UPSTREAM"
  cd "$RUNTIME"
  local dashboard_args=(dashboard --port "$PORT")
  if [[ "$OPEN_BROWSER" == "0" ]]; then
    dashboard_args+=(--no-open)
  fi
  HERMES_WEB_DIST="$WEB/.output/public" "$PYTHON" -m hermes_cli.main "${dashboard_args[@]}"
}

run_watch() {
  trap cleanup EXIT
  trap cleanup_and_exit INT TERM TSTP

  prepare_runtime
  ensure_web_build
  kill_existing_port_processes "$PORT"
  local current_sig
  current_sig="$(watch_signature)"
  start_dashboard
  open_browser_once "http://127.0.0.1:$PORT"

  while true; do
    sleep "$WATCH_INTERVAL"

    if [[ -n "${CHILD_PID:-}" ]] && ! kill -0 "$CHILD_PID" 2>/dev/null; then
      echo "Dashboard process exited; restarting..."
      kill_existing_port_processes "$PORT"
      prepare_runtime
      ensure_web_build
      start_dashboard
      current_sig="$(watch_signature)"
      continue
    fi

    local next_sig
    next_sig="$(watch_signature)"
    if [[ "$next_sig" != "$current_sig" ]]; then
      echo "Detected Python change, restarting Hermes dashboard..."
      stop_dashboard
      kill_existing_port_processes "$PORT"
      prepare_runtime
      ensure_web_build
      start_dashboard
      current_sig="$next_sig"
    fi
  done
}

run_dev() {
  trap cleanup EXIT
  trap cleanup_and_exit INT TERM TSTP

  HERMES_SESSION_TOKEN_OVERRIDE="${HERMES_DEV_SESSION_TOKEN:-$(generate_session_token)}"

  prepare_runtime
  ensure_web_deps
  kill_existing_port_processes "$PORT"
  kill_existing_port_processes "$WEB_DEV_PORT"

  local current_sig
  current_sig="$(watch_signature)"
  start_dashboard
  start_nuxt_dev
  open_browser_once "http://127.0.0.1:$WEB_DEV_PORT"

  echo ""
  echo "Fast dev mode ready: http://127.0.0.1:$WEB_DEV_PORT"
  echo "Frontend changes use Nuxt HMR; Python changes restart only the Hermes backend."
  echo ""

  while true; do
    sleep "$WATCH_INTERVAL"

    if [[ -n "${WEB_DEV_PID:-}" ]] && ! kill -0 "$WEB_DEV_PID" 2>/dev/null; then
      echo "Nuxt dev server exited; stopping dev mode."
      exit 1
    fi

    if [[ -n "${CHILD_PID:-}" ]] && ! kill -0 "$CHILD_PID" 2>/dev/null; then
      echo "Dashboard backend process exited; restarting..."
      kill_existing_port_processes "$PORT"
      prepare_runtime
      start_dashboard
      current_sig="$(watch_signature)"
      continue
    fi

    local next_sig
    next_sig="$(watch_signature)"
    if [[ "$next_sig" != "$current_sig" ]]; then
      echo "Detected Python change, restarting Hermes dashboard backend..."
      stop_dashboard
      kill_existing_port_processes "$PORT"
      prepare_runtime
      start_dashboard
      current_sig="$next_sig"
    fi
  done
}

if [[ "$DEV" == "1" ]]; then
  run_dev
elif [[ "$WATCH" == "1" ]]; then
  run_watch
else
  run_once
fi
