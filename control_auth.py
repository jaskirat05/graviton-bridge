from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

from aiohttp import web
from dotenv import load_dotenv

from .constants import ROOT_DIR

_WORKER_ID_PATH = ROOT_DIR / ".worker_id"

# Load project-root .env defaults once; process env still takes precedence.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)

_NONCE_CACHE: Dict[str, float] = {}

HEADER_TIMESTAMP = "X-Graviton-Timestamp"
HEADER_NONCE = "X-Graviton-Nonce"
HEADER_SIGNATURE = "X-Graviton-Signature"


def get_worker_id() -> str:
    env_worker_id = os.getenv("GRAVITON_WORKER_ID", "").strip()
    if env_worker_id:
        return env_worker_id

    try:
        if _WORKER_ID_PATH.exists():
            existing = _WORKER_ID_PATH.read_text(encoding="utf-8").strip()
            if existing:
                return existing
    except Exception:
        pass

    generated = f"worker-{uuid.uuid4().hex[:12]}"
    try:
        _WORKER_ID_PATH.write_text(generated, encoding="utf-8")
    except Exception:
        # Last resort: still return generated value even if persistence fails.
        pass
    return generated


def _load_secret() -> str:
    return os.getenv("GRAVITON_BRIDGE_CONTROL_HMAC_SECRET", "").strip()


def _max_skew_seconds() -> int:
    raw = os.getenv("GRAVITON_BRIDGE_CONTROL_MAX_SKEW_SECONDS", "60").strip()
    try:
        value = int(raw)
        return max(1, value)
    except Exception:
        return 60


def _nonce_ttl_seconds() -> int:
    raw = os.getenv("GRAVITON_BRIDGE_CONTROL_NONCE_TTL_SECONDS", "300").strip()
    try:
        value = int(raw)
        return max(10, value)
    except Exception:
        return 300


def _prune_nonces(now: float) -> None:
    expired = [nonce for nonce, expiry in _NONCE_CACHE.items() if expiry <= now]
    for nonce in expired:
        _NONCE_CACHE.pop(nonce, None)


def control_auth_enabled() -> bool:
    return bool(_load_secret())


def verify_control_hmac(request: web.Request, body: bytes) -> Tuple[bool, Optional[web.Response]]:
    """
    Verify HMAC + nonce + timestamp headers for control-plane mutations.

    Expected headers:
    - X-Graviton-Timestamp: unix epoch seconds
    - X-Graviton-Nonce: unique random token per request
    - X-Graviton-Signature: hex(HMAC_SHA256(secret, method\npath\ntimestamp\nnonce\nbody))
    """
    secret = _load_secret()
    if not secret:
        return (
            False,
            web.json_response(
                {"error": "Control auth is not configured on worker"},
                status=503,
            ),
        )

    timestamp = request.headers.get(HEADER_TIMESTAMP, "").strip()
    nonce = request.headers.get(HEADER_NONCE, "").strip()
    signature = request.headers.get(HEADER_SIGNATURE, "").strip().lower()

    if not timestamp or not nonce or not signature:
        return (
            False,
            web.json_response(
                {
                    "error": (
                        "Missing control auth headers. Required: "
                        f"{HEADER_TIMESTAMP}, {HEADER_NONCE}, {HEADER_SIGNATURE}"
                    )
                },
                status=401,
            ),
        )

    try:
        sent_ts = int(timestamp)
    except Exception:
        return False, web.json_response({"error": "Invalid timestamp header"}, status=401)

    now = time.time()
    if abs(now - sent_ts) > _max_skew_seconds():
        return False, web.json_response({"error": "Stale timestamp"}, status=401)

    _prune_nonces(now)
    if nonce in _NONCE_CACHE:
        return False, web.json_response({"error": "Replay detected (nonce reused)"}, status=401)

    message = (
        request.method.upper().encode("utf-8")
        + b"\n"
        + request.path.encode("utf-8")
        + b"\n"
        + str(sent_ts).encode("utf-8")
        + b"\n"
        + nonce.encode("utf-8")
        + b"\n"
        + body
    )
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False, web.json_response({"error": "Invalid signature"}, status=401)

    _NONCE_CACHE[nonce] = now + _nonce_ttl_seconds()
    return True, None
