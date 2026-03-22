# Frontend

This directory contains the React + TypeScript + Vite UI for Project Metis.

## Quick Start

```sh
npm install
npm run dev
```

## Local Config

Optional `.env` file:

```env
VITE_API_URL=http://localhost:8000
```

If not set, the frontend defaults to `http://localhost:8000` in dev and same-origin in production.

Backend machine-specific settings (like local RAG folders and private prompt tweaks)
should go in root `config.local.yaml` (see `config.local.example.yaml`).

## Main Files

- `src/components/ChatInterface.tsx`: chat interface and streaming response handling.
- `src/components/RagPanel.tsx`: RAG status and retrieval panel.
- `src/components/ChatContext.tsx`: current backend context viewer.
- `src/components/Sidebar.tsx`: left sidebar tabs.

## Useful Commands

```sh
npm run build
npm run lint
npm run preview
```
