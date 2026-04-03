"""
Chat history management endpoints.
Stores chat histories as JSON in the memory folder.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.memory_manager import save_messages_before_reset

router = APIRouter(prefix="/history", tags=["history"])

PROJECT_ROOT = Path(__file__).parent.parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
CHAT_HISTORY_FILE = MEMORY_DIR / "chat_history.json"

MEMORY_DIR.mkdir(exist_ok=True)


class Message(BaseModel):
    id: str
    text: str
    sender: str
    timestamp: str
    tokensPerSecond: float | None = None
    planningNotes: Optional[List[Dict[str, Any]]] = None


class ChatHistory(BaseModel):
    chatId: Optional[str] = None
    title: Optional[str] = None
    messages: List[Message]
    lastUpdated: str


class ChatSummary(BaseModel):
    id: str
    title: str
    lastUpdated: str
    messageCount: int
    preview: str


class ChatLoadResponse(BaseModel):
    activeChatId: Optional[str]
    chats: List[ChatSummary]
    chat: ChatHistory


class ChatListResponse(BaseModel):
    activeChatId: Optional[str]
    chats: List[ChatSummary]


class ChatRenamePayload(BaseModel):
    title: str


def _now_iso() -> str:
    return datetime.now().isoformat()


def _initial_messages() -> List[Dict[str, Any]]:
    return []


def _strip_legacy_greeting(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        message
        for message in messages
        if not (
            message.get("sender") == "ai"
            and str(message.get("text") or "").strip() == "Hello! How can I assist you today?"
        )
    ]


def _new_chat(title: str = "New chat") -> Dict[str, Any]:
    return {
        "id": str(uuid4()),
        "title": title,
        "customTitle": False,
        "messages": _initial_messages(),
        "lastUpdated": _now_iso(),
        "createdAt": _now_iso(),
    }


def _normalize_message(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    try:
        message = Message(**raw)
    except Exception:
        return None
    return message.model_dump()


def _derive_title(messages: List[Dict[str, Any]], fallback: str = "New chat") -> str:
    for message in messages:
        if message.get("sender") != "user":
            continue
        text = str(message.get("text") or "").strip()
        if not text:
            continue
        first_line = text.splitlines()[0].strip()
        if len(first_line) > 48:
            return f"{first_line[:45].rstrip()}..."
        return first_line
    return fallback


def _preview_text(messages: List[Dict[str, Any]]) -> str:
    for message in reversed(messages):
        text = str(message.get("text") or "").strip()
        if not text:
            continue
        first_line = text.splitlines()[0].strip()
        if len(first_line) > 72:
            return f"{first_line[:69].rstrip()}..."
        return first_line
    return "No messages yet"


def _normalize_chat(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    raw_messages = raw.get("messages")
    normalized_messages = []
    if isinstance(raw_messages, list):
        normalized_messages = [msg for item in raw_messages if (msg := _normalize_message(item))]
    normalized_messages = _strip_legacy_greeting(normalized_messages)

    fallback_title = str(raw.get("title") or "").strip() or "New chat"
    title = _derive_title(normalized_messages, fallback_title)

    return {
        "id": str(raw.get("id") or uuid4()),
        "title": title,
        "customTitle": bool(raw.get("customTitle", False)),
        "messages": normalized_messages,
        "lastUpdated": str(raw.get("lastUpdated") or _now_iso()),
        "createdAt": str(raw.get("createdAt") or _now_iso()),
    }


def _load_store() -> Dict[str, Any]:
    if not CHAT_HISTORY_FILE.exists():
        return {"activeChatId": None, "chats": []}

    with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    if isinstance(raw, dict) and isinstance(raw.get("chats"), list):
        chats = [chat for item in raw["chats"] if (chat := _normalize_chat(item))]
        active_raw = raw.get("activeChatId")
        active_chat_id = str(active_raw) if active_raw else None
        if chats and (not active_chat_id or not any(chat["id"] == active_chat_id for chat in chats)):
            active_chat_id = chats[0]["id"]
        if not chats:
            active_chat_id = None
        return {"activeChatId": active_chat_id, "chats": chats}

    # Migrate legacy single-chat format.
    legacy_chat = _normalize_chat({
        "id": str(uuid4()),
        "title": "New chat",
        "messages": raw.get("messages", []) if isinstance(raw, dict) else [],
        "lastUpdated": raw.get("lastUpdated") if isinstance(raw, dict) else _now_iso(),
    })
    if legacy_chat is None:
        legacy_chat = _new_chat()
    return {"activeChatId": legacy_chat["id"], "chats": [legacy_chat]}


def _save_store(store: Dict[str, Any]) -> None:
    with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=2, ensure_ascii=False)


def _get_chat_or_raise(store: Dict[str, Any], chat_id: str) -> Dict[str, Any]:
    for chat in store["chats"]:
        if chat["id"] == chat_id:
            return chat
    raise HTTPException(status_code=404, detail="Chat not found")


def _chat_summary(chat: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": chat["id"],
        "title": chat["title"],
        "lastUpdated": chat["lastUpdated"],
        "messageCount": len(chat["messages"]),
        "preview": _preview_text(chat["messages"]),
    }


def _build_load_response(store: Dict[str, Any], chat: Dict[str, Any]) -> ChatLoadResponse:
    return ChatLoadResponse(
        activeChatId=store["activeChatId"],
        chats=[ChatSummary(**_chat_summary(item)) for item in store["chats"]],
        chat=ChatHistory(
            chatId=chat["id"],
            title=chat["title"],
            messages=[Message(**item) for item in chat["messages"]],
            lastUpdated=chat["lastUpdated"],
        ),
    )


def _build_fresh_chat_response(store: Dict[str, Any]) -> ChatLoadResponse:
    return ChatLoadResponse(
        activeChatId=None,
        chats=[ChatSummary(**_chat_summary(item)) for item in store["chats"]],
        chat=ChatHistory(
            chatId=None,
            title="New chat",
            messages=[],
            lastUpdated=_now_iso(),
        ),
    )


def _save_messages_to_memory(messages: List[Dict[str, Any]]) -> None:
    def save_in_background() -> None:
        try:
            save_messages_before_reset(messages)
        except Exception as exc:
            print(f"Warning: Failed to save messages to temp_memory in background: {exc}")

    thread = threading.Thread(target=save_in_background, daemon=True)
    thread.start()


@router.get("/chats", response_model=ChatListResponse)
async def list_chats() -> ChatListResponse:
    try:
        store = _load_store()
        _save_store(store)
        return ChatListResponse(
            activeChatId=store["activeChatId"],
            chats=[ChatSummary(**_chat_summary(chat)) for chat in store["chats"]],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list chats: {exc}")


@router.get("/load", response_model=ChatLoadResponse)
async def load_chat_history(chat_id: str | None = Query(default=None)) -> ChatLoadResponse:
    try:
        store = _load_store()
        if not store["chats"]:
            _save_store(store)
            return _build_fresh_chat_response(store)
        target_id = chat_id or store["activeChatId"]
        chat = _get_chat_or_raise(store, target_id)
        store["activeChatId"] = chat["id"]
        _save_store(store)
        return _build_load_response(store, chat)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load chat history: {exc}")


@router.post("/chats", response_model=ChatLoadResponse)
async def create_chat() -> ChatLoadResponse:
    try:
        store = _load_store()
        chat = _new_chat()
        store["chats"] = [chat, *store["chats"]]
        store["activeChatId"] = chat["id"]
        _save_store(store)
        return _build_load_response(store, chat)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create chat: {exc}")


@router.patch("/chats/{chat_id}", response_model=ChatLoadResponse)
async def rename_chat(chat_id: str, payload: ChatRenamePayload) -> ChatLoadResponse:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Chat title is required")

    try:
        store = _load_store()
        chat = _get_chat_or_raise(store, chat_id)
        chat["title"] = title
        chat["customTitle"] = True
        chat["lastUpdated"] = _now_iso()
        store["activeChatId"] = chat["id"]
        store["chats"].sort(key=lambda item: item["lastUpdated"], reverse=True)
        _save_store(store)
        updated_chat = _get_chat_or_raise(store, chat["id"])
        return _build_load_response(store, updated_chat)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to rename chat: {exc}")


@router.delete("/chats/{chat_id}", response_model=ChatLoadResponse)
async def delete_chat(chat_id: str) -> ChatLoadResponse:
    try:
        store = _load_store()
        chat = _get_chat_or_raise(store, chat_id)
        store["chats"] = [item for item in store["chats"] if item["id"] != chat["id"]]

        if not store["chats"]:
            store["activeChatId"] = None
            _save_store(store)
            return _build_fresh_chat_response(store)

        if store["activeChatId"] == chat["id"]:
            store["activeChatId"] = store["chats"][0]["id"]

        _save_store(store)
        active_chat = _get_chat_or_raise(store, store["activeChatId"])
        return _build_load_response(store, active_chat)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {exc}")


@router.post("/save", response_model=ChatLoadResponse)
async def save_chat_history(history: ChatHistory) -> ChatLoadResponse:
    try:
        store = _load_store()
        target_id = history.chatId or store["activeChatId"]
        if target_id:
            chat = _get_chat_or_raise(store, target_id)
        else:
            chat = _new_chat()
            store["chats"] = [chat, *store["chats"]]
        messages = [message.model_dump() for message in history.messages]
        messages = _strip_legacy_greeting(messages)

        chat["messages"] = messages
        chat["lastUpdated"] = _now_iso()
        if chat.get("customTitle"):
            chat["title"] = str(history.title or chat["title"] or "New chat").strip() or "New chat"
        else:
            chat["title"] = _derive_title(messages, str(history.title or chat["title"] or "New chat"))
        store["activeChatId"] = chat["id"]
        store["chats"].sort(key=lambda item: item["lastUpdated"], reverse=True)
        _save_store(store)
        updated_chat = _get_chat_or_raise(store, chat["id"])
        return _build_load_response(store, updated_chat)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save chat history: {exc}")


@router.post("/reset", response_model=ChatLoadResponse)
async def reset_chat_history(chat_id: str | None = Query(default=None)) -> ChatLoadResponse:
    try:
        store = _load_store()
        target_id = chat_id or store["activeChatId"]
        chat = _get_chat_or_raise(store, target_id)

        existing_messages = [
            {"role": "user" if item["sender"] == "user" else "assistant", "content": item["text"]}
            for item in chat["messages"]
        ]
        if existing_messages:
            _save_messages_to_memory(existing_messages)

        chat["messages"] = _initial_messages()
        chat["lastUpdated"] = _now_iso()
        chat["title"] = "New chat"
        chat["customTitle"] = False
        store["activeChatId"] = chat["id"]
        store["chats"].sort(key=lambda item: item["lastUpdated"], reverse=True)
        _save_store(store)
        updated_chat = _get_chat_or_raise(store, chat["id"])
        return _build_load_response(store, updated_chat)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to reset chat history: {exc}")
