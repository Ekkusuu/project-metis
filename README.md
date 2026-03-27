# Project Metis

![Project Metis banner](frontend/src/assets/banner.png)

Project Metis is a local-first AI assistant with three parts:
- a React frontend,
- a FastAPI backend,
- a Node `node-llama-cpp` LLM service.

It can also index local folders for RAG and store conversation memory on disk.

## Downloading a Release

Download the latest Docker release bundle directly:

**[⬇ Download latest release zip](https://github.com/Ekkusuu/project-metis/releases/latest/download/project-metis-release.zip)**

The download flow is simple:
1. open the GitHub Release page,
2. download the release zip,
3. extract it,
4. put their GGUF file in `model/`,
5. put embedding and reranker folders in `rag-models/`,
6. run `docker compose up`.

If NVIDIA Docker is configured on that machine, run:

```sh
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
```

Important:
- the Docker release includes the application code,
- it does not include GGUF model files or embedding model folders

Typical release folder layout:

```text
metis-release/
|- docker-compose.yml
|- docker-compose.gpu.yml
|- config.yaml
|- config.local.example.yaml
|- RELEASE.md
|- model/
|- rag-models/
|- memory/
|- docs/
|- .chromadb/
```

Inside that folder, copy `config.local.example.yaml` to `config.local.yaml` if you want local overrides.
The release example config uses `docs` and `memory/long_term` for RAG by default.

## Requirements

- Python 3.10+
- Node.js 18+
- `npm`
- a GGUF model in `model/`
- embedding / reranker models in `rag-models/` if RAG is enabled
- Docker Desktop or Docker Engine if you want the Docker workflow
- NVIDIA GPU + drivers if you want GPU acceleration

## Manual Setup

Use this when you want the normal dev workflow with separate services.

### 1. Install everything

Windows:

```bat
setup.bat
```

macOS / Linux:

```sh
sh ./setup.sh
```

If you need CPU-only PyTorch:

```sh
TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu sh ./setup.sh
```

### 2. Start the app

Windows:

```bat
start.bat
```

macOS / Linux:

```sh
sh ./start.sh
```

Or run each service manually:

```sh
# terminal 1
cd backend/llm_service && npm start

# terminal 2
python -m uvicorn backend.main:app --reload

# terminal 3
cd frontend && npm run dev
```

Manual dev URLs:
- frontend: `http://localhost:5173`
- backend: `http://localhost:8000`
- llm service: `http://localhost:3000`

## Docker Setup


In Docker, the frontend is built and served by the backend, so you open one URL:
- app: `http://localhost:8000`

Use the default compose file for the normal startup path:

```sh
docker compose up
```

Use the GPU override only on machines with working NVIDIA Docker support:

```sh
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
```

### Recommended commands

Windows:

```bat
start_docker.bat
```

macOS / Linux / Git Bash:

```sh
./start_docker.sh
```

### No GPU

Windows:

```bat
start_docker.bat --no-gpu
```

macOS / Linux / Git Bash:

```sh
./start_docker.sh --no-gpu
```

### Force rebuild

Use this only when image-level things changed, such as:
- Dockerfiles,
- Python dependencies,
- Node dependencies,
- CUDA / `node-llama-cpp` build setup.

Windows:

```bat
start_docker.bat --build
```

macOS / Linux / Git Bash:

```sh
./start_docker.sh --build
```

### When you do not need a rebuild

Just run the normal Docker wrapper again when you changed:
- `config.yaml`
- `config.local.yaml`
- RAG folders to index
- local model or document paths

## Configuration

Main config lives in `config.yaml`.

Optional machine-specific overrides live in `config.local.yaml`.
That file is git-ignored and is the right place for:
- local file paths,
- personal prompts,
- machine-specific model settings.

To create it:

```sh
cp config.local.example.yaml config.local.yaml
```

At minimum, check these values:
- `model.path`
- `model.tokenizer_path`
- `rag.folders_to_index`
- `rag.embedding_model`
- `rag.reranker_model`

## How Docker Path Mapping Works

If your config contains absolute host paths like `C:\Users\...` or `/home/...`, containers cannot read them automatically.

`prepare_docker_release.py` solves this by:
- reading `config.yaml` and `config.local.yaml`,
- detecting absolute host paths,
- generating `.docker/config.local.generated.yaml`,
- generating `.docker/docker-compose.generated.yml`.

That generated Compose file is a local override layered on top of `docker-compose.yml`.
It adds the bind mounts needed for the paths found in your config.

In short:
- your host folder gets mounted into the container,
- the generated config points the app to that in-container path.

You usually do not need to run this script directly because the Docker wrappers already do it for you.

## Useful Commands

Stop Docker stack:

```sh
docker compose down
```

Manually generate Docker overrides:

```sh
python prepare_docker_release.py --gpu
```

Run Docker manually with generated overrides:

```sh
docker compose -f docker-compose.yml -f .docker/docker-compose.generated.yml up
```

Rebuild only the LLM service from scratch:

```sh
docker compose -f docker-compose.yml -f .docker/docker-compose.generated.yml build --no-cache llm_service
```

## Publishing a Docker Release

The simplest setup now is GitHub Actions.

When a GitHub Release is published, `.github/workflows/publish-release.yml` will:
- build the backend and LLM Docker images,
- push them to `ghcr.io`,
- generate the downloadable release zip,
- upload `project-metis-release.zip` to the GitHub Release.

What happens:
- the backend and LLM images are built and pushed,
- the release tag is used as the Docker image tag,
- a zip bundle is generated,
- the zip is uploaded to the GitHub Release.

To use the GitHub Actions flow:
- create or publish a GitHub Release with the version tag you want,
- make sure the repository Actions permissions allow `contents: write` and `packages: write`,
- wait for the `Publish Release` workflow to finish.

The release zip contains:
- `docker-compose.yml`
- `docker-compose.gpu.yml`
- `config.yaml`
- `config.local.example.yaml`
- `RELEASE.md`
- `model/`, `rag-models/`, `memory/`, `docs/`, `.chromadb/`

The default release images are published for both `linux/amd64` and `linux/arm64`, so the standard `docker compose up` flow works on Intel/AMD Linux and Apple Silicon Docker setups.

On some platforms, the LLM service may take longer on first startup while `node-llama-cpp` prepares a compatible local build.

Default published image names:
- `ghcr.io/ekkusuu/project-metis-backend:<tag>`
- `ghcr.io/ekkusuu/project-metis-llm-service:<tag>`

Example:
- `ghcr.io/ekkusuu/project-metis-backend:v1.0.0`
- `ghcr.io/ekkusuu/project-metis-llm-service:v1.0.0`

## Project Layout

```text
Project Metis/
|- backend/
|- frontend/
|- model/
|- rag-models/
|- memory/
|- docs/
|- config.yaml
|- config.local.yaml        # optional, git-ignored
|- docker-compose.yml
|- prepare_docker_release.py
|- generate_release_bundle.py
|- setup.bat
|- setup.sh
|- start.bat
|- start.sh
|- start_docker.bat
|- start_docker.sh
```

## API Endpoints

Backend:
- `GET /health`
- `POST /chat`
- `POST /chat/stream`
- `GET /chat/context`
- `GET /history/load`
- `POST /history/save`
- `POST /history/reset`
- `GET /memory/status`
- `POST /memory/summarize`
- `POST /rag/reindex`
- `GET /rag/stats`
- `POST /rag/clear`
- `GET /rag/last-retrieval`

LLM service:
- `GET /health`
- `POST /chat/completion`
- `POST /chat/stream`

## Notes

- frontend API defaults to `http://localhost:8000` in dev and same-origin in production
- chat history is stored in `memory/chat_history.json`
- long-term memory files are written under `memory/long_term/`
- RAG indexing runs on backend startup and can also be triggered through the API
- keep personal paths and prompt edits in `config.local.yaml`
