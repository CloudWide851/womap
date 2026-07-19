#!/usr/bin/env bash

set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
STATE_ROOT="${WOMAP_LAUNCHER_STATE_ROOT:-$ROOT/.womap-data/runtime/linux}"
LOG_ROOT="${WOMAP_LAUNCHER_LOG_ROOT:-$ROOT/.womap-data/logs/linux}"
UV_BIN="${WOMAP_UV_BIN:-uv}"
PNPM_BIN="${WOMAP_PNPM_BIN:-pnpm}"
CURL_BIN="${WOMAP_CURL_BIN:-curl}"
WORKER_GRACE_SECONDS="${WOMAP_WORKER_GRACE_SECONDS:-45}"
API_HOST="127.0.0.1"
API_PORT="8000"

mkdir -p "$STATE_ROOT" "$LOG_ROOT"

usage() {
  printf '%s\n' "Usage: ./start-womap.sh {setup|run|worker|status|doctor|upgrade|stop}"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'missing required command: %s\n' "$1" >&2
    return 1
  }
}

load_api_config() {
  local values
  if ! values="$(cd "$ROOT" && "$UV_BIN" run python -c 'from app.shared.config import get_settings; s=get_settings(); print(s.server.host); print(s.server.port)' 2>/dev/null)"; then
    return 0
  fi
  API_HOST="$(printf '%s\n' "$values" | sed -n '1p')"
  API_PORT="$(printf '%s\n' "$values" | sed -n '2p')"
  [[ "$API_PORT" =~ ^[0-9]+$ ]] || API_PORT="8000"
}

record_file() {
  printf '%s/%s.record\n' "$STATE_ROOT" "$1"
}

ready_file() {
  printf '%s/%s.ready\n' "$STATE_ROOT" "$1"
}

stop_file() {
  printf '%s/%s.stop\n' "$STATE_ROOT" "$1"
}

process_start_ticks() {
  local pid="$1" stat remainder
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  stat="$(<"/proc/$pid/stat")" || return 1
  remainder="${stat#*) }"
  set -- $remainder
  printf '%s\n' "${20:-}"
}

write_record() {
  local role="$1" pid="$2" token="$3" ticks
  ticks="$(process_start_ticks "$pid")"
  {
    printf 'pid=%s\n' "$pid"
    printf 'start_ticks=%s\n' "$ticks"
    printf 'command_token=%s\n' "$token"
  } >"$(record_file "$role")"
}

read_record() {
  local role="$1" line file
  file="$(record_file "$role")"
  RECORD_PID=""
  RECORD_START_TICKS=""
  RECORD_COMMAND_TOKEN=""
  [[ -f "$file" ]] || return 1
  while IFS= read -r line; do
    case "$line" in
      pid=*) RECORD_PID="${line#pid=}" ;;
      start_ticks=*) RECORD_START_TICKS="${line#start_ticks=}" ;;
      command_token=*) RECORD_COMMAND_TOKEN="${line#command_token=}" ;;
    esac
  done <"$file"
  [[ "$RECORD_PID" =~ ^[1-9][0-9]*$ && "$RECORD_START_TICKS" =~ ^[0-9]+$ ]]
}

record_is_valid() {
  local role="$1" actual_ticks command_line
  read_record "$role" || return 1
  [[ -r "/proc/$RECORD_PID/cmdline" ]] || return 1
  actual_ticks="$(process_start_ticks "$RECORD_PID")" || return 1
  [[ "$actual_ticks" == "$RECORD_START_TICKS" ]] || return 1
  command_line="$(tr '\0' ' ' <"/proc/$RECORD_PID/cmdline")"
  [[ -n "$RECORD_COMMAND_TOKEN" && "$command_line" == *"$RECORD_COMMAND_TOKEN"* ]]
}

remove_record() {
  rm -f "$(record_file "$1")" "$(ready_file "$1")" "$(stop_file "$1")"
}

build_frontend() {
  if command -v "$PNPM_BIN" >/dev/null 2>&1; then
    (cd "$ROOT/frontend" && "$PNPM_BIN" build)
  elif [[ -f "$ROOT/frontend/dist/index.html" ]]; then
    printf '%s\n' "pnpm unavailable; using existing frontend/dist"
  else
    printf '%s\n' "pnpm is unavailable and frontend/dist is missing" >&2
    return 1
  fi
}

run_migrations() {
  (cd "$ROOT" && "$UV_BIN" run alembic upgrade head)
}

start_api() {
  record_is_valid run-api && {
    printf 'run-api already running (pid=%s)\n' "$RECORD_PID"
    return 0
  }
  remove_record run-api
  load_api_config
  (
    cd "$ROOT"
    exec setsid env WOMAP_RUNTIME_MODE=production WOMAP_WORKER_ENABLED=true \
      "$UV_BIN" run uvicorn app.main:app --host "$API_HOST" --port "$API_PORT"
  ) >>"$LOG_ROOT/run-api.log" 2>&1 &
  local pid=$!
  write_record run-api "$pid" "app.main:app"
  local deadline=$((SECONDS + 60))
  until "$CURL_BIN" --fail --silent --max-time 2 "http://$API_HOST:$API_PORT/health/ready" >/dev/null; do
    if ! record_is_valid run-api || (( SECONDS >= deadline )); then
      stop_service run-api 0
      printf '%s\n' "run-api did not become ready; see .womap-data/logs/linux/run-api.log" >&2
      return 1
    fi
    sleep 1
  done
  printf 'run-api ready at http://%s:%s (pid=%s)\n' "$API_HOST" "$API_PORT" "$pid"
}

start_worker() {
  record_is_valid run-worker && {
    printf 'run-worker already running (pid=%s)\n' "$RECORD_PID"
    return 0
  }
  remove_record run-worker
  local ready stop
  ready="$(ready_file run-worker)"
  stop="$(stop_file run-worker)"
  (
    cd "$ROOT"
    exec setsid env WOMAP_RUNTIME_MODE=production WOMAP_WORKER_ENABLED=true \
      "$UV_BIN" run python -m app.features.jobs.worker --ready-file "$ready" --stop-file "$stop"
  ) >>"$LOG_ROOT/run-worker.log" 2>&1 &
  local pid=$!
  write_record run-worker "$pid" "app.features.jobs.worker"
  local deadline=$((SECONDS + 60))
  until [[ -f "$ready" ]]; do
    if ! record_is_valid run-worker || (( SECONDS >= deadline )); then
      stop_service run-worker 0
      printf '%s\n' "run-worker did not become ready; see .womap-data/logs/linux/run-worker.log" >&2
      return 1
    fi
    sleep 1
  done
  printf 'run-worker ready (pid=%s)\n' "$pid"
}

stop_service() {
  local role="$1" cooperative="${2:-1}" deadline
  if ! record_is_valid "$role"; then
    [[ -f "$(record_file "$role")" ]] && printf '%s\n' "$role record is stale; no process was stopped"
    remove_record "$role"
    return 0
  fi
  local pid="$RECORD_PID"
  if [[ "$role" == "run-worker" && "$cooperative" == "1" ]]; then
    printf 'stop\n' >"$(stop_file "$role")"
    deadline=$((SECONDS + WORKER_GRACE_SECONDS))
    while record_is_valid "$role" && (( SECONDS < deadline )); do sleep 1; done
  fi
  if record_is_valid "$role"; then
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    deadline=$((SECONDS + 5))
    while record_is_valid "$role" && (( SECONDS < deadline )); do sleep 1; done
  fi
  if record_is_valid "$role"; then
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi
  remove_record "$role"
  printf '%s stopped\n' "$role"
}

status_services() {
  local role
  for role in run-worker run-api; do
    if record_is_valid "$role"; then
      printf '%s: running pid=%s\n' "$role" "$RECORD_PID"
    elif [[ -f "$(record_file "$role")" ]]; then
      printf '%s: stale record\n' "$role"
    else
      printf '%s: stopped\n' "$role"
    fi
  done
}

doctor() {
  local failed=0 command
  for command in "$UV_BIN" "$CURL_BIN" setsid; do
    if command -v "$command" >/dev/null 2>&1; then
      printf '%s: available\n' "$command"
    else
      printf '%s: missing\n' "$command"
      failed=1
    fi
  done
  [[ -f "$ROOT/frontend/dist/index.html" ]] && printf '%s\n' "frontend/dist: available" || {
    printf '%s\n' "frontend/dist: missing"
    failed=1
  }
  status_services
  return "$failed"
}

setup() {
  require_command "$UV_BIN"
  require_command "$PNPM_BIN"
  (cd "$ROOT" && "$UV_BIN" sync --frozen)
  (cd "$ROOT/frontend" && "$PNPM_BIN" install --frozen-lockfile && "$PNPM_BIN" build)
}

run_all() {
  require_command "$UV_BIN"
  require_command "$CURL_BIN"
  require_command setsid
  build_frontend
  run_migrations
  start_api
  if ! start_worker; then
    stop_service run-api 0
    return 1
  fi
}

upgrade() {
  if record_is_valid run-api || record_is_valid run-worker; then
    printf '%s\n' "stop WOMAP before upgrade" >&2
    return 1
  fi
  require_command "$UV_BIN"
  (cd "$ROOT" && "$UV_BIN" sync --frozen)
  build_frontend
  run_migrations
}

case "${1:-}" in
  setup) setup ;;
  run) run_all ;;
  worker) require_command "$UV_BIN"; require_command setsid; run_migrations; start_worker ;;
  status) status_services ;;
  doctor) doctor ;;
  upgrade) upgrade ;;
  stop) stop_service run-worker 1; stop_service run-api 0 ;;
  *) usage; exit 2 ;;
esac
