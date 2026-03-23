from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_release_bundle(tag: str, backend_ref: str, llm_ref: str) -> Path:
    project_root = Path(__file__).resolve().parent
    release_dir = project_root / ".release" / tag
    bundle_dir = release_dir / f"project-metis-{tag}"

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    for folder in ["model", "rag-models", "memory", "docs", ".chromadb"]:
        target = bundle_dir / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / ".gitkeep").touch()

    shutil.copy2(project_root / "config.yaml", bundle_dir / "config.yaml")

    compose_content = f"""services:
  llm_service:
    image: {llm_ref}
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./model:/app/model:ro
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:3000/health').then((res) => {{ if (!res.ok) process.exit(1); }}).catch(() => process.exit(1));"]
      interval: 30s
      timeout: 10s
      retries: 10
      start_period: 300s

  backend:
    image: {backend_ref}
    restart: unless-stopped
    depends_on:
      - llm_service
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
      start_period: 90s
"""

    gpu_compose_content = """services:
  llm_service:
    environment:
      METIS_LLM_GPU: cuda
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: compute,utility
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  backend:
    environment:
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: compute,utility
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
"""

    config_example_content = """# Local overrides for the release bundle.
# Keep indexed folders inside this extracted release directory unless you also
# add matching bind mounts to docker-compose.yml.

rag:
  folders_to_index:
    - "docs"
    - "memory/long_term"

chat:
  system_prompt: >
    You are Metis, a helpful AI assistant.
    Keep responses concise, accurate, and empathetic.
"""

    release_notes = f"""# Project Metis {tag}

## Quick Start

1. Put your GGUF model file in `model/`
2. Put embedding and reranker model folders in `rag-models/`
3. Copy `config.local.example.yaml` to `config.local.yaml` if you need local overrides
   and keep `rag.folders_to_index` inside this release folder by default
4. For standard startup, run:

```sh
docker compose up
```

5. For GPU-enabled startup, run:

```sh
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
```

6. Open `http://localhost:8000`

## Notes

- `config.yaml` is included in this bundle
- model and embedding files are not included; add your own locally
- `memory/`, `docs/`, and `.chromadb/` are included as local data folders
- `docker-compose.gpu.yml` is included for NVIDIA Docker setups
- `config.local.example.yaml` defaults RAG indexing to `docs` and `memory/long_term`

## Published Images

- `{backend_ref}`
- `{llm_ref}`
"""

    write_text(bundle_dir / "docker-compose.yml", compose_content)
    write_text(bundle_dir / "docker-compose.gpu.yml", gpu_compose_content)
    write_text(bundle_dir / "config.local.example.yaml", config_example_content)
    write_text(bundle_dir / "RELEASE.md", release_notes)

    versioned_zip = release_dir / f"project-metis-{tag}.zip"
    stable_zip = release_dir / "project-metis-release.zip"
    release_dir.mkdir(parents=True, exist_ok=True)

    for zip_path in [versioned_zip, stable_zip]:
        if zip_path.exists():
            zip_path.unlink()

    with zipfile.ZipFile(versioned_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in bundle_dir.rglob("*"):
            zf.write(path, path.relative_to(bundle_dir.parent))

    shutil.copy2(versioned_zip, stable_zip)
    return stable_zip


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the downloadable Project Metis release bundle.")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--backend-ref", required=True)
    parser.add_argument("--llm-ref", required=True)
    args = parser.parse_args()

    zip_path = build_release_bundle(args.tag, args.backend_ref, args.llm_ref)
    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
