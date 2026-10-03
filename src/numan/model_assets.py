"""Explicit installation and verification of offline voice model assets."""

from __future__ import annotations

import hashlib
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class VoiceModelAsset:
    provider: str
    relative_path: str
    url: str
    sha256: str


VOICE_MODEL_ASSETS = (
    VoiceModelAsset(
        "piper",
        "models/tts/piper/en_GB-alan-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "en/en_GB/alan/medium/en_GB-alan-medium.onnx?download=true",
        "0a309668932205e762801f1efc2736cd4b0120329622adf62be09e56339d3330",
    ),
    VoiceModelAsset(
        "piper",
        "models/tts/piper/en_GB-alan-medium.onnx.json",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "en/en_GB/alan/medium/en_GB-alan-medium.onnx.json?download=true",
        "c0f0d124e5895c00e7c03b35dcc8287f319a6998a365b182deb5c8e752ee8c1e",
    ),
    VoiceModelAsset(
        "piper",
        "models/tts/piper/en_US-lessac-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true",
        "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f",
    ),
    VoiceModelAsset(
        "piper",
        "models/tts/piper/en_US-lessac-medium.onnx.json",
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json?download=true",
        "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0",
    ),
    VoiceModelAsset(
        "kokoro",
        "models/tts/kokoro/kokoro-v1.0.onnx",
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.1/kokoro-v1.0.onnx",
        "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a",
    ),
    VoiceModelAsset(
        "kokoro",
        "models/tts/kokoro/voices-v1.0.bin",
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
        "model-files-v1.1/voices-v1.0.bin",
        "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
    ),
)


def selected_assets(provider: str = "all") -> tuple[VoiceModelAsset, ...]:
    if provider == "all":
        return VOICE_MODEL_ASSETS
    if provider not in {"piper", "kokoro"}:
        raise ValueError(f"unknown voice model provider: {provider}")
    return tuple(asset for asset in VOICE_MODEL_ASSETS if asset.provider == provider)


def verify_voice_models(
    root: str | Path, provider: str = "all"
) -> list[dict[str, object]]:
    root = Path(root)
    results = []
    for asset in selected_assets(provider):
        path = root / asset.relative_path
        actual = _sha256(path) if path.is_file() else None
        results.append({
            "provider": asset.provider,
            "path": str(path),
            "present": path.is_file(),
            "valid": actual == asset.sha256,
            "expected_sha256": asset.sha256,
            "actual_sha256": actual,
        })
    return results


def install_voice_models(
    root: str | Path,
    provider: str = "all",
    *,
    opener=urllib.request.urlopen,
    progress: Callable[[VoiceModelAsset, str, int, int | None], None] | None = None,
) -> list[Path]:
    """Download missing/invalid assets and atomically publish verified files."""
    root = Path(root)
    installed = []
    for asset in selected_assets(provider):
        destination = root / asset.relative_path
        if progress is not None:
            progress(asset, "checking", 0, None)
        if destination.is_file() and _sha256(destination) == asset.sha256:
            if progress is not None:
                progress(asset, "cached", destination.stat().st_size, destination.stat().st_size)
            installed.append(destination)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{destination.name}-{uuid4().hex}.partial"
        try:
            with opener(asset.url) as response, temporary.open("wb") as output:
                total = _content_length(response)
                downloaded = 0
                if progress is not None:
                    progress(asset, "downloading", downloaded, total)
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    downloaded += len(chunk)
                    if progress is not None:
                        progress(asset, "downloading", downloaded, total)
            if progress is not None:
                progress(asset, "verifying", downloaded, total)
            actual = _sha256(temporary)
            if actual != asset.sha256:
                raise RuntimeError(
                    f"checksum mismatch for {destination.name}: expected "
                    f"{asset.sha256}, received {actual}"
                )
            os.replace(temporary, destination)
            if progress is not None:
                progress(asset, "installed", downloaded, total)
            installed.append(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return installed


def _content_length(response) -> int | None:
    value = None
    if getattr(response, "headers", None) is not None:
        value = response.headers.get("Content-Length")
    elif hasattr(response, "getheader"):
        value = response.getheader("Content-Length")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
