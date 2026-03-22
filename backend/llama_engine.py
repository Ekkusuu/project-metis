from __future__ import annotations

import os
import json
import yaml
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from pathlib import Path
from typing import List, Dict, Optional, Iterator, Any, cast

# Global configuration
_config: Optional[Dict[str, Any]] = None

# Default paths
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"
LOCAL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.local.yaml"


def _deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override into base and return merged dict."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml with fallback defaults."""
    global _config
    if _config is not None:
        return _config

    default_config = {
        "model": {
            "path": "model/psychologistv2-8.0B-Q4_0.gguf",
            "n_ctx": 8192,
            "n_gpu_layers": -1,
        },
        "chat": {
            "system_prompt": "You are Metis, a helpful AI assistant.",
            "temperature": 0.7,
            "top_p": 0.95,
            "max_tokens": 512,
        },
        "llm_service": {
            "host": "localhost",
            "port": 3000,
        },
    }

    loaded_cfg: Dict[str, Any] = {}

    current_config: Dict[str, Any]

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            if isinstance(raw, dict):
                loaded_cfg = raw
            # Merge with defaults for any missing keys
            current_config = _deep_merge_dicts(default_config, loaded_cfg)
        except Exception as e:
            print(f"Warning: Failed to load config.yaml: {e}. Using defaults.")
            current_config = default_config
    else:
        current_config = default_config

    # Optional local overrides (ignored by git), useful for machine-specific paths
    if LOCAL_CONFIG_PATH.exists():
        try:
            with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8") as f:
                local_cfg = yaml.safe_load(f) or {}
            if isinstance(local_cfg, dict):
                current_config = _deep_merge_dicts(current_config, local_cfg)
        except Exception as e:
            print(f"Warning: Failed to load config.local.yaml: {e}. Continuing without local overrides.")

    _config = current_config

    return cast(Dict[str, Any], _config)


def get_config() -> Dict[str, Any]:
    """Get the loaded configuration."""
    return load_config()


def get_llm_service_url() -> str:
    """Get the LLM service base URL from config."""
    config = get_config()
    llm_cfg = config.get("llm_service", {})
    host = os.getenv("METIS_LLM_SERVICE_HOST", llm_cfg.get("host", "localhost"))
    port = int(os.getenv("METIS_LLM_SERVICE_PORT", str(llm_cfg.get("port", 3000))))
    return f"http://{host}:{port}"


# Reuse a single HTTP session for all LLM service requests to improve
# performance by keeping connections alive and reusing the pool.
_http_session: Optional[requests.Session] = None


def get_http_session() -> requests.Session:
    global _http_session
    if _http_session is not None:
        return _http_session

    session = requests.Session()
    # Configure a sensible HTTPAdapter with retries and a larger pool
    retries = Retry(total=3, backoff_factor=0.2, status_forcelist=(502, 503, 504))
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Keep default headers for keep-alive
    session.headers.update({"Connection": "keep-alive"})

    _http_session = session
    return _http_session


def get_model() -> bool:
    """
    Check if the LLM service is available.
    Returns True if service is reachable, False otherwise.
    """
    try:
        url = f"{get_llm_service_url()}/health"
        session = get_http_session()
        response = session.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("model_loaded", False)
        return False
    except Exception as e:
        print(f"Warning: LLM service not reachable: {e}")
        return False


def chat_completion(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    top_p: float = 0.95,
    max_tokens: int = 512,
) -> str:
    """
    Run a chat completion using the Node.js LLM service.
    Returns the assistant reply content as a string.
    """
    try:
        url = f"{get_llm_service_url()}/chat/completion"
        payload = {
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }

        session = get_http_session()
        response = session.post(url, json=payload, timeout=120)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # Handle both string and dict responses
        if isinstance(content, dict):
            # Extract the actual response text from the dict
            if "response" in content:
                content = content["response"]
            elif "text" in content:
                content = content["text"]
            else:
                # Fallback: convert to string
                content = str(content)
        
        return content.strip() if isinstance(content, str) else str(content).strip()
    except Exception as e:
        print(f"LLM service error: {e}")
        raise RuntimeError(f"LLM service error: {e}")


def chat_completion_stream(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    top_p: float = 0.95,
    max_tokens: int = 512,
) -> Iterator[str]:
    """
    Stream chat completion tokens using the Node.js LLM service.
    Yields delta content strings (individual tokens or partial text).
    """
    try:
        url = f"{get_llm_service_url()}/chat/stream"
        payload = {
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }

        session = get_http_session()
        response = session.post(url, json=payload, stream=True, timeout=120)
        response.raise_for_status()

        # Read NDJSON stream line by line
        for line in response.iter_lines(decode_unicode=True):
            if line:
                try:
                    chunk = json.loads(line)
                    # Only yield delta content, skip done signals
                    if "delta" in chunk and chunk["delta"]:
                        yield chunk["delta"]
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        raise RuntimeError(f"LLM service streaming error: {e}")

