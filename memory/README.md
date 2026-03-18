# Memory Folder

This directory stores local chat state and memory artifacts.

## Files

### `chat_history.json`

- Stored conversation used by history load/save.
- Reset from the UI via `POST /history/reset`.

### `temp_memory.txt`

- Temporary archive for messages removed from active context.
- Also receives messages during chat reset before history is cleared.

### `long_term/`

- Summarized memory files (`memory_YYYYMMDD_HHMMSS.md`).
- Generated when temp memory reaches configured token threshold.

## Notes

- Token thresholds come from `config.yaml` under `memory`.
- Data in this folder is local to your machine/workspace.
