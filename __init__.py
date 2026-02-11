from __future__ import annotations

import os
from pathlib import Path

from aiohttp import web
from aiohttp.web_request import Request

import folder_paths
import server

# Expose frontend extension JS under /extensions/graviton_bridge/*
WEB_DIRECTORY = "./web"

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

ROOT_DIR = Path(__file__).resolve().parent
LOCAL_TEMPLATES_DIR = ROOT_DIR / "templates"
ENV_TEMPLATE_DIRS = "GRAVITON_TEMPLATE_DIRS"


def _register_template_dir(path: Path, *, is_default: bool = False) -> bool:
    """Register a templates directory with Comfy's folder_paths registry."""
    resolved = path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        return False

    folder_paths.add_model_folder_path("templates", str(resolved), is_default=is_default)
    return True


def _load_initial_template_dirs() -> None:
    # Always register this package's local templates folder.
    LOCAL_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    _register_template_dir(LOCAL_TEMPLATES_DIR)

    # Optionally register additional directories from env (colon-separated).
    raw_value = os.getenv(ENV_TEMPLATE_DIRS, "").strip()
    if not raw_value:
        return

    for raw_path in raw_value.split(os.pathsep):
        trimmed = raw_path.strip()
        if not trimmed:
            continue
        _register_template_dir(Path(trimmed))


def _list_registered_template_paths() -> list[str]:
    try:
        return folder_paths.get_folder_paths("templates")
    except Exception:
        return []


def _safe_templates_in_dir(path: Path) -> list[str]:
    files: list[str] = []
    if not path.exists() or not path.is_dir():
        return files

    for child in sorted(path.iterdir()):
        if not child.is_file():
            continue
        suffix = child.suffix.lower()
        if suffix in {".json", ".flow"}:
            files.append(child.name)
    return files


@server.PromptServer.instance.routes.get("/graviton-bridge/templates/paths")
async def get_template_paths(_request: Request) -> web.Response:
    return web.json_response(
        {
            "paths": _list_registered_template_paths(),
            "local_templates_dir": str(LOCAL_TEMPLATES_DIR),
            "env_var": ENV_TEMPLATE_DIRS,
        }
    )


@server.PromptServer.instance.routes.post("/graviton-bridge/templates/add")
async def add_template_path(request: Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON payload"}, status=400)

    raw_path = (payload.get("path") or "").strip()
    if not raw_path:
        return web.json_response({"error": "Field 'path' is required"}, status=400)

    is_default = bool(payload.get("is_default", False))
    ok = _register_template_dir(Path(raw_path), is_default=is_default)
    if not ok:
        return web.json_response(
            {"error": "Path does not exist or is not a directory", "path": raw_path},
            status=400,
        )

    return web.json_response(
        {
            "ok": True,
            "added": str(Path(raw_path).expanduser().resolve()),
            "paths": _list_registered_template_paths(),
        }
    )


@server.PromptServer.instance.routes.get("/graviton-bridge/templates/files")
async def list_template_files(request: Request) -> web.Response:
    raw_path = (request.query.get("path") or "").strip()
    if raw_path:
        chosen = Path(raw_path).expanduser().resolve()
        if str(chosen) not in _list_registered_template_paths():
            return web.json_response(
                {"error": "Path is not registered in templates", "path": str(chosen)},
                status=400,
            )
        return web.json_response({"path": str(chosen), "files": _safe_templates_in_dir(chosen)})

    result = []
    for p in _list_registered_template_paths():
        path = Path(p)
        result.append({"path": p, "files": _safe_templates_in_dir(path)})

    return web.json_response({"entries": result})


_load_initial_template_dirs()

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
