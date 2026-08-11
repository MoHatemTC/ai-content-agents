#!/usr/bin/env bash
# start-dev.sh — run the Sensei backend (FastAPI :8000) and frontend (Vite :8080) together.
#
#   ./start-dev.sh           start (or reuse) both servers
#   ./start-dev.sh status    show what is running
#   ./start-dev.sh stop      stop both servers
#
# After a laptop restart, run `./start-dev.sh` once — the backend does NOT
# auto-start, so without it the app shows "Unable to load your workspaces".
set -uo pipefail

BACKEND_DIR="${BACKEND_DIR:-$HOME/Desktop/ai-content-agents}"
FRONTEND_DIR="${FRONTEND_DIR:-$HOME/Desktop/Sensei-AI}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
LAUNCHER="$FRONTEND_DIR/scripts/launch-detached.py"

log()  { printf '\033[1;36m[sensei]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[sensei]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[sensei]\033[0m %s\n' "$*" >&2; }

# Only sockets in LISTEN state count as "running" — matches the server, not
# stray outbound connections from editors/browsers.
port_pids() { lsof -nP -i "tcp:${1}" -sTCP:LISTEN -t 2>/dev/null || true; }

stop_all() {
  log "Stopping Sensei dev servers…"
  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    for pid in $(port_pids "$port"); do
      kill "$pid" 2>/dev/null || true
    done
  done
  sleep 1
  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    for pid in $(port_pids "$port"); do
      kill -9 "$pid" 2>/dev/null || true
    done
  done
  log "Stopped (ports ${BACKEND_PORT} and ${FRONTEND_PORT} clear)."
}

status() {
  local b f
  b="$(port_pids "$BACKEND_PORT")"
  f="$(port_pids "$FRONTEND_PORT")"
  [[ -n "$b" ]] && log "Backend  running  http://127.0.0.1:${BACKEND_PORT}  (pid ${b//$'\n'/ })" \
                 || warn "Backend  DOWN      http://127.0.0.1:${BACKEND_PORT}"
  [[ -n "$f" ]] && log "Frontend running  http://localhost:${FRONTEND_PORT}  (pid ${f//$'\n'/ })" \
                 || warn "Frontend DOWN      http://localhost:${FRONTEND_PORT}"
}

case "${1:-}" in
  stop)   stop_all; exit 0 ;;
  status) status;   exit 0 ;;
esac

# --- sanity checks ---------------------------------------------------------
[[ -d "$BACKEND_DIR" ]] || { err "Backend dir not found: $BACKEND_DIR (set BACKEND_DIR)"; exit 1; }
[[ -d "$FRONTEND_DIR" ]] || { err "Frontend dir not found: $FRONTEND_DIR (set FRONTEND_DIR)"; exit 1; }
[[ -x "$LAUNCHER" ]] || { err "Missing $LAUNCHER — re-clone the repo or restore scripts/."; exit 1; }
VENV_PY="$BACKEND_DIR/.venv/bin/python"
[[ -x "$VENV_PY" ]] || { err "Missing backend venv at $VENV_PY — run: cd $BACKEND_DIR && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
[[ -f "$BACKEND_DIR/.env" ]] || { warn "No $BACKEND_DIR/.env — create it from .env.example (LITELLM keys + SUPABASE_URL)"; }

# --- backend ---------------------------------------------------------------
if [[ -n "$(port_pids "$BACKEND_PORT")" ]]; then
  log "Backend already running on :$BACKEND_PORT — skipping."
else
  log "Starting backend (FastAPI) on http://127.0.0.1:${BACKEND_PORT} …"
  # Load the repo .env, then drop SUPABASE_JWT_SECRET so the backend verifies
  # Supabase access tokens via GoTrue instead of local HS256 (login breaks
  # otherwise). backend/main.py also loads .env itself by absolute path.
  python3 "$LAUNCHER" "$BACKEND_DIR" "$BACKEND_DIR/server.log" \
    "$VENV_PY" -c "
import os
from dotenv import load_dotenv
load_dotenv('.env', override=False)
os.environ.pop('SUPABASE_JWT_SECRET', None)
import uvicorn
uvicorn.run('backend.main:app', host='127.0.0.1', port=$BACKEND_PORT)
" >/dev/null
  for _ in $(seq 1 20); do
    curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1 && break
    sleep 0.5
  done
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    log "Backend is up. Logs: $BACKEND_DIR/server.log"
  else
    err "Backend failed to start — see $BACKEND_DIR/server.log"
    exit 1
  fi
fi

# --- frontend ----------------------------------------------------------------
if [[ -n "$(port_pids "$FRONTEND_PORT")" ]]; then
  log "Frontend already running on :$FRONTEND_PORT — skipping."
else
  log "Starting frontend (Vite) on http://localhost:${FRONTEND_PORT} …"
  python3 "$LAUNCHER" "$FRONTEND_DIR" "$FRONTEND_DIR/dev.log" npm run dev >/dev/null
  for _ in $(seq 1 40); do
    curl -sf "http://localhost:${FRONTEND_PORT}/" >/dev/null 2>&1 && break
    sleep 0.5
  done
  curl -sf "http://localhost:${FRONTEND_PORT}/" >/dev/null 2>&1 \
    && log "Frontend is up. Logs: $FRONTEND_DIR/dev.log" \
    || warn "Frontend still booting (Vite). Logs: $FRONTEND_DIR/dev.log"
fi

echo
log "Sensei is ready:"
log "   Frontend  http://localhost:${FRONTEND_PORT}"
log "   Backend   http://127.0.0.1:${BACKEND_PORT}/health"
log "   Stop both with: ./start-dev.sh stop"
