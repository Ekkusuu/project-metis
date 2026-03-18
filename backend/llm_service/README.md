# LLM Service

Node.js service in this directory that runs local GGUF inference via `node-llama-cpp`.

## Install

```sh
cd backend/llm_service
npm install
```

## Run

```sh
npm start
```

Port is read from `config.yaml` (`llm_service.port`, default `3000`).

## Endpoints

- `GET /health`
- `POST /chat/completion`
- `POST /chat/stream`
