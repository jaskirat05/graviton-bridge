from __future__ import annotations

from aiohttp import web
from aiohttp.web_request import Request

import server

from .config_store import (
    load_effective_config,
    save_file_config,
)


def _extract_config(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")

    if "config" in payload:
        config = payload.get("config")
        if not isinstance(config, dict):
            raise ValueError("'config' must be a JSON object")
        return config
    return payload


@server.PromptServer.instance.routes.get("/graviton-bridge/config")
async def get_bridge_config(_request: Request) -> web.Response:
    effective = load_effective_config()
    return web.json_response({"config": effective})


@server.PromptServer.instance.routes.post("/graviton-bridge/config")
async def post_bridge_config(request: Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    try:
        config = _extract_config(payload)
    except ValueError as error:
        return web.json_response({"error": str(error)}, status=400)

    mode = config.get("mode")
    if mode is None:
        return web.json_response({"error": "mode is required"}, status=400)

    try:
        saved = save_file_config({"mode": mode})
    except ValueError as error:
        return web.json_response({"error": str(error)}, status=400)

    return web.json_response(
        {
            "ok": True,
            "saved_config": saved,
            "effective_config": load_effective_config(),
        }
    )
