#!/usr/bin/env sh

# install_python_requirements.sh
# Installs Python dependencies and PyTorch CUDA 12.6 wheels.

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

if ! command -v pip >/dev/null 2>&1; then
  echo "Warning: 'pip' command not found in PATH. Using '$PYTHON_BIN -m pip' instead."
fi

TORCH_INDEX_URL=${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu126}

echo "NOTE: Activate your Python virtual environment first if you use one."
echo "Using Python binary: $PYTHON_BIN"
echo

echo "Upgrading pip..."
"$PYTHON_BIN" -m pip install --upgrade pip || echo "pip upgrade failed; continuing anyway..."

echo
echo "Installing packages from requirements.txt..."
"$PYTHON_BIN" -m pip install -r "$SCRIPT_DIR/requirements.txt"
REQ_EXIT=$?
if [ "$REQ_EXIT" -ne 0 ]; then
  echo "Failed to install dependencies from requirements.txt"
  exit "$REQ_EXIT"
fi

echo
echo "Uninstalling existing torch packages (if any)..."
"$PYTHON_BIN" -m pip uninstall -y torch torchvision torchaudio >/dev/null 2>&1 || true

echo "Installing PyTorch wheels from: $TORCH_INDEX_URL"
"$PYTHON_BIN" -m pip install torch torchvision torchaudio --index-url "$TORCH_INDEX_URL"
TORCH_EXIT=$?
if [ "$TORCH_EXIT" -ne 0 ]; then
  echo "PyTorch install failed."
  echo "If your machine is not using NVIDIA CUDA 12.6, set TORCH_INDEX_URL to another index or install manually."
  echo "Verification command:"
  echo "$PYTHON_BIN -c \"import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)\""
  exit "$TORCH_EXIT"
fi

echo
echo "All Python packages installed successfully."
echo "Verify PyTorch with:"
echo "$PYTHON_BIN -c \"import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)\""

exit 0
