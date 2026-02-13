from __future__ import annotations

import os

from aiohttp import web
from aiohttp.web_request import Request

import server

from .config_store import (
    apply_config_patch,
    load_effective_config,
    sanitize_for_response,
)

PAIRING_TOKEN_ENV = "GRAVITON_PAIRING_TOKEN"


def _extract_config(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")

    if "config" in payload:
        config = payload.get("config")
        if not isinstance(config, dict):
            raise ValueError("'config' must be a JSON object")
        return config
    return payload


def _extract_presented_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("X-Graviton-Pairing-Token", "").strip()


def _is_authorized(request: Request) -> tuple[bool, str]:
    expected = os.getenv(PAIRING_TOKEN_ENV, "").strip()
    if not expected:
        return False, f"Pairing token is not configured on server ({PAIRING_TOKEN_ENV})"
    presented = _extract_presented_token(request)
    if not presented:
        return False, "Missing pairing token"
    if presented != expected:
        return False, "Invalid pairing token"
    return True, ""


@server.PromptServer.instance.routes.get("/graviton-bridge/config")
async def get_bridge_config(_request: Request) -> web.Response:
    effective = load_effective_config()
    return web.json_response({"config": sanitize_for_response(effective)})


@server.PromptServer.instance.routes.post("/graviton-bridge/config")
async def post_bridge_config(request: Request) -> web.Response:
    authorized, reason = _is_authorized(request)
    if not authorized:
        return web.json_response({"error": reason}, status=403)

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    try:
        config = _extract_config(payload)
    except ValueError as error:
        return web.json_response({"error": str(error)}, status=400)

    try:
        saved = apply_config_patch(config)
    except ValueError as error:
        return web.json_response({"error": str(error)}, status=400)

    effective = load_effective_config()
    return web.json_response(
        {
            "ok": True,
            "saved_config": sanitize_for_response(saved),
            "effective_config": sanitize_for_response(effective),
        }
    )
