from __future__ import annotations

import argparse
import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent
DOCKER_DIR = PROJECT_ROOT / ".docker"
GENERATED_CONFIG_PATH = DOCKER_DIR / "config.local.generated.yaml"
GENERATED_COMPOSE_PATH = DOCKER_DIR / "docker-compose.generated.yml"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def get_by_path(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def set_by_path(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = data
    for key in path[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value
    current[path[-1]] = value


def make_container_path(host_path: Path, prefix: str) -> str:
    digest = hashlib.sha1(str(host_path).encode("utf-8")).hexdigest()[:10]
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in host_path.name).strip("_") or "path"
    return f"/{prefix}/{safe_name}_{digest}"


def normalize_host_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    return path.resolve() if path.exists() else path


def register_mount(mounts: dict[Path, str], raw_path: str, prefix: str) -> str:
    host_path = normalize_host_path(raw_path)
    existing = mounts.get(host_path)
    if existing:
        return existing
    container_path = make_container_path(host_path, prefix)
    mounts[host_path] = container_path
    return container_path


def maybe_transform_path(
    merged_config: dict[str, Any],
    generated_config: dict[str, Any],
    path_keys: tuple[str, ...],
    mounts: dict[Path, str],
    prefix: str,
) -> None:
    raw_value = get_by_path(merged_config, path_keys)
    if not isinstance(raw_value, str) or not raw_value:
        return
    normalized_value = raw_value.replace("\\", "/")
    host_path = Path(raw_value).expanduser()
    if not host_path.is_absolute():
        if normalized_value != raw_value:
            set_by_path(generated_config, path_keys, normalized_value)
        return
    container_path = register_mount(mounts, raw_value, prefix)
    set_by_path(generated_config, path_keys, container_path)


def maybe_transform_path_list(
    merged_config: dict[str, Any],
    generated_config: dict[str, Any],
    path_keys: tuple[str, ...],
    mounts: dict[Path, str],
    prefix: str,
) -> None:
    raw_value = get_by_path(merged_config, path_keys)
    if not isinstance(raw_value, list):
        return

    changed = False
    transformed: list[Any] = []
    for item in raw_value:
        if isinstance(item, str) and Path(item).expanduser().is_absolute():
            transformed.append(register_mount(mounts, item, prefix))
            changed = True
        elif isinstance(item, str):
            normalized_item = item.replace("\\", "/")
            transformed.append(normalized_item)
            changed = changed or normalized_item != item
        else:
            transformed.append(item)

    if changed:
        set_by_path(generated_config, path_keys, transformed)


def build_generated_files(enable_gpu: bool) -> tuple[Path, Path]:
    DOCKER_DIR.mkdir(exist_ok=True)

    base_config = load_yaml(PROJECT_ROOT / "config.yaml")
    local_config = load_yaml(PROJECT_ROOT / "config.local.yaml")
    merged_config = deep_merge(base_config, local_config)
    generated_config = deepcopy(local_config)

    backend_mounts: dict[Path, str] = {}
    llm_mounts: dict[Path, str] = {}

    maybe_transform_path_list(merged_config, generated_config, ("rag", "folders_to_index"), backend_mounts, "external/rag")
    maybe_transform_path(merged_config, generated_config, ("rag", "persist_directory"), backend_mounts, "external/chroma")
    maybe_transform_path(merged_config, generated_config, ("rag", "embedding_model"), backend_mounts, "external/models")
    maybe_transform_path(merged_config, generated_config, ("rag", "reranker_model"), backend_mounts, "external/models")
    maybe_transform_path(merged_config, generated_config, ("model", "tokenizer_path"), backend_mounts, "external/models")

    maybe_transform_path(merged_config, generated_config, ("model", "path"), backend_mounts, "external/model")
    maybe_transform_path(merged_config, generated_config, ("model", "path"), llm_mounts, "external/model")

    GENERATED_CONFIG_PATH.write_text(yaml.safe_dump(generated_config, sort_keys=False), encoding="utf-8")

    backend_volumes = ["./.docker/config.local.generated.yaml:/app/config.local.yaml:ro"]
    llm_volumes = ["./.docker/config.local.generated.yaml:/app/config.local.yaml:ro"]

    for host_path, container_path in sorted(backend_mounts.items(), key=lambda item: str(item[0]).lower()):
        backend_volumes.append(f"{host_path}:{container_path}:ro")
    for host_path, container_path in sorted(llm_mounts.items(), key=lambda item: str(item[0]).lower()):
        llm_volumes.append(f"{host_path}:{container_path}:ro")

    compose_data: dict[str, Any] = {
        "services": {
            "backend": {"volumes": backend_volumes},
            "llm_service": {"volumes": llm_volumes},
        }
    }

    if enable_gpu:
        gpu_reservation = {
            "resources": {
                "reservations": {
                    "devices": [
                        {
                            "driver": "nvidia",
                            "count": "all",
                            "capabilities": ["gpu"],
                        }
                    ]
                }
            }
        }
        compose_data["services"]["backend"]["environment"] = {
            "NVIDIA_VISIBLE_DEVICES": "all",
            "NVIDIA_DRIVER_CAPABILITIES": "compute,utility",
        }
        compose_data["services"]["llm_service"]["environment"] = {
            "METIS_LLM_GPU": "cuda",
            "NVIDIA_VISIBLE_DEVICES": "all",
            "NVIDIA_DRIVER_CAPABILITIES": "compute,utility",
        }
        compose_data["services"]["backend"]["deploy"] = gpu_reservation
        compose_data["services"]["llm_service"]["deploy"] = deepcopy(gpu_reservation)

    GENERATED_COMPOSE_PATH.write_text(yaml.safe_dump(compose_data, sort_keys=False), encoding="utf-8")
    return GENERATED_CONFIG_PATH, GENERATED_COMPOSE_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Docker overrides from Metis config files.")
    parser.add_argument("--gpu", action="store_true", help="Request NVIDIA GPU access in the generated Docker Compose override.")
    args = parser.parse_args()

    generated_config, generated_compose = build_generated_files(enable_gpu=args.gpu)
    print(f"Generated Docker config override: {generated_config}")
    print(f"Generated Docker Compose override: {generated_compose}")
    print("Run Docker with:")
    print("  docker compose -f docker-compose.yml -f .docker/docker-compose.generated.yml up --build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
