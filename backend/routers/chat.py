from __future__ import annotations

from typing import List, Optional, Literal, Dict, Any, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.llama_engine import chat_completion, chat_completion_stream, get_config
from backend.agent_planner import build_chat_plan, execute_planning_task, inject_planning_notes
from backend.rag_engine import (
    retrieve_context,
    format_context_for_prompt,
    index_all_folders,
    generate_rag_query,
    generate_rag_queries,
)
from backend.context_manager import trim_messages_to_context

router = APIRouter(prefix="", tags=["chat"])


def _set_task_status(tasks: List[Dict[str, Any]], active_index: int | None) -> List[Dict[str, Any]]:
    updated: List[Dict[str, Any]] = []
    for idx, task in enumerate(tasks):
        new_task = dict(task)
        if active_index is None or idx < active_index:
            new_task["status"] = "completed"
        elif idx == active_index:
            new_task["status"] = "in_progress"
        else:
            new_task["status"] = "pending"
        updated.append(new_task)
    return updated


def _apply_rag_context(messages: List[Message], rag_cfg: Dict[str, Any]) -> List[Message]:
    global _last_rag_results

    if not rag_cfg.get("enabled", False):
        return messages

    user_messages = [m for m in messages if m.role == "user"]
    if not user_messages:
        return messages

    last_user_query = user_messages[-1].content
    messages_for_query = [{"role": m.role, "content": m.content} for m in messages]
    rag_queries = generate_rag_queries(messages_for_query, last_user_query)

    _last_rag_results = {
        "queries": rag_queries,
        "original_query": last_user_query,
        "results": []
    }

    combined_contexts: List[Dict[str, Any]] = []
    seen = set()
    per_query_results: List[Dict[str, Any]] = []
    for q in rag_queries:
        try:
            results = retrieve_context(q)
        except Exception:
            results = {"accepted": [], "overflow": [], "rejected_by_distance": [], "rejected_by_score": []}

        if not isinstance(results, dict):
            results = {"accepted": [], "overflow": [], "rejected_by_distance": [], "rejected_by_score": []}

        rejected_distance = results.get("rejected_by_distance", []) or []
        rejected_score = results.get("rejected_by_score", []) or []
        overflow = results.get("overflow", []) or []
        per_query_results.append({
            "query": q,
            "accepted": results.get("accepted", []),
            "overflow": overflow,
            "rejected": rejected_distance + rejected_score,
        })

    combined_accepted: List[Dict[str, Any]] = []
    seen = set()
    for bucket in per_query_results:
        for ctx in bucket["accepted"]:
            md = ctx.get("metadata", {})
            src = md.get("source_file")
            idx = md.get("chunk_index")
            key = (None, ctx.get("text", "")[:160]) if src is None or idx is None else (src, idx)
            if key in seen:
                continue
            seen.add(key)
            combined_accepted.append(ctx)

    reranker_top_k = rag_cfg.get("reranker_top_k", 2)
    max_capacity = len(rag_queries) * reranker_top_k
    current_count = len(combined_accepted)

    print(f"\n   📊 [Capacity Check] Current: {current_count}, Max: {max_capacity}, Need: {max_capacity - current_count}")
    for i, bucket in enumerate(per_query_results):
        overflow_count = len(bucket.get("overflow", []))
        print(f"      Query {i+1} overflow: {overflow_count} chunks")

    if current_count < max_capacity:
        overflow_pool: List[Tuple[Dict[str, Any], Any]] = []
        for bucket in per_query_results:
            for ctx in bucket.get("overflow", []):
                md = ctx.get("metadata", {})
                src = md.get("source_file")
                idx = md.get("chunk_index")
                key = (None, ctx.get("text", "")[:160]) if src is None or idx is None else (src, idx)

                if key not in seen:
                    overflow_pool.append((ctx, key))
                else:
                    print(f"      [Dedup] Overflow chunk already in accepted: {src}")

        print(f"      Total overflow pool (after dedup): {len(overflow_pool)} chunks")
        overflow_pool.sort(key=lambda x: float(x[0].get("rerank_score", 0)), reverse=True)

        slots_available = max_capacity - current_count
        added_count = 0
        for ctx, key in overflow_pool[:slots_available]:
            if "rejection_reason" in ctx:
                del ctx["rejection_reason"]
            seen.add(key)
            combined_accepted.append(ctx)
            added_count += 1

        if added_count > 0:
            print(f"   🔄 [Overflow Fill] Added {added_count} overflow chunks to reach {len(combined_accepted)}/{max_capacity} capacity")
        else:
            print(f"   ⚠️ [Overflow Fill] No overflow chunks available to fill")

    combined_rejected: List[Dict[str, Any]] = []
    for bucket in per_query_results:
        for ctx in bucket["rejected"]:
            md = ctx.get("metadata", {})
            src = md.get("source_file")
            idx = md.get("chunk_index")
            key = (None, ctx.get("text", "")[:160]) if src is None or idx is None else (src, idx)

            if key in seen:
                continue
            seen.add(key)
            if "rejection_reason" not in ctx:
                ctx["rejection_reason"] = "distance"
            combined_rejected.append(ctx)

    combined_contexts = combined_accepted + combined_rejected
    contexts = combined_contexts
    relevant_contexts = [c for c in contexts if "rejection_reason" not in c]

    accepted_list = [c for c in combined_contexts if "rejection_reason" not in c]
    rejected_list = [c for c in combined_contexts if "rejection_reason" in c]

    for bucket in per_query_results:
        acc = bucket.get("accepted", [])
        rej = bucket.get("rejected", [])
        if any(x.get("rerank_score") is not None for x in acc):
            acc.sort(key=lambda x: float(x.get("rerank_score") or -1e9), reverse=True)
        else:
            acc.sort(key=lambda x: float(x.get("distance", 0)))
        rej.sort(key=lambda x: float(x.get("distance", 0)))
        bucket["accepted"] = acc
        bucket["rejected"] = rej

    if any(x.get("rerank_score") is not None for x in accepted_list):
        accepted_list.sort(key=lambda x: float(x.get("rerank_score") or -1e9), reverse=True)
    else:
        accepted_list.sort(key=lambda x: float(x.get("distance", 0)))

    rejected_list.sort(key=lambda x: float(x.get("distance", 0)))

    results_list = []
    for ctx in accepted_list + rejected_list:
        md = ctx.get("metadata", {})
        is_used = "rejection_reason" not in ctx
        full_text = ctx.get("text", "")
        item = {
            "source_file": md.get("source_file", "unknown"),
            "distance": ctx.get("distance", 0),
            "rerank_score": ctx.get("rerank_score"),
            "text_preview": full_text[:200],
            "text": full_text,
            "chunk_index": md.get("chunk_index", 0),
            "used": is_used,
        }
        if not is_used:
            item["rejection_reason"] = ctx.get("rejection_reason")
        results_list.append(item)

    _last_rag_results = {
        "queries": rag_queries,
        "original_query": last_user_query,
        "per_query_results": per_query_results,
        "results": results_list,
    }

    if relevant_contexts:
        context_text = format_context_for_prompt(relevant_contexts)
        for i, msg in enumerate(messages):
            if msg.role == "system":
                enhanced_system = f"{msg.content}\n\n---\nRelevant information from your knowledge base:\n\n{context_text}\n\nUse this information to answer the user's question."
                messages[i] = Message(role="system", content=enhanced_system)
                break
    elif not contexts:
        _last_rag_results = {
            "queries": rag_queries,
            "original_query": last_user_query,
            "results": []
        }

    return messages

# Store last RAG retrieval results
_last_rag_results: Dict[str, Any] = {"results": []}

# Store current chat context (replaces on each request)
_current_context: List[Dict[str, Any]] = []


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: Optional[List[Message]] = Field(
        default=None, description="OpenAI-style chat messages array"
    )
    prompt: Optional[str] = Field(
        default=None, description="Simple prompt; used if messages not provided"
    )
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if (not req.messages or len(req.messages) == 0) and (not req.prompt):
        raise HTTPException(status_code=400, detail="Provide `messages` or `prompt`.")

    config = get_config()
    chat_cfg = config["chat"]
    system_prompt = chat_cfg.get("system_prompt", "You are Metis, a helpful AI assistant.")

    messages: List[Message]
    if req.messages and len(req.messages) > 0:
        # Prepend system prompt if not already present
        if not any(m.role == "system" for m in req.messages):
            messages = [Message(role="system", content=system_prompt)] + req.messages
        else:
            messages = req.messages
    else:
        # Build minimal chat with system prompt from config
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=req.prompt or ""),
        ]

    # Use request params or fall back to config defaults
    temperature = req.temperature if req.temperature is not None else chat_cfg.get("temperature", 0.7)
    top_p = req.top_p if req.top_p is not None else chat_cfg.get("top_p", 0.95)
    max_tokens = req.max_tokens if req.max_tokens is not None else chat_cfg.get("max_tokens", 512)

    # Trim messages to fit within context limit
    messages_dict = [m.model_dump() for m in messages]
    messages_dict = trim_messages_to_context(messages_dict)

    reply = chat_completion(
        messages_dict,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )
    return ChatResponse(reply=reply)


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """
    Streaming version of /chat endpoint. Returns newline-delimited JSON chunks.
    Each line is a JSON object: {"delta": "token text"} or {"done": true}
    """
    if (not req.messages or len(req.messages) == 0) and (not req.prompt):
        raise HTTPException(status_code=400, detail="Provide `messages` or `prompt`.")

    config = get_config()
    chat_cfg = config["chat"]
    rag_cfg = config.get("rag", {})
    system_prompt = chat_cfg.get("system_prompt", "You are Metis, a helpful AI assistant.")

    messages: List[Message]
    if req.messages and len(req.messages) > 0:
        # Prepend system prompt if not already present
        if not any(m.role == "system" for m in req.messages):
            messages = [Message(role="system", content=system_prompt)] + req.messages
        else:
            messages = req.messages
    else:
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=req.prompt or ""),
        ]

    # Use request params or fall back to config defaults
    temperature = req.temperature if req.temperature is not None else chat_cfg.get("temperature", 0.7)
    top_p = req.top_p if req.top_p is not None else chat_cfg.get("top_p", 0.95)
    max_tokens = req.max_tokens if req.max_tokens is not None else chat_cfg.get("max_tokens", 512)

    global _current_context
    import datetime
    timestamp = datetime.datetime.now().isoformat()

    def generate():
        import json
        import time
        
        global _current_context
        local_messages = list(messages)
        latest_user_message = next((m.content for m in reversed(local_messages) if m.role == "user"), req.prompt or "")
        planner_messages = [{"role": m.role, "content": m.content} for m in local_messages]
        plan_tasks = build_chat_plan(planner_messages, latest_user_message, bool(rag_cfg.get("enabled", False)))
        plan_tasks = _set_task_status(plan_tasks, 0)
        yield json.dumps({"type": "task_snapshot", "tasks": plan_tasks}) + "\n"

        local_messages = _apply_rag_context(local_messages, rag_cfg)

        local_messages_dict = [m.model_dump() for m in local_messages]
        local_messages_dict = trim_messages_to_context(local_messages_dict)

        planning_notes: List[str] = []
        last_task_index = len(plan_tasks) - 1
        for idx, task in enumerate(plan_tasks):
            active_tasks = _set_task_status(plan_tasks, idx)
            yield json.dumps({"type": "task_snapshot", "tasks": active_tasks}) + "\n"
            note = execute_planning_task(local_messages_dict, task, planning_notes, latest_user_message)
            if note:
                planning_notes.append(note)
                yield json.dumps({
                    "type": "task_note",
                    "task_id": task.get("id"),
                    "task_content": task.get("content"),
                    "note": note,
                }) + "\n"
            if idx < last_task_index:
                completed_tasks = _set_task_status(plan_tasks, idx + 1)
                yield json.dumps({"type": "task_snapshot", "tasks": completed_tasks}) + "\n"

        local_messages_dict = inject_planning_notes(local_messages_dict, planning_notes)
        local_messages_dict = trim_messages_to_context(local_messages_dict)

        start_time = time.time()
        token_count = 0
        assistant_response = ""
        
        _current_context = [
            {
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": timestamp
            }
            for msg in local_messages_dict
        ]

        for token in chat_completion_stream(
            local_messages_dict,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        ):
            token_count += 1
            assistant_response += token
            # Send each token as NDJSON (newline-delimited JSON)
            yield json.dumps({"type": "delta", "delta": token}) + "\n"
        
        # Calculate tokens per second
        elapsed = time.time() - start_time
        tokens_per_second = token_count / elapsed if elapsed > 0 else 0
        
        # Update context with assistant response
        _current_context.append({
            "role": "assistant",
            "content": assistant_response,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        # Final chunk with performance stats and trimmed message count
        final_chunk = {
            "type": "done",
            "done": True,
            "tokens_per_second": round(tokens_per_second, 2),
            "tasks": _set_task_status(plan_tasks, None),
            "trimmed_messages": [
                {"role": msg["role"], "content": msg["content"]}
                for msg in local_messages_dict
            ]
        }
        yield json.dumps(final_chunk) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/rag/reindex")
def reindex_knowledge_base(clear_existing: bool = True):
    """
    Trigger re-indexing of all folders specified in config.yaml.
    
    - clear_existing: if True, removes old chunks before re-indexing
    """
    try:
        results = index_all_folders(clear_existing=clear_existing)
        total = sum(results.values())
        return {
            "status": "success",
            "total_chunks": total,
            "folders": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/rag/stats")
def get_rag_stats():
    """Get RAG system statistics."""
    try:
        from backend.rag_engine import get_collection, get_file_metadata_path
        import json
        
        config = get_config()
        rag_cfg = config.get("rag", {})
        
        collection = get_collection()
        total_chunks = collection.count()
        
        # Count unique files from metadata
        metadata_path = get_file_metadata_path()
        total_files = 0
        if metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                file_metadata = json.load(f)
                total_files = len(file_metadata)
        
        return {
            "total_chunks": total_chunks,
            "total_files": total_files,
            "collection_name": rag_cfg.get("collection_name", "metis_knowledge"),
            "enabled": rag_cfg.get("enabled", False)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/rag/clear")
def clear_rag_database():
    """Clear all embeddings from the RAG database."""
    try:
        from backend.rag_engine import get_collection, get_file_metadata_path, save_file_metadata
        
        collection = get_collection()
        count_before = collection.count()
        
        # Delete all items in the collection
        if count_before > 0:
            all_items = collection.get()
            if all_items and all_items.get("ids"):
                collection.delete(ids=all_items["ids"])
        
        # Clear file metadata
        save_file_metadata({})
        
        return {
            "status": "success",
            "deleted_count": count_before
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clear failed: {str(e)}")


@router.get("/rag/last-retrieval")
def get_last_rag_retrieval():
    """Get the last RAG retrieval results."""
    global _last_rag_results
    return {
        "results": _last_rag_results
    }


@router.get("/chat/history")
def get_chat_history():
    """Get the current chat context (legacy endpoint - use /chat/context instead)."""
    global _current_context
    return {
        "messages": _current_context
    }


@router.get("/chat/context")
def get_chat_context():
    """Get the current chat context."""
    global _current_context
    return {
        "messages": _current_context
    }
