#!/usr/bin/env sh

# install_all_node_deps.sh
# Installs Node.js dependencies for frontend and backend/llm_service.

set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is not installed or not in PATH."
  exit 1
fi

install_in_dir() {
  target_dir="$1"
  label="$2"

  if [ ! -d "$target_dir" ]; then
    echo "$label: directory not found at $target_dir"
    return 1
  fi

  echo "$label: running npm install"
  (cd "$target_dir" && npm install)
  install_exit=$?

  if [ -f "$target_dir/package-lock.json" ]; then
    echo "$label: package-lock.json found, running npm ci"
    (cd "$target_dir" && npm ci)
    ci_exit=$?
  else
    echo "$label: no package-lock.json, skipping npm ci"
    ci_exit=0
  fi

  if [ "$install_exit" -ne 0 ]; then
    return "$install_exit"
  fi

  if [ "$ci_exit" -ne 0 ]; then
    return "$ci_exit"
  fi

  return 0
}

FRONTEND_ERR=0
BACKEND_ERR=0

echo "Installing frontend dependencies..."
install_in_dir "$SCRIPT_DIR/frontend" "Frontend" || FRONTEND_ERR=$?

echo
echo "Installing backend LLM service dependencies..."
install_in_dir "$SCRIPT_DIR/backend/llm_service" "Backend LLM service" || BACKEND_ERR=$?

echo
echo "Summary:"
if [ "$FRONTEND_ERR" -eq 0 ]; then
  echo "Frontend install succeeded"
else
  echo "Frontend install failed with exit code $FRONTEND_ERR"
fi

if [ "$BACKEND_ERR" -eq 0 ]; then
  echo "Backend LLM service install succeeded"
else
  echo "Backend LLM service install failed with exit code $BACKEND_ERR"
fi

EXIT_CODE=0
if [ "$FRONTEND_ERR" -ne 0 ]; then
  EXIT_CODE="$FRONTEND_ERR"
elif [ "$BACKEND_ERR" -ne 0 ]; then
  EXIT_CODE="$BACKEND_ERR"
fi

exit "$EXIT_CODE"
