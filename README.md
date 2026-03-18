# Project Metis

Project Metis is a local-first AI assistant that combines:
- a React chat UI,
- a FastAPI orchestration backend,
- a Node.js `node-llama-cpp` inference service for GGUF models,
- retrieval-augmented generation (RAG) with ChromaDB,
- and a memory pipeline that preserves long-term user context.

Everything runs locally (no hosted LLM APIs required by default).

## What It Does

- Runs a local GGUF chat model via `node-llama-cpp`.
- Streams model responses token-by-token to the frontend.
- Retrieves relevant context from indexed local folders before generation.
- Shows retrieval diagnostics in the UI (accepted/rejected chunks, distances, rerank scores).
- Persists chat history to disk.
- Stores trimmed/reset conversation text into temp memory, summarizes it, and archives long-term memory.

## How It Works

1. Frontend sends chat history to `POST /chat/stream` on FastAPI.
2. Backend optionally generates multiple contextual RAG queries and retrieves chunks from ChromaDB.
3. Backend injects accepted context chunks into the system prompt.
4. Backend forwards the final message list to Node LLM service (`/chat/stream`).
5. Node service streams tokens back to backend, then backend streams NDJSON to frontend.
6. Backend tracks current context and persists/archives old messages through memory endpoints.

## Tech Stack

- Frontend: React 19, TypeScript, Vite, React Markdown
- Backend API: FastAPI, Uvicorn, Pydantic
- Inference service: Node.js, Express, `node-llama-cpp`
- RAG store: ChromaDB (persistent), local `sentence-transformers` models
- Reranking: `sentence-transformers` CrossEncoder (`bge-reranker-base`)
- Config: `config.yaml`

## Prerequisites

- Python 3.10+
- Node.js 18+
- `npm`
- A compatible GGUF model in `model/`
- Local embedding model folders in `rag-models/` (if RAG is enabled)
- NVIDIA GPU + compatible driver if you want CUDA-accelerated PyTorch/reranker work

## Setup

### 1) Python dependencies

Windows:

```bat
install_python_requirements.bat
```

macOS/Linux:

```sh
sh ./install_python_requirements.sh
```

This installs `requirements.txt` and attempts to install CUDA 12.6 PyTorch wheels by default. Override index if needed:

```sh
TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu sh ./install_python_requirements.sh
```

### 2) Node dependencies

Windows:

```bat
install_all_node_deps.bat
```

macOS/Linux:

```sh
sh ./install_all_node_deps.sh
```

### 3) Configure `config.yaml`

At minimum, verify:
- `model.path` points to a real GGUF file in `model/`
- `model.tokenizer_path` points to an existing tokenizer folder
- `rag.folders_to_index` paths exist on your machine

### 4) Start services

Windows:

```bat
start.bat
```

macOS/Linux:

```sh
sh ./start.sh
```

Manual startup (all platforms):

```sh
# terminal 1
cd backend/llm_service && npm start

# terminal 2
python -m uvicorn backend.main:app --reload

# terminal 3
cd frontend && npm run dev
```

Service URLs:
- LLM service: `http://localhost:3000`
- FastAPI backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

## Configuration Reference (`config.yaml`)

Key sections:
- `model`: GGUF path, tokenizer path, context size, GPU layer offload, thread settings, flash attention, memory locking
- `chat`: system prompt and generation defaults (`temperature`, `top_p`, `max_tokens`)
- `llm_service`: host and port used by backend to reach Node service
- `memory`: temp and long-term token thresholds
- `rag`: on/off, folders, chunking, retrieval limits, distance filter, embedding model, Chroma persistence, query generation prompts, reranker settings
- `prompts`: memory summarization prompts

Note: this project uses config values, not environment variables, for most runtime behavior.

## API Highlights

- `GET /health` - backend health
- `POST /chat` - non-streaming chat
- `POST /chat/stream` - streaming chat + RAG augmentation
- `GET /chat/context` - current backend context snapshot
- `GET /history/load`, `POST /history/save`, `POST /history/reset`
- `GET /memory/status`, `POST /memory/summarize`
- `POST /rag/reindex`, `GET /rag/stats`, `POST /rag/clear`, `GET /rag/last-retrieval`

Node LLM service endpoints (internal to backend, but callable directly):
- `GET /health`
- `POST /chat/completion`
- `POST /chat/stream`

## File Structure

```text
Project Metis/
|- backend/
|  |- main.py
|  |- llama_engine.py
|  |- rag_engine.py
|  |- context_manager.py
|  |- memory_manager.py
|  |- token_utils.py
|  |- routers/
|  |  |- chat.py
|  |  |- history.py
|  |  |- memory.py
|  |- llm_service/
|     |- server.js
|     |- package.json
|- frontend/
|  |- src/components/
|  |  |- ChatInterface.tsx
|  |  |- RagPanel.tsx
|  |  |- ChatContext.tsx
|  |  |- Sidebar.tsx
|  |- package.json
|- memory/
|  |- chat_history.json
|  |- temp_memory.txt
|  |- long_term/
|  |- MEMORY_SYSTEM.md
|- model/
|- rag-models/
|- config.yaml
|- requirements.txt
|- install_python_requirements.bat
|- install_python_requirements.sh
|- install_all_node_deps.bat
|- install_all_node_deps.sh
|- start.bat
|- start.sh
```

## Settings and Behavior Notes

- Frontend API base defaults to `http://localhost:8000` and can be overridden with `frontend/.env` using `VITE_API_URL`.
- Chat history is stored in `memory/chat_history.json` and reloaded on app start.
- Resetting chat saves prior conversation to temp memory asynchronously, then resets visible history immediately.
- Context trimming keeps system prompt and newer messages; removed messages are appended to temp memory.
- Temp memory is summarized into `memory/long_term/memory_*.md` once token limit is reached.
- RAG indexing runs at backend startup and checks for changed/deleted files.

## Caveats

- `config.yaml` currently contains machine-specific folder paths under `rag.folders_to_index`; these must be updated per machine.
- `requirements.txt` intentionally does not pin `torch`; install method depends on your CUDA/CPU setup.
- `node-llama-cpp`, local embeddings, and reranker models can be RAM/VRAM intensive.
- If tokenizer paths or model folders are missing, token counting/RAG quality degrades or features fail.
- The backend CORS list currently includes `"*"`; tighten this for production.
