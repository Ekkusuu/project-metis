"""
Memory management endpoints.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from backend.memory_manager import get_memory_status

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryStatus(BaseModel):
    enabled: bool
    chat_memory_token_limit: int
    long_term_memory_token_limit: int
    long_term_files: int
    latest_memory_file: str | None = None
    latest_memory_preview: str = ""


@router.get("/status", response_model=MemoryStatus)
async def get_memory_status_endpoint() -> MemoryStatus:
    return MemoryStatus(**get_memory_status())


@router.post("/summarize")
async def trigger_summarization() -> dict[str, str]:
    return {
        "status": "unsupported",
        "message": "Memory is summarized per chat automatically when the chat threshold is reached.",
    }
