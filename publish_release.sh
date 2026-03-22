#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

show_usage() {
  echo "Usage: ./publish_release.sh <tag> [--latest]"
  echo
  echo "Environment overrides:"
  echo "  REGISTRY           Docker registry (default: ghcr.io)"
  echo "  IMAGE_NAMESPACE    Image namespace (default: ekkusuu)"
  echo "  BACKEND_IMAGE      Backend image name (default: project-metis-backend)"
  echo "  LLM_IMAGE          LLM image name (default: project-metis-llm-service)"
  echo "  TORCH_INDEX_URL    Backend Docker build arg for PyTorch wheels"
  echo "  GITHUB_REPOSITORY  GitHub repo for the release (default: Ekkusuu/project-metis)"
}

if [ "$#" -lt 1 ]; then
  show_usage
  exit 1
fi

TAG=""
PUSH_LATEST=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --latest)
      PUSH_LATEST=1
      shift
      ;;
    -h|--help)
      show_usage
      exit 0
      ;;
    *)
      if [ -n "$TAG" ]; then
        echo "Error: unexpected argument: $1"
        show_usage
        exit 1
      fi
      TAG="$1"
      shift
      ;;
  esac
done

if [ -z "$TAG" ]; then
  echo "Error: release tag is required."
  show_usage
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH."
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh is not installed or not in PATH."
  exit 1
fi

REGISTRY=${REGISTRY:-ghcr.io}
IMAGE_NAMESPACE=${IMAGE_NAMESPACE:-ekkusuu}
BACKEND_IMAGE=${BACKEND_IMAGE:-project-metis-backend}
LLM_IMAGE=${LLM_IMAGE:-project-metis-llm-service}
TORCH_INDEX_URL=${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu126}
GITHUB_REPOSITORY=${GITHUB_REPOSITORY:-Ekkusuu/project-metis}

BACKEND_REF="${REGISTRY}/${IMAGE_NAMESPACE}/${BACKEND_IMAGE}:${TAG}"
LLM_REF="${REGISTRY}/${IMAGE_NAMESPACE}/${LLM_IMAGE}:${TAG}"
RELEASE_DIR=".release/${TAG}"
BUNDLE_DIR="${RELEASE_DIR}/project-metis-${TAG}"
RELEASE_COMPOSE="${BUNDLE_DIR}/docker-compose.yml"
RELEASE_CONFIG="${BUNDLE_DIR}/config.local.example.yaml"
RELEASE_NOTES="${BUNDLE_DIR}/RELEASE.md"
RELEASE_ZIP="${RELEASE_DIR}/project-metis-${TAG}.zip"

echo "Publishing Docker release ${TAG}"
echo "Backend image: ${BACKEND_REF}"
echo "LLM image: ${LLM_REF}"
echo

docker build --build-arg "TORCH_INDEX_URL=${TORCH_INDEX_URL}" -f backend/Dockerfile -t "$BACKEND_REF" .
docker build -f backend/llm_service/Dockerfile -t "$LLM_REF" .

docker push "$BACKEND_REF"
docker push "$LLM_REF"

if [ "$PUSH_LATEST" -eq 1 ]; then
  BACKEND_LATEST="${REGISTRY}/${IMAGE_NAMESPACE}/${BACKEND_IMAGE}:latest"
  LLM_LATEST="${REGISTRY}/${IMAGE_NAMESPACE}/${LLM_IMAGE}:latest"

  docker tag "$BACKEND_REF" "$BACKEND_LATEST"
  docker tag "$LLM_REF" "$LLM_LATEST"

  docker push "$BACKEND_LATEST"
  docker push "$LLM_LATEST"
fi

mkdir -p "$BUNDLE_DIR" "$BUNDLE_DIR/model" "$BUNDLE_DIR/rag-models" "$BUNDLE_DIR/memory" "$BUNDLE_DIR/docs" "$BUNDLE_DIR/.chromadb"

cp config.yaml "${BUNDLE_DIR}/config.yaml"
touch "${BUNDLE_DIR}/model/.gitkeep" "${BUNDLE_DIR}/rag-models/.gitkeep" "${BUNDLE_DIR}/memory/.gitkeep" "${BUNDLE_DIR}/docs/.gitkeep" "${BUNDLE_DIR}/.chromadb/.gitkeep"

cat > "$RELEASE_COMPOSE" <<EOF
services:
  llm_service:
    image: ${LLM_REF}
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./model:/app/model:ro
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:3000/health').then((res) => { if (!res.ok) process.exit(1); }).catch(() => process.exit(1));"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 90s

  backend:
    image: ${BACKEND_REF}
    restart: unless-stopped
    depends_on:
      llm_service:
        condition: service_healthy
    environment:
      METIS_LLM_SERVICE_HOST: llm_service
      METIS_LLM_SERVICE_PORT: 3000
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./model:/app/model:ro
      - ./rag-models:/app/rag-models:ro
      - ./memory:/app/memory
      - ./.chromadb:/app/.chromadb
      - ./docs:/app/docs:ro
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
EOF

cp config.local.example.yaml "$RELEASE_CONFIG"

cat > "$RELEASE_NOTES" <<EOF
# Project Metis ${TAG}

## Quick Start

1. Put your GGUF model file in `model/`
2. Put embedding and reranker model folders in `rag-models/`
3. Copy `config.local.example.yaml` to `config.local.yaml` if you need local overrides
4. Run:

```sh
docker compose up
```

5. Open `http://localhost:8000`

## Notes

- `config.yaml` is included in this bundle
- model and embedding files are not included; add your own locally
- `memory/`, `docs/`, and `.chromadb/` are included as local data folders

## Published Images

- `${BACKEND_REF}`
- `${LLM_REF}`
EOF

python - <<PY
from pathlib import Path
import zipfile

bundle_dir = Path(r"${BUNDLE_DIR}")
zip_path = Path(r"${RELEASE_ZIP}")
zip_path.parent.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in bundle_dir.rglob("*"):
        zf.write(path, path.relative_to(bundle_dir.parent))
PY

if gh release view "$TAG" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
  gh release upload "$TAG" "$RELEASE_ZIP" --clobber --repo "$GITHUB_REPOSITORY"
else
  gh release create "$TAG" "$RELEASE_ZIP" \
    --repo "$GITHUB_REPOSITORY" \
    --title "$TAG" \
    --notes "Docker release ${TAG}\n\nImages:\n- ${BACKEND_REF}\n- ${LLM_REF}"
fi

echo
echo "Published successfully."
echo "GitHub release: https://github.com/${GITHUB_REPOSITORY}/releases/tag/${TAG}"
