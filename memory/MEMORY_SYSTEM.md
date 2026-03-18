# Memory System Architecture

## Overview

The memory system preserves useful conversation information when active chat context gets trimmed or when chat is reset.

## Core Pieces

- `backend/context_manager.py`
  - Trims oldest messages when token limit is exceeded.
  - Sends removed messages to temp memory.

- `backend/memory_manager.py`
  - Appends removed/reset conversation text to `temp_memory.txt`.
  - Triggers summarization when temp memory token threshold is reached.
  - Writes summaries into `memory/long_term/` and clears temp memory.

- `backend/routers/history.py`
  - Loads/saves chat history.
  - On reset, archives conversation before clearing visible history.

- `backend/routers/memory.py`
  - Exposes memory status.
  - Supports manual summarization trigger.

## Flow

```text
Chat grows -> context limit reached -> old messages trimmed
-> append to temp_memory.txt -> threshold reached
-> summarize -> write to long_term/*.md -> clear temp memory
```

## Config

- `memory.temp_memory_token_limit`
- `memory.long_term_memory_token_limit`

Both are set in `config.yaml`.
