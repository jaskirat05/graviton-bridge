from __future__ import annotations

from aiohttp import web
from aiohttp.web_request import Request

import server

from .config_store import (
    load_effective_config,
    redact_config,
    save_file_config,
)
from .control_auth import control_auth_enabled, get_worker_id, verify_control_hmac


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
    return web.json_response({"config": redact_config(effective)})


@server.PromptServer.instance.routes.get("/graviton-bridge/control/status")
async def get_control_status(_request: Request) -> web.Response:
    effective = load_effective_config()
    return web.json_response(
        {
            "worker_id": get_worker_id(),
            "control_auth_enabled": control_auth_enabled(),
            "config": redact_config(effective),
        }
    )


@server.PromptServer.instance.routes.post("/graviton-bridge/config")
async def post_bridge_config(request: Request) -> web.Response:
    body = await request.read()

    # Enforce control-plane authentication for configuration mutations.
    is_valid, failure_response = verify_control_hmac(request, body)
    if not is_valid:
        return failure_response

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    try:
        config = _extract_config(payload)
    except ValueError as error:
        return web.json_response({"error": str(error)}, status=400)

    if "mode" not in config:
        return web.json_response({"error": "mode is required"}, status=400)

    try:
        saved = save_file_config(config)
    except ValueError as error:
        return web.json_response({"error": str(error)}, status=400)

    return web.json_response(
        {
            "ok": True,
            "worker_id": get_worker_id(),
            "saved_config": redact_config(saved),
            "effective_config": redact_config(load_effective_config()),
        }
    )
