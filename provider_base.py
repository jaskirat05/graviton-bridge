from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .asset_ref import AssetRef


class AssetProvider(ABC):
    @abstractmethod
    def put_bytes(
        self,
        payload: bytes,
        *,
        filename: str,
        kind: str,
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRef:
        raise NotImplementedError

    @abstractmethod
    def put_file(
        self,
        source_path: str,
        *,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRef:
        raise NotImplementedError

    @abstractmethod
    def get_meta(self, asset_id: str) -> AssetRef | None:
        raise NotImplementedError

    @abstractmethod
    def get_bytes(self, asset_id: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def resolve_local_path(self, asset_id: str) -> Path | None:
        raise NotImplementedError

    @abstractmethod
    def list_assets(self) -> list[AssetRef]:
        raise NotImplementedError
