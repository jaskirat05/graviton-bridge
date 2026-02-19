from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from .asset_ref import AssetRef
from .config_store import load_effective_config
from .provider_base import AssetProvider


class OrchestratorAssetProvider(AssetProvider):
    def __init__(self) -> None:
        cfg = load_effective_config().get("orchestrator", {})
        if not isinstance(cfg, dict):
            cfg = {}

        base_url = str(cfg.get("base_url", "")).strip()
        token = str(cfg.get("token", "")).strip()
        if not base_url:
            raise ValueError(
                "Missing orchestrator base_url in bridge config (orchestrator.base_url)"
            )

        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.cache_dir = Path(tempfile.gettempdir()) / "graviton_bridge_asset_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def _read_json(self, response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Invalid JSON response from orchestrator")
        return payload

    def put_bytes(
        self,
        payload: bytes,
        *,
        filename: str,
        kind: str,
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRef:
        mime = mime_type or "application/octet-stream"
        body = {
            "filename": filename,
            "kind": kind,
            "mime_type": mime,
            "size_bytes": len(payload),
            "metadata": metadata or {},
        }

        with httpx.Client(timeout=60.0) as client:
            reg_res = client.post(
                self._url("/assets/register-upload"),
                headers=self._headers(json_body=True),
                content=json.dumps(body),
            )
            reg = self._read_json(reg_res)
            upload = reg.get("upload", {})
            upload_url = upload.get("url")
            if not isinstance(upload_url, str) or not upload_url:
                raise ValueError("Orchestrator register-upload missing upload.url")

            upload_res = client.post(
                self._url(upload_url),
                headers=self._headers(),
                files={"file": (filename, payload, mime)},
            )
            self._read_json(upload_res)

            asset_ref = reg.get("asset_ref", {})
            asset_id = asset_ref.get("asset_id") if isinstance(asset_ref, dict) else None
            if not isinstance(asset_id, str) or not asset_id:
                raise ValueError("register-upload response missing asset_id")

            complete_res = client.post(
                self._url(f"/assets/{asset_id}:complete-upload"),
                headers=self._headers(json_body=True),
                content=json.dumps({}),
            )
            completed = self._read_json(complete_res)
            completed_ref = completed.get("asset_ref")
            if not isinstance(completed_ref, dict):
                raise ValueError("complete-upload response missing asset_ref")

        return AssetRef.from_dict(completed_ref)

    def put_file(
        self,
        source_path: str,
        *,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRef:
        src = Path(source_path)
        payload = src.read_bytes()
        return self.put_bytes(
            payload,
            filename=src.name,
            kind=kind,
            metadata=metadata or {},
        )

    def get_meta(self, asset_id: str) -> AssetRef | None:
        with httpx.Client(timeout=30.0) as client:
            res = client.get(
                self._url(f"/assets/{asset_id}/meta"),
                headers=self._headers(),
            )
            if res.status_code == 404:
                return None
            payload = self._read_json(res)
            asset_ref = payload.get("asset_ref")
            if not isinstance(asset_ref, dict):
                return None
            return AssetRef.from_dict(asset_ref)

    def get_bytes(self, asset_id: str) -> bytes:
        with httpx.Client(timeout=60.0) as client:
            resolve_res = client.get(
                self._url(f"/assets/{asset_id}/resolve"),
                headers=self._headers(),
            )
            resolved = self._read_json(resolve_res)
            download = resolved.get("download", {})
            download_url = download.get("url")
            if not isinstance(download_url, str) or not download_url:
                raise ValueError("resolve response missing download.url")

            file_res = client.get(
                self._url(download_url),
                headers=self._headers(),
            )
            file_res.raise_for_status()
            return file_res.content

    def resolve_local_path(self, asset_id: str) -> Path | None:
        meta = self.get_meta(asset_id)
        if meta is None:
            return None

        suffix = Path(meta.filename or "").suffix or ".bin"
        target = self.cache_dir / f"{asset_id}{suffix}"
        payload = self.get_bytes(asset_id)
        target.write_bytes(payload)
        return target

    def list_assets(self) -> list[AssetRef]:
        # Not required for runtime chaining; can be added later if needed.
        return []
