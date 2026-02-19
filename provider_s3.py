from __future__ import annotations

import hashlib
import json
import mimetypes
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .asset_ref import AssetRef
from .config_store import load_effective_config
from .provider_base import AssetProvider


class S3AssetProvider(AssetProvider):
    def __init__(self) -> None:
        cfg = load_effective_config().get("s3", {})
        if not isinstance(cfg, dict):
            cfg = {}

        self.bucket = str(cfg.get("bucket", "")).strip()
        self.region = str(cfg.get("region", "")).strip()
        self.prefix = str(cfg.get("prefix", "")).strip().strip("/")
        self.access_key = str(cfg.get("access_key", "")).strip()
        self.secret_key = str(cfg.get("secret_key", "")).strip()

        if not self.bucket:
            raise ValueError("Missing S3 bucket in bridge config (s3.bucket)")
        if not self.region:
            raise ValueError("Missing S3 region in bridge config (s3.region)")
        if not self.access_key or not self.secret_key:
            raise ValueError(
                "Missing S3 credentials in bridge config (s3.access_key, s3.secret_key)"
            )

        self._s3 = self._build_client()
        self.cache_dir = Path(tempfile.gettempdir()) / "graviton_bridge_s3_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _build_client(self):
        try:
            import boto3
        except Exception as error:
            raise RuntimeError("S3 provider requires boto3 installed") from error

        return boto3.client(
            "s3",
            region_name=self.region,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )

    def _join_key(self, *parts: str) -> str:
        cleaned = [p.strip("/") for p in parts if p and p.strip("/")]
        return "/".join(cleaned)

    def _blob_key_for(self, asset_id: str, filename: str) -> str:
        suffix = Path(filename).suffix or ".bin"
        blob_name = f"{asset_id}{suffix}"
        return self._join_key(self.prefix, "blobs", blob_name)

    def _meta_key_for(self, asset_id: str) -> str:
        return self._join_key(self.prefix, "meta", f"{asset_id}.json")

    def _build_locator(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"

    def _parse_locator_key(self, locator: str) -> str:
        prefix = f"s3://{self.bucket}/"
        if not locator.startswith(prefix):
            raise ValueError(f"Invalid locator for bucket {self.bucket}: {locator}")
        return locator[len(prefix) :]

    def _write_meta(self, meta: dict[str, Any]) -> None:
        key = self._meta_key_for(str(meta.get("asset_id", "")))
        payload = json.dumps(meta, sort_keys=True).encode("utf-8")
        self._s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="application/json",
        )

    def _read_meta(self, asset_id: str) -> dict[str, Any] | None:
        key = self._meta_key_for(asset_id)
        try:
            res = self._s3.get_object(Bucket=self.bucket, Key=key)
        except Exception:
            return None
        body = res.get("Body")
        if body is None:
            return None
        try:
            raw = body.read()
            loaded = json.loads(raw.decode("utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            return None
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
        resolved_mime = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        checksum = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        created_at = datetime.now(timezone.utc).isoformat()

        blob_key = self._blob_key_for(asset_id, filename)
        self._s3.put_object(
            Bucket=self.bucket,
            Key=blob_key,
            Body=payload,
            ContentType=resolved_mime,
        )

        meta = {
            "asset_id": asset_id,
            "provider": "s3",
            "kind": kind,
            "mime_type": resolved_mime,
            "size_bytes": len(payload),
            "checksum": checksum,
            "locator": self._build_locator(blob_key),
            "filename": filename,
            "created_at": created_at,
            "metadata": metadata or {},
        }
        self._write_meta(meta)
        return AssetRef.from_dict(meta)

    def put_file(
        self,
        source_path: str,
        *,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRef:
        src = Path(source_path)
        payload = src.read_bytes()
        return self.put_bytes(payload, filename=src.name, kind=kind, metadata=metadata or {})

    def get_meta(self, asset_id: str) -> AssetRef | None:
        meta = self._read_meta(asset_id)
        if not meta:
            return None
        return AssetRef.from_dict(meta)

    def get_bytes(self, asset_id: str) -> bytes:
        meta = self.get_meta(asset_id)
        if meta is None:
            raise ValueError(f"Asset not found: {asset_id}")
        blob_key = self._parse_locator_key(meta.locator)
        res = self._s3.get_object(Bucket=self.bucket, Key=blob_key)
        body = res.get("Body")
        if body is None:
            raise ValueError(f"Asset payload missing: {asset_id}")
        return body.read()

    def resolve_local_path(self, asset_id: str) -> Path | None:
        meta = self.get_meta(asset_id)
        if meta is None:
            return None
        suffix = Path(meta.filename or "").suffix or ".bin"
        target = self.cache_dir / f"{asset_id}{suffix}"
        target.write_bytes(self.get_bytes(asset_id))
        return target

    def list_assets(self) -> list[AssetRef]:
        prefix = self._join_key(self.prefix, "meta")
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
        refs: list[AssetRef] = []
        while True:
            page = self._s3.list_objects_v2(**kwargs)
            for obj in page.get("Contents", []):
                key = str(obj.get("Key", ""))
                if not key.endswith(".json"):
                    continue
                try:
                    res = self._s3.get_object(Bucket=self.bucket, Key=key)
                    body = res.get("Body")
                    if body is None:
                        continue
                    raw = json.loads(body.read().decode("utf-8"))
                    if isinstance(raw, dict):
                        refs.append(AssetRef.from_dict(raw))
                except Exception:
                    continue
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
            if not isinstance(token, str) or not token:
                break
            kwargs["ContinuationToken"] = token
        refs.sort(key=lambda r: r.created_at, reverse=True)
        return refs
