from __future__ import annotations

import os

from .constants import LOCAL_TEMPLATES_DIR, WEB_DIRECTORY
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Register routes via side-effect imports.
from . import asset_routes as _asset_routes  # noqa: F401
from . import config_routes as _config_routes  # noqa: F401
from . import template_routes as _template_routes  # noqa: F401


def _load_local_env() -> None:
    env_path = LOCAL_TEMPLATES_DIR.parent / ".env"
    if not env_path.exists() or not env_path.is_file():
        return

    try:
        raw = env_path.read_text(encoding="utf-8")
    except Exception:
        return

    for line in raw.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_local_env()
LOCAL_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
