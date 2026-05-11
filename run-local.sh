#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB="$ROOT/web"
PORT="${PORT:-9119}"
WEB_DEV_HOST="${WEB_DEV_HOST:-127.0.0.1}"
WEB_DEV_PORT="${WEB_DEV_PORT:-3019}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"
PORT_STOP_TIMEOUT="${PORT_STOP_TIMEOUT:-5}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-30}"
DEV=0
PREVIEW_PID=""
DEV_PID=""
STARTED_PORT=""

usage() {
  cat <<EOF
Usage: ./run-local.sh [--dev]

Options:
  --dev      Run the Nuxt dev server with HMR.

Environment:
  PORT             Production preview port. Default: 9119.
  WEB_DEV_HOST     Nuxt dev host for --dev. Default: 127.0.0.1.
  WEB_DEV_PORT     Nuxt dev port for --dev. Default: 3019.
  OPEN_BROWSER     Open the UI on startup. Default: 1. Set 0 to disable.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dev|--watch)
      DEV=1
      ;;
    --sync-runtime)
      echo "--sync-runtime was removed with the legacy Python web-chat runtime." >&2
      exit 1
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

ensure_web_deps() {
  if [[ ! -d "$WEB/node_modules" ]]; then
    echo "Installing Nuxt dependencies..."
    (cd "$WEB" && pnpm install --frozen-lockfile)
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

port_open() {
  node -e "const net=require('node:net'); const s=net.createConnection({host:'127.0.0.1',port:Number(process.argv[1])}); s.on('connect',()=>{s.destroy(); process.exit(0)}); s.on('error',()=>process.exit(1)); s.setTimeout(200,()=>{s.destroy(); process.exit(1)});" "$1" >/dev/null 2>&1
}

wait_for_port() {
  local target_port="$1"
  local service_name="$2"
  local deadline=$((SECONDS + STARTUP_TIMEOUT))

  echo "Waiting for $service_name on port $target_port..."
  while [[ "$SECONDS" -lt "$deadline" ]]; do
    if port_open "$target_port"; then
      echo "$service_name is ready on http://127.0.0.1:$target_port"
      return 0
    fi
    sleep 0.2
  done

  echo "Warning: timed out waiting for $service_name on port $target_port" >&2
  return 1
}

kill_existing_port_processes() {
  local target_port="$1"
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
    [[ -z "$pids" ]] && return
    sleep 0.2
  done

  pids="$(lsof -tiTCP:"$target_port" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -z "$pids" ]] && return

  echo "Force-stopping stubborn process(es) on port $target_port: $pids"
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill -KILL "$pid" 2>/dev/null || true
  done <<< "$pids"
}

cleanup() {
  if [[ -n "${DEV_PID:-}" ]] && kill -0 "$DEV_PID" 2>/dev/null; then
    kill "$DEV_PID" 2>/dev/null || true
    wait "$DEV_PID" 2>/dev/null || true
  fi
  if [[ -n "${PREVIEW_PID:-}" ]] && kill -0 "$PREVIEW_PID" 2>/dev/null; then
    kill "$PREVIEW_PID" 2>/dev/null || true
    wait "$PREVIEW_PID" 2>/dev/null || true
  fi
  if [[ -n "$STARTED_PORT" ]]; then
    kill_existing_port_processes "$STARTED_PORT"
  fi
}

cleanup_and_exit() {
  cleanup
  exit 130
}

run_dev() {
  trap cleanup EXIT
  trap cleanup_and_exit INT TERM TSTP

  ensure_web_deps
  kill_existing_port_processes "$WEB_DEV_PORT"
  STARTED_PORT="$WEB_DEV_PORT"

  echo "Starting Nuxt dev server on http://$WEB_DEV_HOST:$WEB_DEV_PORT"
  (cd "$WEB" && exec pnpm dev --host "$WEB_DEV_HOST" --port "$WEB_DEV_PORT") &
  DEV_PID=$!

  if wait_for_port "$WEB_DEV_PORT" "Nuxt dev server"; then
    open_browser_once "http://$WEB_DEV_HOST:$WEB_DEV_PORT"
  fi

  wait "$DEV_PID"
}

run_preview() {
  trap cleanup EXIT
  trap cleanup_and_exit INT TERM TSTP

  ensure_web_deps
  (cd "$WEB" && pnpm build)
  kill_existing_port_processes "$PORT"
  STARTED_PORT="$PORT"

  echo "Starting Nuxt/Nitro preview on http://127.0.0.1:$PORT"
  (cd "$WEB" && HOST=127.0.0.1 PORT="$PORT" exec node .output/server/index.mjs) &
  PREVIEW_PID=$!

  if wait_for_port "$PORT" "Nuxt/Nitro preview"; then
    open_browser_once "http://127.0.0.1:$PORT"
  fi

  wait "$PREVIEW_PID"
}

if [[ "$DEV" == "1" ]]; then
  run_dev
else
  run_preview
fi
