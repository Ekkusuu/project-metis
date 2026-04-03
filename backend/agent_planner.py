from __future__ import annotations

import json
import random
import re
from typing import Any, Dict, List
import yaml

from backend.llama_engine import chat_completion, strip_thinking_tags


PHASE_ORDER = ["analyze", "context", "compose"]
MIN_TASKS = 3
MAX_TASKS = 6
BAD_TASK_PREFIXES = {
    "tell the user",
    "help the user",
    "explain to the user",
}
FALLBACK_SIGNATURES = {
    "clarify what is needed for",
    "review relevant knowledge and recent chat context",
    "review recent chat context and key constraints",
    "draft and refine the response",
}


def _extract_json_array(raw: str) -> str | None:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return raw

    match = re.search(r"(\[.*\])", raw, re.DOTALL)
    if match:
        return match.group(1)
    return None


def _extract_json_object(raw: str) -> str | None:
    raw = raw.strip()
    if raw.startswith("{") and raw.endswith("}"):
        return raw

    match = re.search(r"(\{.*\})", raw, re.DOTALL)
    if match:
        return match.group(1)
    return None


def _extract_yaml_candidate(raw: str) -> str:
    raw = raw.strip()
    fenced_match = re.search(r"```(?:yaml|yml)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        return fenced_match.group(1).strip()
    return raw


def _normalize_phase(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    if value in PHASE_ORDER:
        return value
    aliases = {
        "understand": "analyze",
        "analyze_request": "analyze",
        "analyse": "analyze",
        "analyze": "analyze",
        "review": "context",
        "context_review": "context",
        "retrieve": "context",
        "context": "context",
        "answer": "compose",
        "draft": "compose",
        "respond": "compose",
        "compose": "compose",
    }
    return aliases.get(value)


def _is_useful_task(content: str) -> bool:
    normalized = content.strip().lower()
    if len(normalized) < 12:
        return False
    if any(normalized.startswith(prefix) for prefix in BAD_TASK_PREFIXES):
        return False
    banned_phrases = [
        "underlying causes of loneliness",
        "social skills and confidence",
        "seek support from friends",
        "mental health professional",
    ]
    if any(phrase in normalized for phrase in banned_phrases):
        return False
    return True


def _parse_line_plan(raw: str) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    for line in raw.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^[-*\d.)\s]+", "", cleaned).strip()
        if ":" not in cleaned:
            continue
        phase_label, content = cleaned.split(":", 1)
        phase = _normalize_phase(phase_label)
        if not phase:
            continue
        content = content.strip()
        if not content:
            continue
        tasks.append({"content": content, "phase": phase})

    if tasks:
        return tasks

    # Fallback parser for outputs that omit phases but still provide task lines.
    unlabeled_lines: List[str] = []
    for line in raw.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.startswith("```"):
            continue
        # Only treat explicit list items as fallback tasks, not arbitrary prose.
        if not re.match(r"^\s*(?:[-*]|\d+[.)]|task\s*\d+|step\s*\d+)", line, re.IGNORECASE):
            continue
        cleaned = re.sub(r"^[-*\d.)\s]+", "", cleaned).strip()
        cleaned = re.sub(r"^(task|step)\s*\d+\s*[:.-]\s*", "", cleaned, flags=re.IGNORECASE).strip()
        if cleaned:
            unlabeled_lines.append(cleaned)

    if len(unlabeled_lines) >= MIN_TASKS:
        phases = ["analyze", "context", "compose", "compose", "compose", "compose"]
        for idx, content in enumerate(unlabeled_lines[:MAX_TASKS]):
            tasks.append({"content": content, "phase": phases[idx]})
    return tasks


def _looks_like_fallback(tasks: List[Dict[str, Any]]) -> bool:
    if not tasks:
        return False
    normalized = [str(task.get("content", "")).strip().lower() for task in tasks]
    return all(any(signature in item for signature in FALLBACK_SIGNATURES) for item in normalized)


def _coerce_tasks(parsed: List[Any], fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(parsed) < MIN_TASKS:
        return fallback
    parsed = parsed[:MAX_TASKS]

    tasks: List[Dict[str, Any]] = []
    for idx, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        phase = _normalize_phase(item.get("phase"))
        if not isinstance(content, str) or not content.strip() or not phase or not _is_useful_task(content):
            continue
        tasks.append({"id": f"task-{idx}", "content": content.strip()[:120], "phase": phase, "status": "pending"})

    if len(tasks) < MIN_TASKS:
        return fallback

    tasks.sort(key=lambda task: PHASE_ORDER.index(str(task.get("phase", "compose"))))
    return tasks


def _coerce_plain_tasks(lines: List[str], fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(lines) < MIN_TASKS:
        return fallback

    phases = ["analyze", "context", "compose", "compose", "compose", "compose"]
    tasks: List[Dict[str, Any]] = []
    for idx, content in enumerate(lines[:MAX_TASKS], start=1):
        normalized_content = content.strip()
        if not _is_useful_task(normalized_content):
            continue
        tasks.append({
            "id": f"task-{idx}",
            "content": normalized_content[:120],
            "phase": phases[idx - 1],
            "status": "pending",
        })
    if len(tasks) < MIN_TASKS:
        return fallback
    return tasks


def _dynamic_fallback_plan(last_user_message: str, rag_enabled: bool) -> List[Dict[str, Any]]:
    topic = re.sub(r"\s+", " ", last_user_message.strip()).strip("?.! ")[:90] or "the request"
    context_phrase = "Check which retrieved notes or prior details actually matter here"
    if not rag_enabled:
        context_phrase = "Check which recent chat details matter most before answering"

    return [
        {
            "id": "task-1",
            "content": f"Pin down whether the user wants reassurance, practical steps, or a follow-up question about {topic}",
            "phase": "analyze",
            "status": "pending",
        },
        {
            "id": "task-2",
            "content": context_phrase,
            "phase": "context",
            "status": "pending",
        },
        {
            "id": "task-3",
            "content": "Decide how direct, empathetic, and concrete the opening of the reply should be",
            "phase": "compose",
            "status": "pending",
        },
    ]


def _parse_plan_response(raw: str, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    yaml_candidate = _extract_yaml_candidate(raw)
    if yaml_candidate:
        try:
            parsed_yaml = yaml.safe_load(yaml_candidate)
        except Exception:
            parsed_yaml = None
        if isinstance(parsed_yaml, dict) and isinstance(parsed_yaml.get("tasks"), list):
            return _coerce_tasks(parsed_yaml["tasks"], fallback)
        if isinstance(parsed_yaml, list):
            return _coerce_tasks(parsed_yaml, fallback)

    json_object = _extract_json_object(raw)
    if json_object:
        parsed = json.loads(json_object)
        if isinstance(parsed, dict) and isinstance(parsed.get("tasks"), list):
            return _coerce_tasks(parsed["tasks"], fallback)

    parsed_tasks = _parse_line_plan(raw)
    if len(parsed_tasks) >= MIN_TASKS:
        return _coerce_tasks(parsed_tasks, fallback)

    json_block = _extract_json_array(raw)
    if json_block:
        parsed = json.loads(json_block)
        if isinstance(parsed, list):
            return _coerce_tasks(parsed, fallback)

    return fallback


def _build_primary_plan_prompt(conversation_excerpt: str, last_user_message: str, rag_enabled: bool, variation_token: int) -> str:
    return (
        "Create an internal execution plan for answering a chat request. "
        "This is a read-only chat assistant with no tools, so the tasks must break the current request into concrete internal subtasks for producing the reply, not broad planning slogans or user advice. "
        "Each task should focus on one real subproblem from this exact request, such as choosing between two plausible interpretations, deciding which prior fact changes the answer, identifying the single missing detail that blocks a confident answer, or choosing the structure of the reply. "
        "Every task must refer to the user's actual request, constraint, ambiguity, missing detail, or decision point. If a task could fit almost any conversation, it is too generic and should be rewritten more specifically. "
        "Do not write generic tasks like clarifying the request, reviewing context, checking emotional cues, determining whether a follow-up question is needed, shaping tone, or generating a response unless they explicitly mention what about this request must be clarified, reviewed, or decided. "
        "Bad example: 'Determine whether the user is asking for personal advice or general information.' Better example: 'Decide whether the user wants a first-step plan for starting a habit or help choosing which habit to start with.' "
        "Bad example: 'Review context.' Better example: 'Check whether the user already mentioned a deadline, resource limit, or prior failed attempt that changes the starting advice.' "
        "Do NOT write tasks that tell the user what to do. Do NOT output answer content or therapy advice. "
        "Return ONLY valid YAML in this exact shape:\n"
        "tasks:\n"
        "  - content: ...\n"
        "    phase: analyze\n"
        f"Use exactly {MIN_TASKS} to {MAX_TASKS} tasks. Never output more than {MAX_TASKS}. Allowed phases are analyze, context, compose. "
        "It is okay to produce slightly different but equally good task phrasing on different runs.\n\n"
        f"RAG enabled: {'yes' if rag_enabled else 'no'}\n"
        f"Conversation:\n{conversation_excerpt}\n\n"
        f"Latest request: {last_user_message}\n"
        f"Variation token: {variation_token}. Use it only to permit mild variation in wording or emphasis, not to change the overall intent."
    )


def _build_rescue_plan_prompt(conversation_excerpt: str, last_user_message: str, rag_enabled: bool, variation_token: int) -> str:
    return (
        f"Write exactly 4 to {MAX_TASKS} short internal tasks for preparing the assistant's next reply. "
        "The tasks must be specific to the current request and should sound like private workflow subtasks. "
        "If a task could be reused unchanged for many different user prompts, it is too generic and should be rewritten. "
        "Prefer concrete subtasks such as resolving an ambiguity in the user's ask, choosing which earlier fact matters most, deciding what assumption must be avoided, deciding whether the reply should answer first or ask one targeted follow-up, or choosing between two response structures specific to this request. "
        "Bad example: 'Review context.' Better example: 'Check whether the user already shared a constraint, deadline, or previous attempt that changes the advice.' "
        "Bad example: 'Generate a response.' Better example: 'Decide whether the reply should open with one concrete first step or first frame the decision the user has to make.' "
        "Do not mention tools. Do not write advice to the user. "
        "Return ONLY valid YAML in this exact shape:\n"
        "tasks:\n"
        "  - content: ...\n"
        "    phase: analyze\n\n"
        f"RAG enabled: {'yes' if rag_enabled else 'no'}\n"
        f"Conversation:\n{conversation_excerpt}\n\n"
        f"Latest request: {last_user_message}\n"
        f"Variation token: {variation_token}. Allow slight wording variance only."
    )


def _build_repair_prompt(raw_output: str) -> str:
    return (
        "Convert the following planner output into valid YAML. "
        "Return ONLY valid YAML in this exact shape:\n"
        "tasks:\n"
        "  - content: ...\n"
        "    phase: analyze\n"
        f"Use exactly {MIN_TASKS} to {MAX_TASKS} tasks and never output more than {MAX_TASKS}. Allowed phases are analyze, context, compose. "
        "Do not invent unrelated tasks; keep the original intent but normalize it.\n\n"
        f"Planner output to repair:\n{raw_output}"
    )


def execute_planning_task(
    messages: List[Dict[str, str]],
    task: Dict[str, Any],
    prior_notes: List[str],
    last_user_message: str,
) -> str:
    phase = str(task.get("phase", "analyze"))
    content = str(task.get("content", "")).strip()
    variation_token = random.randint(1000, 9999)

    conversation_excerpt = "\n".join(
        f"{msg.get('role', 'user')}: {msg.get('content', '')[:280]}"
        for msg in messages[-8:]
        if msg.get("role") in {"system", "user", "assistant"}
    )
    notes_text = "\n".join(f"- {note}" for note in prior_notes[-4:]) or "- None yet"

    prompt = (
        "You are an internal planning worker helping craft the next assistant reply. "
        "Complete the current task and return 1-2 short private working notes. "
        "The notes should influence the final response, but they are not shown to the user. "
        "Focus on things like what the user is really asking, emotional tone, missing context, whether a follow-up question would help, what prior context matters, and what response style fits best. "
        "Do not write the final answer. Do not repeat the task text. Do not mention tools.\n\n"
        f"Current phase: {phase}\n"
        f"Current task: {content}\n\n"
        f"Prior working notes:\n{notes_text}\n\n"
        f"Conversation:\n{conversation_excerpt}\n\n"
        f"Latest request: {last_user_message}\n\n"
        f"Variation token: {variation_token}. Let this allow slight wording variance, but keep the note useful and stable.\n\n"
        "Return only plain text bullet points."
    )

    try:
        raw = chat_completion(
            [
                {
                    "role": "system",
                    "content": "You produce short, useful internal working notes for a chat assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.35,
            top_p=0.9,
            max_tokens=140,
        )
        raw = strip_thinking_tags(raw)

        lines = []
        for line in raw.splitlines():
            cleaned = re.sub(r"^[-*\d.)\s]+", "", line).strip()
            if cleaned:
                lines.append(cleaned[:180])
        if lines:
            return " | ".join(lines[:2])
    except Exception:
        pass

    if phase == "analyze":
        return f"The reply should first pin down what the user really wants from {last_user_message[:80]}."
    if phase == "context":
        return "The reply should use the most relevant recent context and check whether any important detail is still missing."
    return "The reply should balance empathy with directness and decide whether advice or a follow-up question should come first."


def inject_planning_notes(messages: List[Dict[str, str]], notes: List[str]) -> List[Dict[str, str]]:
    if not notes:
        return messages

    enhanced_messages = [dict(message) for message in messages]
    notes_text = "\n".join(f"- {note}" for note in notes)
    for message in enhanced_messages:
        if message.get("role") == "system":
            message["content"] = (
                f"{message.get('content', '')}\n\n"
                "---\n"
                "Internal working notes for this reply:\n"
                f"{notes_text}\n\n"
                "Use these notes to shape the answer, but never mention the planning process or the notes themselves."
            )
            break
    return enhanced_messages


def _fallback_plan(last_user_message: str, rag_enabled: bool) -> List[Dict[str, Any]]:
    topic = last_user_message.strip().splitlines()[0][:80] or "the request"
    context_task = "Review relevant knowledge and recent chat context"
    if not rag_enabled:
        context_task = "Review recent chat context and key constraints"

    return [
        {"id": "task-1", "content": f"Clarify what is needed for {topic}", "phase": "analyze", "status": "pending"},
        {"id": "task-2", "content": context_task, "phase": "context", "status": "pending"},
        {"id": "task-3", "content": "Draft and refine the response", "phase": "compose", "status": "pending"},
    ]


def build_chat_plan(messages: List[Dict[str, str]], last_user_message: str, rag_enabled: bool) -> List[Dict[str, Any]]:
    """Create a small read-only task plan for the current chat turn."""
    fallback: List[Dict[str, Any]] = []
    variation_token = random.randint(1000, 9999)

    conversation_excerpt = "\n".join(
        f"{msg.get('role', 'user')}: {msg.get('content', '')[:240]}"
        for msg in messages[-6:]
        if msg.get("role") in {"user", "assistant"}
    )

    primary_prompt = _build_primary_plan_prompt(conversation_excerpt, last_user_message, rag_enabled, variation_token)
    rescue_prompt = _build_rescue_plan_prompt(conversation_excerpt, last_user_message, rag_enabled, variation_token)

    def _attempt_plan(prompt: str, temperature: float, top_p: float) -> tuple[List[Dict[str, Any]], str]:
        raw = chat_completion(
            [
                {
                    "role": "system",
                    "content": "You create concise internal execution plans for a chat assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            top_p=top_p,
            max_tokens=180,
        )
        raw = strip_thinking_tags(raw)
        print("\n[planner] raw plan output:\n" + raw + "\n")
        return _parse_plan_response(raw, fallback), raw

    def _repair_plan(raw: str) -> List[Dict[str, Any]]:
        repaired = chat_completion(
            [
                {
                    "role": "system",
                    "content": "You normalize planner outputs into strict YAML.",
                },
                {"role": "user", "content": _build_repair_prompt(raw)},
            ],
            temperature=0.0,
            top_p=0.4,
            max_tokens=220,
        )
        repaired = strip_thinking_tags(repaired)
        print("\n[planner] repaired plan output:\n" + repaired + "\n")
        return _parse_plan_response(repaired, fallback)

    try:
        tasks, raw = _attempt_plan(primary_prompt, 0.45, 0.92)
        if _looks_like_fallback(tasks):
            tasks = _repair_plan(raw)
        if _looks_like_fallback(tasks):
            tasks, raw = _attempt_plan(rescue_prompt, 0.55, 0.95)
        if _looks_like_fallback(tasks):
            tasks = _repair_plan(raw)
        return tasks
    except Exception:
        return fallback
