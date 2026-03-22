#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

GPU_FLAG="--gpu"
BUILD_FLAG=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-gpu)
      GPU_FLAG=""
      shift
      ;;
    --build)
      BUILD_FLAG="--build"
      shift
      ;;
    *)
      break
      ;;
  esac
done

echo "Generating Docker overrides..."
if [ -n "$GPU_FLAG" ]; then
  python prepare_docker_release.py "$GPU_FLAG"
else
  python prepare_docker_release.py
fi

echo "Starting Docker stack..."
docker compose -f docker-compose.yml -f .docker/docker-compose.generated.yml up ${BUILD_FLAG:+$BUILD_FLAG} "$@"
