"""
Simple context management to keep messages within n_ctx limit.
Removes older messages when context is too long.
"""
from typing import List, Dict, Any
from backend.llama_engine import get_config
from backend.token_utils import estimate_token_count, count_message_tokens


def trim_messages_to_context(messages: List[Dict[str, str]], max_tokens: int = None) -> List[Dict[str, str]]:
    """
    Trim messages to fit within context limit.
    Always keeps the system message (first) and removes oldest user/assistant pairs.
    
    Args:
        messages: List of message dicts with role and content
        max_tokens: Maximum tokens allowed (defaults to n_ctx from config - 512 for response)
    
    Returns:
        Trimmed list of messages that fits within context
    """
    if max_tokens is None:
        config = get_config()
        n_ctx = config.get("model", {}).get("n_ctx", 8192)
        # Reserve space for response
        response_reserve = config.get("chat", {}).get("max_tokens", 512)
        max_tokens = n_ctx - response_reserve
    
    if not messages:
        return messages
    
    # Calculate current token count
    current_tokens = count_message_tokens(messages)
    
    # If we're under the limit, return as-is
    if current_tokens <= max_tokens:
        return messages
    
    # Always keep system message (first message)
    system_msg = None
    other_messages = messages
    
    if messages[0].get("role") == "system":
        system_msg = messages[0]
        other_messages = messages[1:]
    
    # Always preserve the latest non-system message, which is typically the current user turn.
    preserved_tail = other_messages[-1:] if other_messages else []
    candidate_messages = other_messages[:-1] if len(other_messages) > 1 else []
    trimmed_messages = candidate_messages[:]

    while trimmed_messages and count_message_tokens([system_msg] + trimmed_messages + preserved_tail if system_msg else trimmed_messages + preserved_tail) > max_tokens:
        trimmed_messages.pop(0)

    trimmed_messages = trimmed_messages + preserved_tail
    
    # Reconstruct with system message first
    if system_msg:
        result = [system_msg] + trimmed_messages
    else:
        result = trimmed_messages
    
    # Log the trimming action
    removed_count = len(messages) - len(result)
    if removed_count > 0:
        print(f"Context trimmed: removed {removed_count} oldest message(s) to stay within {max_tokens} token limit")
        print(f"  Before: {current_tokens} tokens ({len(messages)} messages)")
        print(f"  After: {count_message_tokens(result)} tokens ({len(result)} messages)")
    
    return result
