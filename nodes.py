from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .provider_router import get_asset_provider

try:
    import torch
except Exception:  # pragma: no cover
    torch = None


def _ensure_torch() -> None:
    if torch is None:
        raise RuntimeError("PyTorch is required for Graviton image nodes")


def _to_pil_from_image_tensor(image_tensor: Any) -> Image.Image:
    _ensure_torch()
    tensor = image_tensor
    if isinstance(tensor, list) and tensor:
        tensor = tensor[0]
    if hasattr(tensor, "dim") and tensor.dim() == 4:
        tensor = tensor[0]
    if not hasattr(tensor, "cpu"):
        raise ValueError("Unsupported image tensor type")
    arr = tensor.cpu().numpy()
    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    if arr.ndim == 3 and arr.shape[2] in (3, 4):
        return Image.fromarray(arr)
    raise ValueError("Expected image tensor shape [H, W, C]")


def _to_image_tensor_from_pil(img: Image.Image) -> Any:
    _ensure_torch()
    rgb = img.convert("RGB")
    arr = np.asarray(rgb).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def _save_text(payload: str, filename: str, kind: str) -> dict[str, Any]:
    data = payload.encode("utf-8")
    provider = get_asset_provider()
    return provider.put_bytes(
        data,
        filename=filename,
        kind=kind,
        mime_type="text/plain; charset=utf-8",
    ).to_dict()


def _save_file_from_path(path_value: str, kind: str) -> dict[str, Any]:
    source_path = Path(path_value).expanduser()
    if not source_path.is_absolute():
        source_path = source_path.resolve()
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Source file not found: {source_path}")
    provider = get_asset_provider()
    return provider.put_file(str(source_path), kind=kind).to_dict()


def _extract_asset_id(raw_ref: str) -> str:
    value = (raw_ref or "").strip()
    if not value:
        return ""
    if value.startswith("{"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                asset_id = parsed.get("asset_id")
                if isinstance(asset_id, str):
                    return asset_id.strip()
        except Exception:
            pass
    return value


class GravitonSaveImage:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "image": ("IMAGE",),
                "filename": ("STRING", {"default": "graviton_image.png"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("asset_id", "asset_ref")
    FUNCTION = "save"
    CATEGORY = "graviton/io/save"
    OUTPUT_NODE = True

    def save(self, image: Any, filename: str) -> tuple[str, str]:
        pil = _to_pil_from_image_tensor(image)
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        provider = get_asset_provider()
        asset_ref = provider.put_bytes(
            buf.getvalue(),
            filename=filename or "graviton_image.png",
            kind="image",
            mime_type="image/png",
        )
        return (asset_ref.asset_id, json.dumps(asset_ref.to_dict()))


class GravitonLoadImage:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"asset_ref": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "load"
    CATEGORY = "graviton/io/load"

    def load(self, asset_ref: str) -> tuple[Any]:
        provider = get_asset_provider()
        payload = provider.get_bytes(_extract_asset_id(asset_ref))
        img = Image.open(io.BytesIO(payload))
        return (_to_image_tensor_from_pil(img),)


class GravitonSaveText:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": ""}),
                "filename": ("STRING", {"default": "graviton_text.md"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("asset_id", "asset_ref")
    FUNCTION = "save"
    CATEGORY = "graviton/io/save"
    OUTPUT_NODE = True

    def save(self, text: str, filename: str) -> tuple[str, str]:
        meta = _save_text(text or "", filename or "graviton_text.md", "text")
        return (meta["asset_id"], json.dumps(meta))


class GravitonLoadText:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"asset_ref": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "load"
    CATEGORY = "graviton/io/load"

    def load(self, asset_ref: str) -> tuple[str]:
        provider = get_asset_provider()
        payload = provider.get_bytes(_extract_asset_id(asset_ref))
        return (payload.decode("utf-8"),)


class GravitonSaveFile:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"source_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("asset_id", "asset_ref")
    FUNCTION = "save"
    CATEGORY = "graviton/io/save"
    OUTPUT_NODE = True

    KIND = "file"

    def save(self, source_path: str) -> tuple[str, str]:
        meta = _save_file_from_path(source_path, self.KIND)
        return (meta["asset_id"], json.dumps(meta))


class GravitonLoadFile:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"asset_ref": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("local_path",)
    FUNCTION = "load"
    CATEGORY = "graviton/io/load"

    def load(self, asset_ref: str) -> tuple[str]:
        provider = get_asset_provider()
        blob = provider.resolve_local_path(_extract_asset_id(asset_ref))
        if blob is None:
            raise ValueError("Asset not found")
        return (str(blob),)


class GravitonSaveVideo(GravitonSaveFile):
    KIND = "video"
    CATEGORY = "graviton/io/save"


class GravitonLoadVideo(GravitonLoadFile):
    CATEGORY = "graviton/io/load"


class GravitonSaveAudio(GravitonSaveFile):
    KIND = "audio"
    CATEGORY = "graviton/io/save"


class GravitonLoadAudio(GravitonLoadFile):
    CATEGORY = "graviton/io/load"


class GravitonSave3D(GravitonSaveFile):
    KIND = "3d"
    CATEGORY = "graviton/io/save"


class GravitonLoad3D(GravitonLoadFile):
    CATEGORY = "graviton/io/load"


NODE_CLASS_MAPPINGS = {
    "GravitonSaveImage": GravitonSaveImage,
    "GravitonLoadImage": GravitonLoadImage,
    "GravitonSaveText": GravitonSaveText,
    "GravitonLoadText": GravitonLoadText,
    "GravitonSaveFile": GravitonSaveFile,
    "GravitonLoadFile": GravitonLoadFile,
    "GravitonSaveVideo": GravitonSaveVideo,
    "GravitonLoadVideo": GravitonLoadVideo,
    "GravitonSaveAudio": GravitonSaveAudio,
    "GravitonLoadAudio": GravitonLoadAudio,
    "GravitonSave3D": GravitonSave3D,
    "GravitonLoad3D": GravitonLoad3D,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GravitonSaveImage": "Graviton Save Image",
    "GravitonLoadImage": "Graviton Load Image",
    "GravitonSaveText": "Graviton Save Text",
    "GravitonLoadText": "Graviton Load Text",
    "GravitonSaveFile": "Graviton Save File",
    "GravitonLoadFile": "Graviton Load File",
    "GravitonSaveVideo": "Graviton Save Video",
    "GravitonLoadVideo": "Graviton Load Video",
    "GravitonSaveAudio": "Graviton Save Audio",
    "GravitonLoadAudio": "Graviton Load Audio",
    "GravitonSave3D": "Graviton Save 3D",
    "GravitonLoad3D": "Graviton Load 3D",
}
