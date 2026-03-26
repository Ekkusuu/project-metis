from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.routers.chat import router as chat_router
from backend.routers.history import router as history_router
from backend.routers.memory import router as memory_router
from backend.routers.settings import router as settings_router
from backend.llama_engine import get_config

app = FastAPI(title="Project Metis Backend")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
API_PREFIXES = {"chat", "history", "memory", "rag", "settings", "health", "docs", "redoc", "openapi.json"}

# Allow frontend dev server (Vite default 5173) and local origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "*",  # adjust or remove wildcard in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(history_router)
app.include_router(memory_router)
app.include_router(settings_router)


@app.get("/", tags=["root"], include_in_schema=False)
async def read_root():
    if FRONTEND_INDEX_FILE.exists():
        return FileResponse(FRONTEND_INDEX_FILE)
    return {"message": "Project Metis backend is running"}


@app.get("/health", tags=["health"])
async def health():
    """Simple health-check endpoint."""
    return {"status": "ok"}


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(status_code=404, detail="Not Found")

    first_segment = full_path.split("/", 1)[0]
    if first_segment in API_PREFIXES:
        raise HTTPException(status_code=404, detail="Not Found")

    requested_path = (FRONTEND_DIST_DIR / full_path).resolve()
    if FRONTEND_DIST_DIR.resolve() in requested_path.parents and requested_path.is_file():
        return FileResponse(requested_path)

    return FileResponse(FRONTEND_INDEX_FILE)


@app.on_event("startup")
async def startup_event():
    """Run initialization tasks on backend startup."""
    config = get_config()
    
    # Check LLM service connectivity
    print("\n" + "="*60)
    print("Checking LLM service...")
    print("="*60)
    try:
        from backend.llama_engine import get_model, get_llm_service_url
        service_url = get_llm_service_url()
        is_ready = get_model()
        if is_ready:
            print(f"✓ LLM service is ready")
            print(f"  Service URL: {service_url}")
            print(f"  Model path: {config['model']['path']}")
            print(f"  Context size: {config['model'].get('n_ctx', 8192)}")
        else:
            print(f"⚠ LLM service is not ready yet")
            print(f"  Service URL: {service_url}")
            print(f"  Make sure to start the Node.js LLM service:")
            print(f"  cd backend/llm_service && npm install && npm start")
        print("="*60 + "\n")
    except Exception as e:
        print(f"✗ Error connecting to LLM service: {e}")
        print("  Make sure to start the Node.js LLM service:")
        print("  cd backend/llm_service && npm install && npm start")
        print("="*60 + "\n")
    
    # RAG initialization
    rag_cfg = config.get("rag", {})
    if rag_cfg.get("enabled", False):
        print("="*60)
        print("RAG System: Checking for file changes...")
        print("="*60)
        
        try:
            from backend.rag_engine import index_all_folders, get_collection
            
            # Always check for changes (new, modified, or deleted files)
            collection = get_collection()
            count_before = collection.count()
            
            print(f"Current index: {count_before} chunks")
            print("Scanning for new, modified, or deleted files...")
            
            results = index_all_folders(clear_existing=False)
            
            count_after = collection.count()
            total_new_chunks = sum(results.values())
            
            if total_new_chunks > 0:
                print(f"\n✓ Indexed {total_new_chunks} new/updated chunks")
                print(f"  Total chunks in index: {count_before} → {count_after}")
            else:
                print(f"\n✓ No changes detected. Index is up to date.")
            
            print("="*60 + "\n")
        except Exception as e:
            print(f"Error during RAG auto-indexing: {e}")
            print("RAG system may not function correctly. Check your configuration.")


if __name__ == "__main__":
    # Allow quick local run: `python backend/main.py` (works if uvicorn is installed)
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
