"""
Memory management for Project Metis.
Summarizes per-chat conversation segments directly into YAML long-term memory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import datetime
import yaml

from backend.llama_engine import chat_completion, get_config, strip_thinking_tags
from backend.token_utils import count_tokens

PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
LONG_TERM_DIR = MEMORY_DIR / "long_term"

MEMORY_DIR.mkdir(exist_ok=True)
LONG_TERM_DIR.mkdir(exist_ok=True)


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _memory_cfg() -> Dict[str, Any]:
    memory_cfg = get_config().get("memory", {})
    return {
        "enabled": memory_cfg.get("enabled", True),
        "chat_memory_token_limit": memory_cfg.get("chat_memory_token_limit", memory_cfg.get("temp_memory_token_limit", 3000)),
        "long_term_memory_token_limit": memory_cfg.get("long_term_memory_token_limit", 5000),
    }


def _message_to_transcript_line(message: Dict[str, Any]) -> str:
    sender = str(message.get("sender") or message.get("role") or "user").lower()
    role = "User" if sender == "user" else "AI"
    text = strip_thinking_tags(str(message.get("text") or message.get("content") or "")).strip()
    return f"{role}: {text}" if text else ""


def _messages_to_transcript(messages: List[Dict[str, Any]]) -> str:
    lines = [_message_to_transcript_line(message) for message in messages]
    return "\n".join(line for line in lines if line).strip()


def _format_summary(summary: str) -> List[str]:
    cleaned = strip_thinking_tags(summary).strip()
    lines = cleaned.splitlines()
    facts: List[str] = []
    seen = set()
    for line in lines:
      stripped = line.strip()
      if not stripped:
          continue
      if stripped.startswith(("- ", "* ", "• ")):
          stripped = stripped[2:].strip()
      normalized = stripped.lower()
      if normalized in seen:
          continue
      seen.add(normalized)
      facts.append(stripped)
    return facts


def _load_latest_memory_file() -> Tuple[Path | None, Dict[str, Any]]:
    existing_files = sorted(LONG_TERM_DIR.glob("memory_*.yaml"))
    if not existing_files:
        return None, {"entries": []}
    latest_file = existing_files[-1]
    try:
        with open(latest_file, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            data = {"entries": []}
        if not isinstance(data.get("entries"), list):
            data["entries"] = []
        return latest_file, data
    except Exception:
        return latest_file, {"entries": []}


def _write_memory_entry(entry: Dict[str, Any]) -> None:
    cfg = _memory_cfg()
    long_term_limit = cfg["long_term_memory_token_limit"]
    latest_file, latest_data = _load_latest_memory_file()
    new_entry_doc = {"entries": [entry]}
    new_entry_tokens = count_tokens(yaml.safe_dump(new_entry_doc, sort_keys=False, allow_unicode=False))

    if latest_file is not None:
        existing_yaml = yaml.safe_dump(latest_data, sort_keys=False, allow_unicode=False)
        existing_tokens = count_tokens(existing_yaml)
        if existing_tokens + new_entry_tokens < long_term_limit:
            latest_data["entries"].append(entry)
            with open(latest_file, "w", encoding="utf-8") as handle:
                yaml.safe_dump(latest_data, handle, sort_keys=False, allow_unicode=False)
            return

    timestamp = _now().strftime("%Y%m%d_%H%M%S")
    target = LONG_TERM_DIR / f"memory_{timestamp}.yaml"
    with open(target, "w", encoding="utf-8") as handle:
        yaml.safe_dump({"entries": [entry]}, handle, sort_keys=False, allow_unicode=False)


def summarize_chat_segment(chat_id: str, chat_title: str, messages: List[Dict[str, Any]]) -> None:
    transcript = _messages_to_transcript(messages)
    if not transcript:
        return

    prompts_cfg = get_config().get("prompts", {})
    system_prompt = prompts_cfg.get(
        "memory_summarization_system",
        "You are a memory extraction assistant. Extract only explicitly stated facts about the user.",
    )
    user_prompt_template = prompts_cfg.get(
        "memory_summarization_user",
        "Extract the key facts about the user from this conversation:\n\n```\n{content}\n```",
    )
    user_prompt = user_prompt_template.format(content=transcript)
    summary = chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=500,
    )
    facts = _format_summary(summary)
    if not facts:
        return

    entry = {
        "created_at": _now().isoformat(),
        "source_chat_id": chat_id,
        "source_chat_title": chat_title,
        "message_count": len(messages),
        "facts": facts,
    }
    _write_memory_entry(entry)


def maybe_archive_chat_memory(chat: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    cfg = _memory_cfg()
    state = dict(chat.get("memoryState") or {})
    if not cfg["enabled"]:
        chat["memoryState"] = state
        return chat

    messages = list(chat.get("messages") or [])
    start_index = int(state.get("lastArchivedMessageCount", 0) or 0)
    pending_messages = messages[start_index:]
    if not pending_messages:
        chat["memoryState"] = state
        return chat

    transcript = _messages_to_transcript(pending_messages)
    token_count = count_tokens(transcript)
    if not force and token_count < cfg["chat_memory_token_limit"]:
        state["pendingTokenCount"] = token_count
        chat["memoryState"] = state
        return chat

    summarize_chat_segment(str(chat.get("id") or "unknown-chat"), str(chat.get("title") or "New chat"), pending_messages)
    state["lastArchivedMessageCount"] = len(messages)
    state["pendingTokenCount"] = 0
    state["lastArchivedAt"] = _now().isoformat()
    chat["memoryState"] = state
    return chat


def get_memory_status() -> Dict[str, Any]:
    cfg = _memory_cfg()
    files = sorted(LONG_TERM_DIR.glob("memory_*.yaml"))
    latest_file = files[-1] if files else None
    latest_content = ""
    if latest_file is not None:
        try:
            latest_content = latest_file.read_text(encoding="utf-8")
        except Exception:
            latest_content = ""
    return {
        "enabled": cfg["enabled"],
        "chat_memory_token_limit": cfg["chat_memory_token_limit"],
        "long_term_memory_token_limit": cfg["long_term_memory_token_limit"],
        "long_term_files": len(files),
        "latest_memory_file": latest_file.name if latest_file else None,
        "latest_memory_preview": latest_content[:2000],
    }
