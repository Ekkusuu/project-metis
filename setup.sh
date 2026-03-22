#!/usr/bin/env sh

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

TORCH_INDEX_URL=${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu126}

install_python() {
  echo "Installing Python dependencies..."
  echo "Using Python binary: $PYTHON_BIN"
  echo "TIP: Activate your virtual environment first if you use one."

  "$PYTHON_BIN" -m pip install --upgrade pip || echo "pip upgrade failed; continuing anyway..."

  "$PYTHON_BIN" -m pip install -r "$SCRIPT_DIR/requirements.txt" || return $?

  "$PYTHON_BIN" -m pip uninstall -y torch torchvision torchaudio >/dev/null 2>&1 || true
  "$PYTHON_BIN" -m pip install torch torchvision torchaudio --index-url "$TORCH_INDEX_URL" || return $?

  echo "Python dependencies installed."
  echo "Verify PyTorch with:"
  echo "$PYTHON_BIN -c \"import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)\""
  return 0
}

install_node_dir() {
  target_dir="$1"
  label="$2"

  if [ ! -d "$target_dir" ]; then
    echo "$label: directory not found at $target_dir"
    return 1
  fi

  if [ -f "$target_dir/package-lock.json" ]; then
    echo "$label: package-lock.json found, running npm ci"
    (cd "$target_dir" && npm ci)
  else
    echo "$label: running npm install"
    (cd "$target_dir" && npm install)
  fi
}

install_node() {
  echo "Installing Node dependencies..."
  install_node_dir "$SCRIPT_DIR/frontend" "Frontend" || return $?
  install_node_dir "$SCRIPT_DIR/backend/llm_service" "Backend LLM service" || return $?
  echo "Node dependencies installed."
  return 0
}

echo "Starting Project Metis setup..."
echo

install_python
PYTHON_EXIT=$?

echo

install_node
NODE_EXIT=$?

echo
echo "Summary:"
if [ "$PYTHON_EXIT" -eq 0 ]; then
  echo "Python setup succeeded"
else
  echo "Python setup failed with exit code $PYTHON_EXIT"
fi

if [ "$NODE_EXIT" -eq 0 ]; then
  echo "Node setup succeeded"
else
  echo "Node setup failed with exit code $NODE_EXIT"
fi

if [ "$PYTHON_EXIT" -ne 0 ]; then
  exit "$PYTHON_EXIT"
fi

if [ "$NODE_EXIT" -ne 0 ]; then
  exit "$NODE_EXIT"
fi

exit 0
