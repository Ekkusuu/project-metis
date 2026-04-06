from __future__ import annotations

from copy import deepcopy
from uuid import uuid4
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.llama_engine import get_base_config, get_config, get_local_config, reset_config_cache, save_local_config
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


class SettingsPreset(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    settings: SettingsPayload


class SettingsPresetCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    settings: SettingsPayload


class SettingsPresetUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    settings: SettingsPayload


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


def _normalize_presets(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        preset_id = str(item.get("id") or uuid4())
        title = str(item.get("title") or "Untitled preset").strip()
        description = str(item.get("description") or "").strip()
        settings_data = item.get("settings")
        if not isinstance(settings_data, dict):
            continue
        try:
            validated = SettingsPayload(**settings_data)
        except Exception:
            continue
        normalized.append(
            {
                "id": preset_id,
                "title": title[:80],
                "description": description[:240],
                "settings": validated.model_dump(),
            }
        )
    return normalized


def _read_presets() -> List[Dict[str, Any]]:
    local = get_local_config()
    return _normalize_presets(local.get("settings_presets", []))


def _write_presets(presets: List[Dict[str, Any]]) -> None:
    local = get_local_config()
    local["settings_presets"] = presets
    save_local_config(local)


def _read_active_preset_id() -> Optional[str]:
    local = get_local_config()
    value = local.get("active_settings_preset_id")
    return str(value) if isinstance(value, str) and value.strip() else None


def _write_active_preset_id(preset_id: Optional[str]) -> None:
    local = get_local_config()
    if preset_id:
      local["active_settings_preset_id"] = preset_id
    else:
      local.pop("active_settings_preset_id", None)
    save_local_config(local)


def _current_settings_preset() -> Dict[str, Any]:
    return {
        "id": "current-settings",
        "title": "Default settings",
        "description": "The baseline configuration Metis uses when no saved preset is selected.",
        "settings": _extract_settings(get_base_config()),
        "readonly": True,
    }


def _apply_settings_override(overrides: Dict[str, Any]) -> Dict[str, Any]:
    current = get_config()
    previous = _extract_settings(current)

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


@router.get("/settings")
def get_settings() -> Dict[str, Any]:
    current = _extract_settings(get_config())
    local_raw = get_local_config()
    local = _extract_settings(_deep_merge(current, local_raw)) if local_raw else {}
    return {
        "settings": current,
        "local_overrides": local,
        "current_preset": _current_settings_preset(),
        "active_preset_id": _read_active_preset_id(),
        "presets": _read_presets(),
    }


@router.put("/settings")
def update_settings(payload: SettingsPayload) -> Dict[str, Any]:
    overrides = payload.model_dump()

    try:
        local = get_local_config()
        local.update(overrides)
        local.pop("active_settings_preset_id", None)
        result = _apply_settings_override(local)
        result["current_preset"] = _current_settings_preset()
        result["active_preset_id"] = None
        result["presets"] = _read_presets()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {e}")


@router.post("/settings/presets")
def create_settings_preset(payload: SettingsPresetCreate) -> Dict[str, Any]:
    try:
        presets = _read_presets()
        preset = {
            "id": str(uuid4()),
            "title": payload.title.strip(),
            "description": payload.description.strip(),
            "settings": payload.settings.model_dump(),
        }
        presets.append(preset)
        _write_presets(presets)
        return {"status": "success", "preset": preset, "current_preset": _current_settings_preset(), "active_preset_id": _read_active_preset_id(), "presets": presets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save preset: {e}")


@router.put("/settings/presets/{preset_id}")
def update_settings_preset(preset_id: str, payload: SettingsPresetUpdate) -> Dict[str, Any]:
    presets = _read_presets()
    index = next((i for i, item in enumerate(presets) if item.get("id") == preset_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Preset not found")

    updated = {
        "id": preset_id,
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "settings": payload.settings.model_dump(),
    }
    presets[index] = updated
    try:
        _write_presets(presets)
        return {"status": "success", "preset": updated, "current_preset": _current_settings_preset(), "active_preset_id": _read_active_preset_id(), "presets": presets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update preset: {e}")


@router.delete("/settings/presets/{preset_id}")
def delete_settings_preset(preset_id: str) -> Dict[str, Any]:
    presets = _read_presets()
    next_presets = [item for item in presets if item.get("id") != preset_id]
    if len(next_presets) == len(presets):
        raise HTTPException(status_code=404, detail="Preset not found")

    try:
        active_id = _read_active_preset_id()
        if active_id == preset_id:
            _write_active_preset_id(None)
        _write_presets(next_presets)
        return {"status": "success", "current_preset": _current_settings_preset(), "active_preset_id": _read_active_preset_id(), "presets": next_presets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete preset: {e}")


@router.put("/settings/presets/{preset_id}/apply")
def apply_settings_preset(preset_id: str) -> Dict[str, Any]:
    presets = _read_presets()
    preset = next((item for item in presets if item.get("id") == preset_id), None)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    try:
        local = get_local_config()
        local.update(preset.get("settings", {}))
        local["active_settings_preset_id"] = preset_id
        result = _apply_settings_override(local)
        result["preset"] = preset
        result["current_preset"] = _current_settings_preset()
        result["active_preset_id"] = preset_id
        result["presets"] = presets
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply preset: {e}")
