from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
import wave
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .provider_router import get_asset_provider

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

try:
    import av
except Exception:  # pragma: no cover
    av = None

try:
    from comfy_api.latest import InputImpl, Types
except Exception:  # pragma: no cover
    InputImpl = None
    Types = None


def _ensure_torch() -> None:
    if torch is None:
        raise RuntimeError("PyTorch is required for Graviton image nodes")


def _ensure_av() -> None:
    if av is None:
        raise RuntimeError("PyAV is required for Graviton audio nodes")


def _ensure_comfy_video_types() -> None:
    if InputImpl is None:
        raise RuntimeError("Comfy video runtime types are not available")


def _ensure_comfy_3d_types() -> None:
    if Types is None or not hasattr(Types, "File3D"):
        raise RuntimeError("Comfy 3D runtime types are not available")


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


def _iter_image_batch_tensors(image_tensor: Any) -> list[Any]:
    _ensure_torch()
    tensor = image_tensor
    if isinstance(tensor, list):
        frames: list[Any] = []
        for item in tensor:
            if hasattr(item, "dim") and item.dim() == 4:
                frames.extend([item[i] for i in range(item.shape[0])])
            else:
                frames.append(item)
        return frames
    if not hasattr(tensor, "dim"):
        raise ValueError("Unsupported image tensor type")
    if tensor.dim() == 4:
        return [tensor[i] for i in range(tensor.shape[0])]
    if tensor.dim() == 3:
        return [tensor]
    raise ValueError("Expected image tensor with shape [B, H, W, C] or [H, W, C]")


def _parse_asset_ref(asset_ref: str) -> dict[str, Any]:
    raw = (asset_ref or "").strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _infer_filename_from_asset_ref(asset_ref: str, fallback: str) -> str:
    parsed = _parse_asset_ref(asset_ref)
    name = parsed.get("filename")
    if isinstance(name, str) and name.strip():
        return os.path.basename(name.strip())
    return fallback


def _materialize_asset_to_temp(asset_ref: str, fallback_filename: str) -> str:
    provider = get_asset_provider()
    payload = provider.get_bytes(_require_asset_id(asset_ref))
    suffix = Path(_infer_filename_from_asset_ref(asset_ref, fallback_filename)).suffix or Path(fallback_filename).suffix
    cache_dir = Path(tempfile.gettempdir()) / "graviton_bridge_assets"
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_dir / f"{uuid.uuid4().hex}{suffix}"
    tmp_path.write_bytes(payload)
    return str(tmp_path)


def _f32_pcm(wav: Any) -> Any:
    _ensure_torch()
    if wav.dtype.is_floating_point:
        return wav
    if wav.dtype == torch.int16:
        return wav.float() / (2**15)
    if wav.dtype == torch.int32:
        return wav.float() / (2**31)
    raise ValueError(f"Unsupported wav dtype: {wav.dtype}")


def _decode_audio_payload(payload: bytes) -> tuple[Any, int]:
    _ensure_av()
    _ensure_torch()
    with av.open(io.BytesIO(payload)) as af:
        if not af.streams.audio:
            raise ValueError("No audio stream found in the file.")
        stream = af.streams.audio[0]
        sample_rate = stream.codec_context.sample_rate
        channels = stream.channels
        frames: list[Any] = []
        for frame in af.decode(streams=stream.index):
            buf = torch.from_numpy(frame.to_ndarray())
            if buf.shape[0] != channels:
                buf = buf.view(-1, channels).t()
            frames.append(buf)
        if not frames:
            raise ValueError("No audio frames decoded.")
        wav = torch.cat(frames, dim=1)
        wav = _f32_pcm(wav)
        return wav, int(sample_rate)


def _encode_audio_to_wav_bytes(audio: dict[str, Any]) -> bytes:
    _ensure_torch()
    waveform = audio.get("waveform")
    sample_rate = int(audio.get("sample_rate"))
    if waveform is None:
        raise ValueError("AUDIO input missing waveform")
    if hasattr(waveform, "dim") and waveform.dim() == 3:
        waveform = waveform[0]
    if not hasattr(waveform, "dim") or waveform.dim() != 2:
        raise ValueError("Expected waveform shape [B,C,S] or [C,S]")
    pcm = torch.clamp(waveform, -1.0, 1.0)
    pcm = (pcm.t().cpu().numpy() * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(int(waveform.shape[0]))
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


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


def _require_asset_id(asset_ref: str) -> str:
    asset_id = _extract_asset_id(asset_ref)
    if not asset_id:
        raise ValueError(
            "asset_ref resolved to empty value. "
            "Check chain template (e.g. {{ step_id.output.output }}) and upstream step output."
        )
    return asset_id


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

    def save(self, image: Any, filename: str) -> dict[str, Any]:
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
        asset_id = asset_ref.asset_id
        asset_ref_json = json.dumps(asset_ref.to_dict())
        return {
            "ui": {"asset_id": [asset_id], "asset_ref": [asset_ref_json]},
            "result": (asset_id, asset_ref_json),
        }


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
        payload = provider.get_bytes(_require_asset_id(asset_ref))
        img = Image.open(io.BytesIO(payload))
        return (_to_image_tensor_from_pil(img),)


class GravitonSaveImagesBatch:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "graviton_image"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("asset_id", "asset_ref", "count")
    FUNCTION = "save"
    CATEGORY = "graviton/io/save"
    OUTPUT_NODE = True

    def save(self, images: Any, filename_prefix: str) -> dict[str, Any]:
        provider = get_asset_provider()
        prefix = (filename_prefix or "graviton_image").strip() or "graviton_image"
        frames = _iter_image_batch_tensors(images)
        if not frames:
            raise ValueError("No images to save")
        # Store the full batch in one compressed payload to avoid one object per frame.
        batch = np.stack(
            [np.clip(frame.cpu().numpy() * 255.0, 0, 255).astype(np.uint8) for frame in frames],
            axis=0,
        )
        packed = io.BytesIO()
        np.savez_compressed(packed, frames=batch)
        meta = provider.put_bytes(
            packed.getvalue(),
            filename=f"{prefix}.npz",
            kind="image",
            mime_type="application/x-npz",
        ).to_dict()
        asset_id = meta["asset_id"]
        asset_ref_json = json.dumps(meta)
        return {
            "ui": {"asset_id": [asset_id], "asset_ref": [asset_ref_json], "count": [len(frames)]},
            "result": (asset_id, asset_ref_json, len(frames)),
        }


class GravitonLoadImagesBatch:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"asset_ref": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("IMAGE", "INT")
    RETURN_NAMES = ("images", "count")
    FUNCTION = "load"
    CATEGORY = "graviton/io/load"

    def load(self, asset_ref: str) -> tuple[Any, int]:
        provider = get_asset_provider()
        payload = provider.get_bytes(_require_asset_id(asset_ref))
        packed = np.load(io.BytesIO(payload), allow_pickle=False)
        if "frames" not in packed:
            raise ValueError("Invalid batch payload: missing 'frames'")
        frames = packed["frames"]
        if frames.ndim != 4 or frames.shape[-1] not in (3, 4):
            raise ValueError("Invalid batch payload shape; expected [B,H,W,C]")
        batch = frames[..., :3].astype(np.float32) / 255.0
        _ensure_torch()
        return (torch.from_numpy(batch), int(batch.shape[0]))


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

    def save(self, text: str, filename: str) -> dict[str, Any]:
        meta = _save_text(text or "", filename or "graviton_text.md", "text")
        asset_id = meta["asset_id"]
        asset_ref_json = json.dumps(meta)
        return {
            "ui": {"asset_id": [asset_id], "asset_ref": [asset_ref_json]},
            "result": (asset_id, asset_ref_json),
        }


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
        payload = provider.get_bytes(_require_asset_id(asset_ref))
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

    def save(self, source_path: str) -> dict[str, Any]:
        meta = _save_file_from_path(source_path, self.KIND)
        asset_id = meta["asset_id"]
        asset_ref_json = json.dumps(meta)
        return {
            "ui": {"asset_id": [asset_id], "asset_ref": [asset_ref_json]},
            "result": (asset_id, asset_ref_json),
        }


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
        blob = provider.resolve_local_path(_require_asset_id(asset_ref))
        if blob is None:
            raise ValueError("Asset not found")
        return (str(blob),)


class GravitonSaveVideo:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        format_options = ["auto", "mp4", "webm", "mov", "mkv"]
        codec_options = ["auto", "h264", "hevc", "vp9", "av1"]
        try:
            if Types is not None and hasattr(Types, "VideoContainer"):
                format_options = list(Types.VideoContainer.as_input())
            if Types is not None and hasattr(Types, "VideoCodec"):
                codec_options = list(Types.VideoCodec.as_input())
        except Exception:
            pass
        return {
            "required": {
                "video": ("VIDEO",),
                "filename_prefix": ("STRING", {"default": "video/graviton"}),
                "format": (format_options, {"default": "auto"}),
                "codec": (codec_options, {"default": "auto"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("asset_id", "asset_ref")
    FUNCTION = "save"
    CATEGORY = "graviton/io/save"
    OUTPUT_NODE = True

    def save(self, video: Any, filename_prefix: str, format: str, codec: str) -> dict[str, Any]:
        if not hasattr(video, "save_to"):
            raise ValueError("Expected VIDEO input")
        ext = "mp4" if format in ("auto", "", None) else str(format).lower()
        cache_dir = Path(tempfile.gettempdir()) / "graviton_bridge_assets"
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_dir / f"{uuid.uuid4().hex}.{ext}"
        container = format
        codec_value = codec
        try:
            if Types is not None and hasattr(Types, "VideoContainer") and format not in ("auto", "", None):
                container = Types.VideoContainer(format)
            if Types is not None and hasattr(Types, "VideoCodec") and codec not in ("auto", "", None):
                codec_value = Types.VideoCodec(codec)
        except Exception:
            pass
        video.save_to(str(tmp_path), format=container, codec=codec_value, metadata=None)
        provider = get_asset_provider()
        meta = provider.put_file(str(tmp_path), kind="video").to_dict()
        asset_id = meta["asset_id"]
        asset_ref_json = json.dumps(meta)
        return {
            "ui": {"asset_id": [asset_id], "asset_ref": [asset_ref_json]},
            "result": (asset_id, asset_ref_json),
        }


class GravitonLoadVideo:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"asset_ref": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)
    FUNCTION = "load"
    CATEGORY = "graviton/io/load"

    def load(self, asset_ref: str) -> tuple[Any]:
        _ensure_comfy_video_types()
        local_path = _materialize_asset_to_temp(asset_ref, "graviton_video.mp4")
        return (InputImpl.VideoFromFile(local_path),)


class GravitonSaveAudio:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "audio": ("AUDIO",),
                "filename": ("STRING", {"default": "graviton_audio.wav"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("asset_id", "asset_ref")
    FUNCTION = "save"
    CATEGORY = "graviton/io/save"
    OUTPUT_NODE = True

    def save(self, audio: dict[str, Any], filename: str) -> dict[str, Any]:
        payload = _encode_audio_to_wav_bytes(audio)
        name = filename or "graviton_audio.wav"
        provider = get_asset_provider()
        meta = provider.put_bytes(payload, filename=name, kind="audio", mime_type="audio/wav").to_dict()
        asset_id = meta["asset_id"]
        asset_ref_json = json.dumps(meta)
        return {
            "ui": {"asset_id": [asset_id], "asset_ref": [asset_ref_json]},
            "result": (asset_id, asset_ref_json),
        }


class GravitonLoadAudio:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"asset_ref": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("audio",)
    FUNCTION = "load"
    CATEGORY = "graviton/io/load"

    def load(self, asset_ref: str) -> tuple[dict[str, Any]]:
        provider = get_asset_provider()
        payload = provider.get_bytes(_require_asset_id(asset_ref))
        waveform, sample_rate = _decode_audio_payload(payload)
        return ({"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate},)


class GravitonSave3D:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "model_3d": ("FILE3DANY",),
                "filename": ("STRING", {"default": "graviton_model.glb"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("asset_id", "asset_ref")
    FUNCTION = "save"
    CATEGORY = "graviton/io/save"
    OUTPUT_NODE = True

    def save(self, model_3d: Any, filename: str) -> dict[str, Any]:
        if not hasattr(model_3d, "save_to"):
            raise ValueError("Expected FILE3D input")
        model_format = getattr(model_3d, "format", None) or Path(filename or "").suffix.lstrip(".") or "glb"
        cache_dir = Path(tempfile.gettempdir()) / "graviton_bridge_assets"
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_dir / f"{uuid.uuid4().hex}.{model_format}"
        model_3d.save_to(str(tmp_path))
        provider = get_asset_provider()
        meta = provider.put_file(str(tmp_path), kind="3d").to_dict()
        asset_id = meta["asset_id"]
        asset_ref_json = json.dumps(meta)
        return {
            "ui": {"asset_id": [asset_id], "asset_ref": [asset_ref_json]},
            "result": (asset_id, asset_ref_json),
        }


class GravitonLoad3D:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {"asset_ref": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("FILE3DANY",)
    RETURN_NAMES = ("model_3d",)
    FUNCTION = "load"
    CATEGORY = "graviton/io/load"

    def load(self, asset_ref: str) -> tuple[Any]:
        _ensure_comfy_3d_types()
        local_path = _materialize_asset_to_temp(asset_ref, "graviton_model.glb")
        return (Types.File3D(local_path),)


NODE_CLASS_MAPPINGS = {
    "GravitonSaveImage": GravitonSaveImage,
    "GravitonLoadImage": GravitonLoadImage,
    "GravitonSaveImagesBatch": GravitonSaveImagesBatch,
    "GravitonLoadImagesBatch": GravitonLoadImagesBatch,
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
    "GravitonSaveImagesBatch": "Graviton Save Images (Batch)",
    "GravitonLoadImagesBatch": "Graviton Load Images (Batch)",
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
