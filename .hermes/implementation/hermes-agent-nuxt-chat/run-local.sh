#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM="${HERMES_AGENT_SOURCE:-/Users/pavolbiely/.hermes/hermes-agent}"
RUNTIME="$ROOT/.runtime/hermes-agent"
WEB="$ROOT/web-nuxt"
PORT="${PORT:-9119}"
PYTHON="$UPSTREAM/venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing Hermes venv python: $PYTHON" >&2
  exit 1
fi

if [[ ! -f "$UPSTREAM/hermes_cli/web_server.py" ]]; then
  echo "Missing Hermes source checkout: $UPSTREAM" >&2
  exit 1
fi

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

RUNTIME_WEB_SERVER="$RUNTIME/hermes_cli/web_server.py" "$PYTHON" - <<'PY'
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
PY

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

echo "Starting Hermes dashboard with Nuxt prototype on http://127.0.0.1:$PORT"
echo "Runtime copy: $RUNTIME"
echo "Source checkout is only read/copied, not modified: $UPSTREAM"
cd "$RUNTIME"
HERMES_WEB_DIST="$WEB/.output/public" "$PYTHON" -m hermes_cli.main dashboard --port "$PORT"
