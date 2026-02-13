from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import ROOT_DIR

CONFIG_PATH = ROOT_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "local",
}


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


def load_effective_config() -> dict[str, Any]:
    loaded = _read_file_config()
    if not loaded:
        return dict(DEFAULT_CONFIG)
    mode = str(loaded.get("mode", DEFAULT_CONFIG["mode"])).strip().lower()
    return {"mode": mode or DEFAULT_CONFIG["mode"]}


def validate_config(config: dict[str, Any]) -> None:
    mode = str(config.get("mode", "local")).strip().lower()
    if mode not in {"local", "orchestrator", "s3", "cloudinary"}:
        raise ValueError("mode must be one of: local, orchestrator, s3, cloudinary")


def save_file_config(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    mode = str(config.get("mode", DEFAULT_CONFIG["mode"])).strip().lower()
    saved = {"mode": mode}
    CONFIG_PATH.write_text(json.dumps(saved, indent=2, sort_keys=True), encoding="utf-8")
    return saved
