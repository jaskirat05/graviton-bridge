from __future__ import annotations

import json
import os
from typing import Any

from .constants import ROOT_DIR

CONFIG_PATH = ROOT_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "local",
    "config_version": "",
    "orchestrator": {
        "base_url": "",
        "token": "",
    },
    "s3": {
        "bucket": "",
        "region": "",
        "prefix": "",
        "access_key": "",
        "secret_key": "",
    },
    "cloudinary": {
        "cloud_name": "",
        "api_key": "",
        "api_secret": "",
        "folder": "",
    },
}

_SECRET_FIELDS = {
    ("orchestrator", "token"),
    ("s3", "access_key"),
    ("s3", "secret_key"),
    ("cloudinary", "api_key"),
    ("cloudinary", "api_secret"),
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


def _normalize_mode(value: Any) -> str:
    return str(value or "local").strip().lower() or "local"


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_section(value: Any, defaults: dict[str, Any]) -> dict[str, str]:
    src = value if isinstance(value, dict) else {}
    out: dict[str, str] = {}
    for key, default in defaults.items():
        out[key] = _normalize_string(src.get(key, default))
    return out


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    mode = _normalize_mode(config.get("mode", DEFAULT_CONFIG["mode"]))
    config_version = _normalize_string(config.get("config_version", DEFAULT_CONFIG["config_version"]))

    normalized = {
        "mode": mode,
        "config_version": config_version,
        "orchestrator": _normalize_section(config.get("orchestrator"), DEFAULT_CONFIG["orchestrator"]),
        "s3": _normalize_section(config.get("s3"), DEFAULT_CONFIG["s3"]),
        "cloudinary": _normalize_section(config.get("cloudinary"), DEFAULT_CONFIG["cloudinary"]),
    }
    return normalized


def _env_config() -> dict[str, Any]:
    return normalize_config(
        {
            "mode": os.getenv("GRAVITON_BRIDGE_MODE", DEFAULT_CONFIG["mode"]),
            "config_version": os.getenv("GRAVITON_BRIDGE_CONFIG_VERSION", DEFAULT_CONFIG["config_version"]),
            "orchestrator": {
                "base_url": os.getenv("GRAVITON_ORCHESTRATOR_BASE_URL", ""),
                "token": os.getenv("GRAVITON_ORCHESTRATOR_TOKEN", ""),
            },
            "s3": {
                "bucket": os.getenv("GRAVITON_S3_BUCKET", ""),
                "region": os.getenv("GRAVITON_S3_REGION", ""),
                "prefix": os.getenv("GRAVITON_S3_PREFIX", ""),
                "access_key": os.getenv("GRAVITON_S3_ACCESS_KEY", ""),
                "secret_key": os.getenv("GRAVITON_S3_SECRET_KEY", ""),
            },
            "cloudinary": {
                "cloud_name": os.getenv("GRAVITON_CLOUDINARY_CLOUD_NAME", ""),
                "api_key": os.getenv("GRAVITON_CLOUDINARY_API_KEY", ""),
                "api_secret": os.getenv("GRAVITON_CLOUDINARY_API_SECRET", ""),
                "folder": os.getenv("GRAVITON_CLOUDINARY_FOLDER", ""),
            },
        }
    )


def load_effective_config() -> dict[str, Any]:
    loaded = _read_file_config()
    if loaded:
        # Config file exists: use config only.
        merged = normalize_config(
            {
                "mode": loaded.get("mode", DEFAULT_CONFIG["mode"]),
                "config_version": loaded.get("config_version", DEFAULT_CONFIG["config_version"]),
                "orchestrator": {
                    **DEFAULT_CONFIG["orchestrator"],
                    **(loaded.get("orchestrator") if isinstance(loaded.get("orchestrator"), dict) else {}),
                },
                "s3": {
                    **DEFAULT_CONFIG["s3"],
                    **(loaded.get("s3") if isinstance(loaded.get("s3"), dict) else {}),
                },
                "cloudinary": {
                    **DEFAULT_CONFIG["cloudinary"],
                    **(loaded.get("cloudinary") if isinstance(loaded.get("cloudinary"), dict) else {}),
                },
            }
        )
        return merged

    # No config file: fall back to environment.
    return _env_config()


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(config))
    for section, field in _SECRET_FIELDS:
        section_obj = redacted.get(section)
        if isinstance(section_obj, dict) and section_obj.get(field):
            section_obj[field] = "***"
    return redacted


def validate_config(config: dict[str, Any]) -> None:
    mode = _normalize_mode(config.get("mode", "local"))
    if mode not in {"local", "orchestrator", "s3", "cloudinary"}:
        raise ValueError("mode must be one of: local, orchestrator, s3, cloudinary")


def save_file_config(config: dict[str, Any]) -> dict[str, Any]:
    # Merge incoming with FILE config only (never env fallback values).
    file_current_raw = _read_file_config()
    file_current = normalize_config(file_current_raw) if file_current_raw else normalize_config(DEFAULT_CONFIG)

    merged = {
        "mode": config.get("mode", file_current["mode"]),
        "config_version": config.get("config_version", file_current["config_version"]),
        "orchestrator": {
            **file_current["orchestrator"],
            **(config.get("orchestrator") if isinstance(config.get("orchestrator"), dict) else {}),
        },
        "s3": {
            **file_current["s3"],
            **(config.get("s3") if isinstance(config.get("s3"), dict) else {}),
        },
        "cloudinary": {
            **file_current["cloudinary"],
            **(config.get("cloudinary") if isinstance(config.get("cloudinary"), dict) else {}),
        },
    }

    normalized = normalize_config(merged)
    validate_config(normalized)

    CONFIG_PATH.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")
    return normalized
