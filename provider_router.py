from __future__ import annotations

from .config_store import load_effective_config
from .provider_base import AssetProvider
from .provider_cloudinary import CloudinaryAssetProvider
from .provider_orchestrator import OrchestratorAssetProvider
from .provider_s3 import S3AssetProvider


def get_asset_provider() -> AssetProvider:
    cfg = load_effective_config()
    mode = str(cfg.get("mode", "local")).strip().lower()
    if mode == "s3":
        return S3AssetProvider()
    if mode == "cloudinary":
        return CloudinaryAssetProvider()
    if mode in {"local", "orchestrator"}:
        return OrchestratorAssetProvider()
    raise ValueError(f"Unsupported asset provider configuration (mode={mode})")
