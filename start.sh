#!/usr/bin/env sh

# start.sh
# Starts all Project Metis services in one terminal session.

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Error: Python is not installed or not in PATH."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is not installed or not in PATH."
  exit 1
fi

LLM_PID=""
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo
  echo "Stopping Project Metis services..."

  if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi

  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi

  if [ -n "$LLM_PID" ] && kill -0 "$LLM_PID" >/dev/null 2>&1; then
    kill "$LLM_PID" >/dev/null 2>&1 || true
  fi

  wait >/dev/null 2>&1 || true
  echo "All services stopped."
}

trap cleanup INT TERM EXIT

echo "============================================================"
echo "Starting Project Metis Services"
echo "============================================================"

echo "Starting LLM Service (Node.js)..."
(
  cd "$SCRIPT_DIR/backend/llm_service" || exit 1
  npm start
) &
LLM_PID=$!

sleep 5

echo "Starting FastAPI Backend (Python)..."
(
  cd "$SCRIPT_DIR" || exit 1
  "$PYTHON_BIN" -m uvicorn backend.main:app --reload
) &
BACKEND_PID=$!

sleep 3

echo "Starting Frontend (Vite)..."
(
  cd "$SCRIPT_DIR/frontend" || exit 1
  npm run dev
) &
FRONTEND_PID=$!

echo
echo "============================================================"
echo "All services started"
echo "============================================================"
echo "LLM Service:  http://localhost:3000"
echo "Backend API:  http://localhost:8000"
echo "Frontend:     http://localhost:5173"
echo "============================================================"
echo "Press Ctrl+C to stop all services."
echo

wait
