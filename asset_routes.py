from __future__ import annotations

from aiohttp import web
from aiohttp.web_request import Request

import server

from .provider_router import get_asset_provider


@server.PromptServer.instance.routes.get("/graviton-bridge/assets")
async def list_assets(_request: Request) -> web.Response:
    provider = get_asset_provider()
    assets = [a.to_dict() for a in provider.list_assets()]
    return web.json_response({"count": len(assets), "assets": assets})


@server.PromptServer.instance.routes.get("/graviton-bridge/assets/{asset_id}/meta")
async def get_asset_meta(request: Request) -> web.Response:
    asset_id = request.match_info.get("asset_id", "")
    provider = get_asset_provider()
    meta = provider.get_meta(asset_id)
    if not meta:
        return web.json_response({"error": "Asset not found"}, status=404)
    return web.json_response(meta.to_dict())


@server.PromptServer.instance.routes.get("/graviton-bridge/assets/{asset_id}")
async def get_asset_bytes(request: Request) -> web.StreamResponse:
    asset_id = request.match_info.get("asset_id", "")
    provider = get_asset_provider()
    meta = provider.get_meta(asset_id)
    if not meta:
        return web.json_response({"error": "Asset not found"}, status=404)

    blob_path = provider.resolve_local_path(asset_id)
    if blob_path is None:
        return web.json_response({"error": "Asset payload missing"}, status=404)

    filename = meta.filename or blob_path.name
    mime_type = meta.mime_type or "application/octet-stream"
    return web.FileResponse(
        path=blob_path,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": str(mime_type),
        },
    )


@server.PromptServer.instance.routes.post("/graviton-bridge/assets/upload")
async def upload_asset(request: Request) -> web.Response:
    kind = request.query.get("kind", "file").strip() or "file"
    if not request.content_type.startswith("multipart/"):
        return web.json_response(
            {"error": "Expected multipart/form-data with field 'file'"},
            status=400,
        )

    reader = await request.multipart()
    part = await reader.next()
    if part is None or part.name != "file":
        return web.json_response({"error": "Missing multipart field 'file'"}, status=400)

    filename = (part.filename or "upload.bin").strip() or "upload.bin"
    payload = await part.read(decode=False)
    if not payload:
        return web.json_response({"error": "Uploaded file is empty"}, status=400)

    provider = get_asset_provider()
    asset_ref = provider.put_bytes(
        payload,
        filename=filename,
        kind=kind,
        mime_type=part.headers.get("Content-Type"),
    )
    return web.json_response({"ok": True, "asset": asset_ref.to_dict()})
