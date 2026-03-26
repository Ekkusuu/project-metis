from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.llama_engine import get_config, get_local_config, reset_config_cache, save_local_config
from backend.rag_engine import index_all_folders, reset_rag_state


router = APIRouter(prefix="", tags=["settings"])


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


class ChatSettings(BaseModel):
    system_prompt: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(ge=0.0, le=1.0)
    max_tokens: int = Field(ge=64, le=8192)


class RagSettings(BaseModel):
    enabled: bool
    folders_to_index: List[str] = Field(default_factory=list)
    top_k: int = Field(ge=1, le=24)
    max_distance: float = Field(ge=-1.0, le=10.0)
    use_reranker: bool
    reranker_top_k: int = Field(ge=1, le=24)
    reranker_min_score: float = Field(ge=-1.0, le=10.0)
    query_generation_count: int = Field(ge=1, le=8)

    @field_validator("folders_to_index", mode="before")
    @classmethod
    def normalize_folders(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("folders_to_index must be a list of paths")
        cleaned: List[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            normalized = item.strip().replace("\\", "/")
            if normalized:
                cleaned.append(normalized)
        return cleaned


class MemorySettings(BaseModel):
    temp_memory_token_limit: int = Field(ge=100, le=50000)
    long_term_memory_token_limit: int = Field(ge=500, le=100000)


class SettingsPayload(BaseModel):
    chat: ChatSettings
    rag: RagSettings
    memory: MemorySettings


def _extract_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    chat_cfg = config.get("chat", {})
    rag_cfg = config.get("rag", {})
    memory_cfg = config.get("memory", {})
    return {
        "chat": {
            "system_prompt": chat_cfg.get("system_prompt", "You are Metis, a helpful AI assistant."),
            "temperature": chat_cfg.get("temperature", 0.7),
            "top_p": chat_cfg.get("top_p", 0.95),
            "max_tokens": chat_cfg.get("max_tokens", 512),
        },
        "rag": {
            "enabled": rag_cfg.get("enabled", True),
            "folders_to_index": [str(path).replace("\\", "/") for path in rag_cfg.get("folders_to_index", ["docs", "memory/long_term"])],
            "top_k": rag_cfg.get("top_k", 6),
            "max_distance": rag_cfg.get("max_distance", 1.5),
            "use_reranker": rag_cfg.get("use_reranker", True),
            "reranker_top_k": rag_cfg.get("reranker_top_k", 2),
            "reranker_min_score": rag_cfg.get("reranker_min_score", 0.1),
            "query_generation_count": rag_cfg.get("query_generation_count", 3),
        },
        "memory": {
            "temp_memory_token_limit": memory_cfg.get("temp_memory_token_limit", 500),
            "long_term_memory_token_limit": memory_cfg.get("long_term_memory_token_limit", 5000),
        },
    }


@router.get("/settings")
def get_settings() -> Dict[str, Any]:
    current = _extract_settings(get_config())
    local_raw = get_local_config()
    local = _extract_settings(_deep_merge(current, local_raw)) if local_raw else {}
    return {
        "settings": current,
        "local_overrides": local,
    }


@router.put("/settings")
def update_settings(payload: SettingsPayload) -> Dict[str, Any]:
    overrides = payload.model_dump()
    current = get_config()
    previous = _extract_settings(current)

    try:
        save_local_config(overrides)
        reset_config_cache()
        reset_rag_state()

        applied = _extract_settings(get_config())
        rag_before = previous.get("rag", {})
        rag_after = applied.get("rag", {})
        reindexed = False
        if rag_after.get("enabled") and rag_before != rag_after:
            try:
                index_all_folders(clear_existing=False)
                reindexed = True
            except Exception as e:
                print(f"Warning: settings save succeeded but reindex failed: {e}")

        return {
            "status": "success",
            "settings": applied,
            "reindexed": reindexed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {e}")
