from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import ROOT_DIR

CONFIG_PATH = ROOT_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "local",
    "orchestrator": {
        "base_url": "",
        "token": "",
    },
    "storage": {
        "provider": "local",
        "bucket": "",
        "prefix": "",
        "endpoint": "",
        "region": "",
        "access_key": "",
        "secret_key": "",
        "session_token": "",
    },
}

_SECRET_KEYS = {"token", "access_key", "secret_key", "session_token"}


def _read_file_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    return {}


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _mask_secrets(data: Any) -> Any:
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if key in _SECRET_KEYS and isinstance(value, str) and value:
                out[key] = "***"
            else:
                out[key] = _mask_secrets(value)
        return out
    if isinstance(data, list):
        return [_mask_secrets(v) for v in data]
    return data


def load_effective_config() -> dict[str, Any]:
    loaded = _read_file_config()
    return _deep_merge(DEFAULT_CONFIG, loaded) if loaded else dict(DEFAULT_CONFIG)


def validate_config(config: dict[str, Any]) -> None:
    mode = str(config.get("mode", "local")).strip().lower()
    if mode not in {"local", "orchestrator", "s3", "cloudinary"}:
        raise ValueError("mode must be one of: local, orchestrator, s3, cloudinary")


def save_file_config(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return config


def apply_config_patch(patch: dict[str, Any]) -> dict[str, Any]:
    current = load_effective_config()
    merged = _deep_merge(current, patch)
    return save_file_config(merged)


def sanitize_for_response(config: dict[str, Any]) -> dict[str, Any]:
    return _mask_secrets(config)
