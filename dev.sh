#!/usr/bin/env bash
# Paradigm local dev — starts both backend and frontend on fixed ports.
# Usage: ./dev.sh          Start both services
#        ./dev.sh stop     Stop both services
#        ./dev.sh restart  Restart both services

set -euo pipefail

BACKEND_PORT=8000
FRONTEND_PORT=3000
PIDDIR="$HOME/.paradigm"
mkdir -p "$PIDDIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
DIM='\033[2m'
RESET='\033[0m'

log() { echo -e "${CYAN}[paradigm]${RESET} $1"; }
err() { echo -e "${RED}[paradigm]${RESET} $1" >&2; }

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 1
    # Force kill any remaining
    pids=$(lsof -ti:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
      echo "$pids" | xargs kill -9 2>/dev/null || true
      sleep 1
    fi
  fi
}

stop_services() {
  log "Stopping Paradigm services..."

  # Kill by saved PIDs
  for svc in backend frontend; do
    if [ -f "$PIDDIR/$svc.pid" ]; then
      local pid
      pid=$(cat "$PIDDIR/$svc.pid")
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
      fi
      rm -f "$PIDDIR/$svc.pid"
    fi
  done

  # Also clear the ports in case PIDs are stale
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"

  log "${GREEN}Stopped.${RESET}"
}

start_services() {
  local project_dir
  project_dir="$(cd "$(dirname "$0")" && pwd)"

  # Check ports are free
  for port in $BACKEND_PORT $FRONTEND_PORT; do
    if lsof -ti:"$port" &>/dev/null; then
      err "Port $port is in use. Run ${DIM}./dev.sh stop${RESET} first, or free the port."
      lsof -i:"$port" -P 2>/dev/null | head -5
      exit 1
    fi
  done

  log "Starting Paradigm..."
  log "${DIM}Backend  → http://localhost:${BACKEND_PORT}${RESET}"
  log "${DIM}Frontend → http://localhost:${FRONTEND_PORT}${RESET}"
  echo ""

  # Start backend
  cd "$project_dir"
  conda run --no-banner -n paradigm \
    uvicorn backend.api.main:app --reload --port "$BACKEND_PORT" \
    > "$PIDDIR/backend.log" 2>&1 &
  echo $! > "$PIDDIR/backend.pid"

  # Start frontend
  cd "$project_dir/frontend"
  npx vite --port "$FRONTEND_PORT" --strictPort \
    > "$PIDDIR/frontend.log" 2>&1 &
  echo $! > "$PIDDIR/frontend.pid"

  # Wait for backend to be ready
  log "Waiting for backend..."
  for i in $(seq 1 20); do
    if curl -s --max-time 1 "http://localhost:${BACKEND_PORT}/health" &>/dev/null; then
      log "${GREEN}Backend ready.${RESET}"
      break
    fi
    if [ "$i" -eq 20 ]; then
      err "Backend failed to start. Check $PIDDIR/backend.log"
      exit 1
    fi
    sleep 1
  done

  # Wait for frontend
  log "Waiting for frontend..."
  for i in $(seq 1 15); do
    if curl -s --max-time 1 "http://localhost:${FRONTEND_PORT}" &>/dev/null; then
      log "${GREEN}Frontend ready.${RESET}"
      break
    fi
    if [ "$i" -eq 15 ]; then
      err "Frontend failed to start. Check $PIDDIR/frontend.log"
      exit 1
    fi
    sleep 1
  done

  echo ""
  log "${GREEN}Paradigm is running!${RESET}"
  log "  App:     http://localhost:${FRONTEND_PORT}"
  log "  API:     http://localhost:${BACKEND_PORT}"
  log "  Swagger: http://localhost:${BACKEND_PORT}/docs"
  log ""
  log "${DIM}Logs: $PIDDIR/backend.log, $PIDDIR/frontend.log${RESET}"
  log "${DIM}Stop: ./dev.sh stop${RESET}"
}

case "${1:-start}" in
  start)
    start_services
    ;;
  stop)
    stop_services
    ;;
  restart)
    stop_services
    start_services
    ;;
  *)
    echo "Usage: ./dev.sh [start|stop|restart]"
    exit 1
    ;;
esac
