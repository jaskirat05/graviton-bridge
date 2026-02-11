from __future__ import annotations

from pathlib import Path
from typing import Optional

from aiohttp import web
from aiohttp.web_request import Request

import server

# Expose frontend extension JS under /extensions/graviton_bridge/*
WEB_DIRECTORY = "./web"

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

ROOT_DIR = Path(__file__).resolve().parent
LOCAL_TEMPLATES_DIR = ROOT_DIR / "templates"
ALLOWED_TEMPLATE_SUFFIXES = {".json", ".flow"}


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


def _sanitize_template_filename(raw_name: str) -> Optional[str]:
    """Validate and sanitize uploaded/downloaded template filename."""
    filename = Path((raw_name or "").strip()).name
    if not filename:
        return None
    if filename in {".", ".."}:
        return None
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_TEMPLATE_SUFFIXES:
        return None
    return filename


def _resolve_local_template_file(raw_name: str) -> Optional[Path]:
    filename = _sanitize_template_filename(raw_name)
    if not filename:
        return None
    target = (LOCAL_TEMPLATES_DIR / filename).resolve()
    if LOCAL_TEMPLATES_DIR.resolve() not in target.parents:
        return None
    return target


@server.PromptServer.instance.routes.get("/graviton-bridge/templates")
async def list_local_templates(_request: Request) -> web.Response:
    """List files hosted by graviton_bridge itself."""
    LOCAL_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for name in _safe_templates_in_dir(LOCAL_TEMPLATES_DIR):
        p = LOCAL_TEMPLATES_DIR / name
        stat = p.stat()
        files.append(
            {
                "filename": name,
                "size_bytes": stat.st_size,
                "modified_at": int(stat.st_mtime),
            }
        )

    return web.json_response(
        {
            "path": str(LOCAL_TEMPLATES_DIR.resolve()),
            "count": len(files),
            "files": files,
        }
    )


@server.PromptServer.instance.routes.get("/graviton-bridge/templates/download/{filename}")
async def download_local_template(request: Request) -> web.StreamResponse:
    """Download a template file from this custom node's local templates dir."""
    target = _resolve_local_template_file(request.match_info.get("filename", ""))
    if target is None:
        return web.json_response({"error": "Invalid filename"}, status=400)
    if not target.exists() or not target.is_file():
        return web.json_response({"error": "Template file not found"}, status=404)
    return web.FileResponse(
        path=target,
        headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
    )


@server.PromptServer.instance.routes.post("/graviton-bridge/templates/upload")
async def upload_local_template(request: Request) -> web.Response:
    """
    Upload template to this custom node's local templates dir.

    Supports:
    - multipart/form-data with field "file"
    - JSON body { "filename": "...", "content": "..." }
    """
    LOCAL_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    filename = ""
    content: bytes

    if request.content_type.startswith("multipart/"):
        reader = await request.multipart()
        part = await reader.next()
        if part is None or part.name != "file":
            return web.json_response(
                {"error": "Expected multipart field named 'file'"},
                status=400,
            )
        filename = part.filename or ""
        content = await part.read(decode=False)
    else:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid request body"}, status=400)
        filename = payload.get("filename", "")
        text_content = payload.get("content")
        if not isinstance(text_content, str):
            return web.json_response(
                {"error": "JSON body must include string field 'content'"},
                status=400,
            )
        content = text_content.encode("utf-8")

    target = _resolve_local_template_file(filename)
    if target is None:
        return web.json_response(
            {"error": "Invalid filename. Allowed extensions: .json, .flow"},
            status=400,
        )

    target.write_bytes(content)
    return web.json_response(
        {
            "ok": True,
            "filename": target.name,
            "path": str(target),
            "size_bytes": len(content),
        }
    )

LOCAL_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
