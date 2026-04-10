from __future__ import annotations

import json
import random
import re
import time
from typing import Any, Dict, List
import yaml

from backend.llama_engine import add_generation_metrics, chat_completion, get_config, strip_thinking_tags, strip_to_final_text
from backend.token_utils import count_tokens


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
    yaml_match = re.search(r"(?:^|\n)(tasks\s*:.*)$", raw, re.DOTALL | re.IGNORECASE)
    if yaml_match:
        return yaml_match.group(1).strip()
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


def _clean_task_content(content: str) -> str:
    cleaned = content.strip()
    cleaned = re.sub(r"^content\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _extract_task_resolution(output: str) -> str:
    text = strip_to_final_text(output).strip() or strip_thinking_tags(output).strip()
    if not text:
        return ""

    conclusion_match = re.search(r"(?:^|\n)(?:Conclusion(?: for [^\n:]+)?|Recommendation|Decision)\s*:?\s*(.*)$", text, re.IGNORECASE | re.DOTALL)
    if conclusion_match:
        conclusion = conclusion_match.group(1).strip()
        if conclusion:
            return conclusion.split("\n\n", 1)[0].strip()

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if paragraphs:
        return paragraphs[-1]
    return text


def _topic_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z]{3,}", text.lower())
        if token not in {
            "what", "when", "where", "which", "with", "this", "that", "from", "have", "were",
            "they", "them", "then", "than", "your", "just", "about", "would", "could", "should",
            "there", "their", "into", "also", "only", "want", "need", "know", "tell", "does",
            "who", "how", "why",
        }
    }


def _is_related_to_latest(latest_message: str, older_message: str) -> bool:
    latest_tokens = _topic_tokens(latest_message)
    older_tokens = _topic_tokens(older_message)
    if not latest_tokens or not older_tokens:
        return False
    return len(latest_tokens & older_tokens) > 0


def _select_recent_conversation(messages: List[Dict[str, str]], max_messages: int) -> List[Dict[str, str]]:
    latest_user = next((msg for msg in reversed(messages) if msg.get("role") == "user"), None)
    if latest_user is None:
        return []

    latest_content = str(latest_user.get("content", ""))
    relevant = [msg for msg in messages if msg.get("role") in {"user", "assistant"}]
    trailing = relevant[-max_messages:]
    selected: List[Dict[str, str]] = []
    for msg in trailing:
        if msg is latest_user:
            selected.append(msg)
            continue
        if _is_related_to_latest(latest_content, str(msg.get("content", ""))):
            selected.append(msg)

    if latest_user not in selected:
        selected.append(latest_user)
    return selected


def _select_recent_task_context(messages: List[Dict[str, str]], max_messages: int) -> List[Dict[str, str]]:
    relevant = [msg for msg in messages if msg.get("role") in {"user", "assistant"}]
    if not relevant:
        return []
    return relevant[-max_messages:]


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
        # Only treat explicit task/step items as fallback tasks, not generic markdown bullets.
        if not re.match(r"^\s*(?:task\s*\d+|step\s*\d+|\d+[.)]\s*(?:analyze|context|compose|task|step))", line, re.IGNORECASE):
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
        return True
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
        if not isinstance(content, str) or not content.strip() or not phase:
            continue
        cleaned_content = _clean_task_content(content)
        if not cleaned_content or not _is_useful_task(cleaned_content):
            continue
        tasks.append({"id": f"task-{idx}", "content": cleaned_content, "phase": phase, "status": "pending"})

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
        normalized_content = _clean_task_content(content)
        if not _is_useful_task(normalized_content):
            continue
        tasks.append({
            "id": f"task-{idx}",
            "content": normalized_content,
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
        "The latest request is the primary target. Older conversation context is secondary background only, and should be ignored if it is not directly relevant to answering the latest request. "
        "If the user has changed topics, make tasks for the new topic instead of carrying over assumptions from earlier turns. "
        "Each task should focus on one real subproblem from this exact request, such as choosing between two plausible interpretations, deciding which prior fact changes the answer, identifying the single missing detail that blocks a confident answer, or choosing the structure of the reply. "
        "Every task must refer to the user's actual request, constraint, ambiguity, missing detail, or decision point. If a task could fit almost any conversation, it is too generic and should be rewritten more specifically. "
        "Use the smallest number of tasks that fully covers the real subproblems. Usually 3 or 4 tasks are enough. Only use 5 or 6 if the request genuinely has that many distinct decision points. "
        "Do not write generic tasks like clarifying the request, reviewing context, checking emotional cues, determining whether a follow-up question is needed, shaping tone, or generating a response unless they explicitly mention what about this request must be clarified, reviewed, or decided. "
        "Each task must be a short task title, not an explanation. Aim for roughly 6 to 12 words. Do not include prefixes like 'content:' or extra commentary. "
        "If the latest request is a simple factual question, keep the tasks factual. Do not introduce emotional-support, dating, therapy, or relationship tasks unless the latest request is actually about those topics. "
        "For example, for 'who is riki?' good tasks are things like identifying which entity the retrieved evidence points to, checking whether the name is ambiguous, and deciding how to answer concisely. Bad tasks would mention emotional state, dating, encouragement, or practical life advice. "
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
        f"Write between {MIN_TASKS} and {MAX_TASKS} short internal tasks for preparing the assistant's next reply. "
        "The latest request is the primary target. Older conversation context is secondary background only, and should be ignored if it is not directly relevant to answering the latest request. "
        "If the user has changed topics, make tasks for the new topic instead of carrying over assumptions from earlier turns. "
        "The tasks must be specific to the current request and should sound like private workflow subtasks. "
        "If a task could be reused unchanged for many different user prompts, it is too generic and should be rewritten. "
        "Use the smallest number of tasks that fully covers the real subproblems. Usually 3 or 4 tasks are enough. Only use 5 or 6 if the request genuinely has that many distinct decision points. "
        "Each task must be a short task title, not an explanation. Aim for roughly 6 to 12 words. Do not include prefixes like 'content:' or any other field labels. "
        "If the latest request is a simple factual question, keep the tasks factual. Do not introduce emotional-support, dating, therapy, or relationship tasks unless the latest request is actually about those topics. "
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
        "Merge redundant tasks and keep only the smallest set that covers the distinct subproblems. "
        "Each task must be a short task title, not an explanation. Aim for roughly 6 to 12 words. Remove prefixes like 'content:' if they appear. "
        "Do not invent unrelated tasks; keep the original intent but normalize it.\n\n"
        f"Planner output to repair:\n{raw_output}"
    )


def execute_planning_task(
    messages: List[Dict[str, str]],
    task: Dict[str, Any],
    completed_tasks: List[Dict[str, str]],
    last_user_message: str,
) -> str:
    result = execute_planning_task_with_metrics(messages, task, completed_tasks, last_user_message)
    return str(result.get("note", ""))


def execute_planning_task_with_metrics(
    messages: List[Dict[str, str]],
    task: Dict[str, Any],
    completed_tasks: List[Dict[str, str]],
    last_user_message: str,
) -> Dict[str, Any]:
    phase = str(task.get("phase", "analyze"))
    content = str(task.get("content", "")).strip()
    variation_token = random.randint(1000, 9999)
    chat_system_prompt = get_config().get("chat", {}).get("system_prompt", "You are Metis, a helpful AI assistant.")

    retrieved_context_blocks: List[str] = []
    for msg in messages:
        if msg.get("role") != "system":
            continue
        content_text = str(msg.get("content", ""))
        marker = "Relevant information from your knowledge base:"
        if marker not in content_text:
            continue
        extracted = content_text.split(marker, 1)[1]
        extracted = extracted.split("Use this information to answer the user's question.", 1)[0].strip()
        if extracted:
            retrieved_context_blocks.append(extracted)

    retrieved_context_text = "\n\n".join(retrieved_context_blocks).strip() or "- None"

    recent_messages = _select_recent_task_context(messages, max_messages=4)
    conversation_excerpt = "\n".join(
        f"{msg.get('role', 'user')}: {msg.get('content', '')[:280]}"
        for msg in recent_messages
    )
    completed_tasks_text = "\n\n".join(
        f"Completed task: {item.get('task', '').strip()}\n"
        f"Resolved conclusion: {_extract_task_resolution(str(item.get('output', '')))}"
        for item in completed_tasks[-4:]
        if item.get('task') and _extract_task_resolution(str(item.get('output', '')))
    ) or "- None yet"

    prompt = (
        f"Core assistant identity and behavior:\n{chat_system_prompt}\n\n"
        "You are an internal planning worker helping craft the next assistant reply. "
        "You must solve only the current task for the latest user message. "
        "If older conversation context points to a different topic, ignore it. "
        "The current task and latest user message always override older context. "
        "If the conversation includes retrieved knowledge-base context, you must use that retrieved information when it is relevant to the task. "
        "Treat retrieved context as real evidence for the task, not as optional background. "
        "Complete the current task and produce a full internal subresponse for that task. "
        "This subresponse is not shown directly to the user, but it will be provided to the final response generator as context. "
        "Be specific, concrete, and focused. Work only on the current task, using the whole conversation as context. "
        "Treat the latest user message as the primary target of the task, and use the broader chat context only to support or disambiguate it. "
        "Use previously completed tasks only to understand progress and avoid duplication. Assume their conclusions are already known. "
        "Do not restate prior completed-task conclusions, shared diagnosis, or the same retrieved facts unless the current task truly requires a direct contrast. "
        "Add only the new analysis, decision, distinction, tradeoff, or recommendation needed for the current task. "
        "If the current task overlaps earlier tasks, focus only on what remains unresolved or what is uniquely different about this task. "
        "Do not begin by re-summarizing the user's situation, the retrieved context, or previous task outputs. Go straight to the incremental point for this task. "
        "Do not repeat the same recommendation across tasks. Each task output must contribute one distinct incremental insight. "
        "Do not restate the same 'core issue', 'knowledge base alignment', or 'recommended path' sections from earlier tasks. "
        "If those are already established, refer to them implicitly and move straight to the unique decision required by the current task. "
        "Answer the current task itself, not the broader request again. "
        "Treat earlier tasks as resolved inputs, not text to continue or rewrite. The current task should read like a separate pass over the problem with one distinct goal. "
        "If the latest request is a simple factual question, keep the output factual and concise. Do not drift into emotional support, dating advice, therapy framing, or unrelated practical guidance. "
        "Do not write the final user-facing answer, but do write a substantial internal analysis or recommendation for this task. "
        "Keep the output concise: 1 short paragraph or up to 4 compact bullet points. Aim for roughly 60 to 120 words. "
        "End with a short conclusion the final responder can directly use. "
        "Do not mention tools.\n\n"
        f"Current phase: {phase}\n"
        f"Current task: {content}\n\n"
        f"Latest user message (primary target): {last_user_message}\n\n"
        f"Retrieved knowledge-base context for this task:\n{retrieved_context_text}\n\n"
        f"Previously completed tasks for this request:\n{completed_tasks_text}\n\n"
        f"Full context for this task, including any retrieved knowledge-base material:\n{conversation_excerpt}\n\n"
        "Important: if the conversation contains an older unrelated topic, do not analyze or mention it.\n\n"
        f"Variation token: {variation_token}. Let this allow slight wording variance, but keep the output useful and stable.\n\n"
        "Return a full plain-text internal subresponse for this task."
    )

    try:
        started_at = time.time()
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
            max_tokens=1400,
        )
        duration_seconds = time.time() - started_at
        raw_token_count = count_tokens(raw)
        add_generation_metrics(raw_token_count, duration_seconds)
        display_note = raw.strip()
        final_text = strip_to_final_text(raw)
        final_text = final_text.strip() or strip_thinking_tags(raw).strip()
        if final_text:
            return {
                "note": final_text,
                "display_note": display_note,
                "raw_token_count": raw_token_count,
                "duration_seconds": duration_seconds,
            }
    except Exception:
        pass

    if phase == "analyze":
        note = f"The reply should first pin down what the user really wants from {last_user_message[:80]}."
    elif phase == "context":
        note = "The reply should use the most relevant recent context and check whether any important detail is still missing."
    else:
        note = "The reply should balance empathy with directness and decide whether advice or a follow-up question should come first."

    return {
        "note": note,
        "display_note": note,
        "raw_token_count": 0,
        "duration_seconds": 0.0,
    }


def inject_planning_notes(messages: List[Dict[str, str]], completed_tasks: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if not completed_tasks:
        return messages

    enhanced_messages = [dict(message) for message in messages]
    notes_text = "\n\n".join(
        f"Task: {item.get('task', '').strip()}\n"
        f"Task output:\n{item.get('output', '').strip()}"
        for item in completed_tasks
        if item.get('task') and item.get('output')
    )
    for message in enhanced_messages:
        if message.get("role") == "system":
            message["content"] = (
                f"{message.get('content', '')}\n\n"
                "---\n"
                "Completed internal task outputs for this reply:\n"
                f"{notes_text}\n\n"
                "Use these completed task outputs to shape the final answer, but never mention the planning process or the tasks themselves. "
                "Do not copy large blocks of the internal task output verbatim."
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

    recent_messages = _select_recent_conversation(messages, max_messages=3)
    conversation_excerpt = "\n".join(
        f"{msg.get('role', 'user')}: {msg.get('content', '')[:240]}"
        for msg in recent_messages
    )

    primary_prompt = _build_primary_plan_prompt(conversation_excerpt, last_user_message, rag_enabled, variation_token)
    rescue_prompt = _build_rescue_plan_prompt(conversation_excerpt, last_user_message, rag_enabled, variation_token)

    def _attempt_plan(prompt: str, temperature: float, top_p: float) -> tuple[List[Dict[str, Any]], str]:
        raw_output = chat_completion(
            [
                {
                    "role": "system",
                    "content": "You create concise internal execution plans for a chat assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            top_p=top_p,
            max_tokens=1200,
        )
        stripped_output = strip_to_final_text(raw_output)
        print("\n[planner] raw model output:\n" + str(raw_output) + "\n")
        print("[planner] stripped plan output:\n" + stripped_output + "\n")
        parse_source = stripped_output or raw_output
        return _parse_plan_response(parse_source, fallback), raw_output

    def _repair_plan(raw: str) -> List[Dict[str, Any]]:
        repaired_output = chat_completion(
            [
                {
                    "role": "system",
                    "content": "You normalize planner outputs into strict YAML.",
                },
                {"role": "user", "content": _build_repair_prompt(raw)},
            ],
            temperature=0.0,
            top_p=0.4,
            max_tokens=1200,
        )
        repaired = strip_to_final_text(repaired_output)
        print("\n[planner] raw repaired model output:\n" + str(repaired_output) + "\n")
        print("[planner] repaired plan output:\n" + repaired + "\n")
        return _parse_plan_response(repaired or repaired_output, fallback)

    try:
        tasks, raw = _attempt_plan(primary_prompt, 0.3, 0.9)
        if _looks_like_fallback(tasks):
            tasks = _repair_plan(raw)
        if _looks_like_fallback(tasks):
            tasks, raw = _attempt_plan(rescue_prompt, 0.55, 0.95)
        if _looks_like_fallback(tasks):
            tasks = _repair_plan(raw)
        return tasks
    except Exception:
        return fallback
