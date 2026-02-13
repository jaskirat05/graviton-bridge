from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .asset_ref import AssetRef
from .provider_base import AssetProvider


class CloudinaryAssetProvider(AssetProvider):
    def __init__(self) -> None:
        self.cloud_name = os.getenv("GRAVITON_CLOUDINARY_CLOUD_NAME", "").strip()
        self.api_key = os.getenv("GRAVITON_CLOUDINARY_API_KEY", "").strip()
        self.api_secret = os.getenv("GRAVITON_CLOUDINARY_API_SECRET", "").strip()
        self.folder = os.getenv("GRAVITON_CLOUDINARY_FOLDER", "").strip().strip("/")

        if not self.cloud_name:
            raise ValueError(
                "Missing Cloudinary cloud name: set GRAVITON_CLOUDINARY_CLOUD_NAME"
            )
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Missing Cloudinary credentials: set GRAVITON_CLOUDINARY_API_KEY and "
                "GRAVITON_CLOUDINARY_API_SECRET"
            )

        self.upload_base = f"https://api.cloudinary.com/v1_1/{self.cloud_name}"
        self.cache_dir = Path(tempfile.gettempdir()) / "graviton_bridge_cloudinary_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _public_id_for(self, asset_id: str) -> str:
        if self.folder:
            return f"{self.folder}/{asset_id}"
        return asset_id

    def _locator(self, resource_type: str, public_id: str) -> str:
        return f"cloudinary://{self.cloud_name}/{resource_type}/upload/{public_id}"

    def _mime_from_resource(self, resource_type: str, fmt: str | None, fallback: str) -> str:
        if resource_type == "image" and fmt:
            return f"image/{fmt}"
        if resource_type == "video" and fmt:
            return f"video/{fmt}"
        if fmt:
            guessed = mimetypes.guess_type(f"file.{fmt}")[0]
            if guessed:
                return guessed
        return fallback

    def _kind_from_resource(self, resource_type: str, fallback_kind: str = "file") -> str:
        if resource_type == "image":
            return "image"
        if resource_type == "video":
            return "video"
        return fallback_kind

    def _signature(self, params: dict[str, Any]) -> str:
        filtered = {
            k: v
            for k, v in params.items()
            if v is not None and v != "" and k not in {"file", "api_key", "signature"}
        }
        to_sign = "&".join(f"{k}={filtered[k]}" for k in sorted(filtered))
        return hashlib.sha1(f"{to_sign}{self.api_secret}".encode("utf-8")).hexdigest()

    def _auth(self) -> tuple[str, str]:
        return (self.api_key, self.api_secret)

    def _resource_url(self, resource_type: str, public_id: str) -> str:
        encoded_public_id = quote(public_id, safe="")
        return f"{self.upload_base}/resources/{resource_type}/upload/{encoded_public_id}"

    def _to_asset_ref(self, resource: dict[str, Any], checksum: str = "") -> AssetRef:
        public_id = str(resource.get("public_id", ""))
        resource_type = str(resource.get("resource_type", "raw"))
        fmt = str(resource.get("format", "")) or None
        secure_url = str(resource.get("secure_url", ""))
        bytes_size = int(resource.get("bytes", 0) or 0)
        created_at = str(resource.get("created_at", ""))
        original_filename = str(resource.get("original_filename", "")).strip()
        filename = f"{original_filename}.{fmt}" if original_filename and fmt else (original_filename or public_id)
        asset_id = public_id.split("/")[-1]
        mime_type = self._mime_from_resource(resource_type, fmt, "application/octet-stream")

        return AssetRef(
            asset_id=asset_id,
            provider="cloudinary",
            kind=self._kind_from_resource(resource_type),
            mime_type=mime_type,
            size_bytes=bytes_size,
            checksum=checksum,
            locator=self._locator(resource_type, public_id),
            filename=filename,
            created_at=created_at,
            metadata={"secure_url": secure_url, "public_id": public_id, "resource_type": resource_type},
        )

    def _fetch_resource(self, public_id: str) -> dict[str, Any] | None:
        with httpx.Client(timeout=30.0) as client:
            for resource_type in ("image", "video", "raw"):
                res = client.get(self._resource_url(resource_type, public_id), auth=self._auth())
                if res.status_code == 404:
                    continue
                res.raise_for_status()
                payload = res.json()
                if isinstance(payload, dict):
                    return payload
        return None

    def put_bytes(
        self,
        payload: bytes,
        *,
        filename: str,
        kind: str,
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRef:
        asset_id = str(uuid.uuid4())
        public_id = self._public_id_for(asset_id)
        checksum = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        ts = int(time.time())

        params: dict[str, Any] = {
            "timestamp": ts,
            "public_id": public_id,
            "overwrite": "true",
            "unique_filename": "false",
        }
        signature = self._signature(params)

        data = {
            **params,
            "api_key": self.api_key,
            "signature": signature,
        }
        if mime_type:
            data["resource_type"] = "auto"
        if metadata:
            data["context"] = "|".join(f"{k}={v}" for k, v in metadata.items() if v is not None)

        with httpx.Client(timeout=60.0) as client:
            upload_res = client.post(
                f"{self.upload_base}/auto/upload",
                data=data,
                files={"file": (filename, payload, mime_type or "application/octet-stream")},
            )
            upload_res.raise_for_status()
            raw = upload_res.json()
            if not isinstance(raw, dict):
                raise ValueError("Invalid Cloudinary upload response")
            ref = self._to_asset_ref(raw, checksum=checksum)
            return ref

    def put_file(
        self,
        source_path: str,
        *,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRef:
        src = Path(source_path)
        payload = src.read_bytes()
        mime = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
        return self.put_bytes(
            payload,
            filename=src.name,
            kind=kind,
            mime_type=mime,
            metadata=metadata or {},
        )

    def get_meta(self, asset_id: str) -> AssetRef | None:
        public_id = self._public_id_for(asset_id)
        resource = self._fetch_resource(public_id)
        if not resource:
            return None
        return self._to_asset_ref(resource)

    def get_bytes(self, asset_id: str) -> bytes:
        meta = self.get_meta(asset_id)
        if meta is None:
            raise ValueError(f"Asset not found: {asset_id}")
        secure_url = str(meta.metadata.get("secure_url", ""))
        if not secure_url:
            raise ValueError(f"Cloudinary secure_url missing: {asset_id}")
        with httpx.Client(timeout=60.0) as client:
            res = client.get(secure_url)
            res.raise_for_status()
            return res.content

    def resolve_local_path(self, asset_id: str) -> Path | None:
        meta = self.get_meta(asset_id)
        if meta is None:
            return None
        suffix = Path(meta.filename or "").suffix or ".bin"
        target = self.cache_dir / f"{asset_id}{suffix}"
        target.write_bytes(self.get_bytes(asset_id))
        return target

    def list_assets(self) -> list[AssetRef]:
        refs: list[AssetRef] = []
        with httpx.Client(timeout=30.0) as client:
            for resource_type in ("image", "video", "raw"):
                next_cursor: str | None = None
                while True:
                    params: dict[str, Any] = {"max_results": 100}
                    if self.folder:
                        params["prefix"] = f"{self.folder}/"
                    if next_cursor:
                        params["next_cursor"] = next_cursor
                    res = client.get(
                        f"{self.upload_base}/resources/{resource_type}/upload",
                        params=params,
                        auth=self._auth(),
                    )
                    res.raise_for_status()
                    payload = res.json()
                    if not isinstance(payload, dict):
                        break
                    resources = payload.get("resources", [])
                    if isinstance(resources, list):
                        for item in resources:
                            if isinstance(item, dict):
                                refs.append(self._to_asset_ref(item))
                    cursor = payload.get("next_cursor")
                    next_cursor = str(cursor) if isinstance(cursor, str) and cursor else None
                    if not next_cursor:
                        break
        refs.sort(key=lambda r: r.created_at, reverse=True)
        return refs
