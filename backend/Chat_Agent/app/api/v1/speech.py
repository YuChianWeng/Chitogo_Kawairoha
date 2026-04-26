from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/speech", tags=["speech"])


async def _to_wav(audio_bytes: bytes, src_mime: str) -> bytes:
    """Convert any browser audio format to 16kHz mono WAV via ffmpeg."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in path")

    suffix = ".webm" if "webm" in src_mime else ".wav" if "wav" in src_mime else ".ogg"
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / f"input{suffix}"
        dst = Path(tmpdir) / "output.wav"
        src.write_bytes(audio_bytes)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(src),
            "-ar", "16000", "-ac", "1", "-f", "wav", str(dst),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("ffmpeg error: %s", stderr.decode(errors="replace"))
            raise RuntimeError("audio conversion failed")
        return dst.read_bytes()


@router.post("/transcribe")
async def transcribe_audio(request: Request, file: UploadFile = File(...)) -> dict[str, str]:
    settings = request.app.state.settings
    api_key = settings.hf_api_key
    endpoint_url = settings.hf_endpoint_url
    if not api_key or not endpoint_url:
        raise HTTPException(status_code=500, detail="語音辨識服務未設定。")

    audio_bytes = await file.read()
    src_mime = file.content_type or "audio/webm"
    
    # If it's already WAV, don't convert
    if src_mime == "audio/wav" or src_mime == "audio/x-wav":
        payload_bytes = audio_bytes
        content_type = "audio/wav"
    else:
        # Try to convert to WAV for better accuracy
        try:
            payload_bytes = await _to_wav(audio_bytes, src_mime)
            content_type = "audio/wav"
        except Exception as exc:
            logger.warning("Audio conversion skipped or failed (falling back to original): %s", exc)
            payload_bytes = audio_bytes
            content_type = src_mime

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": content_type}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint_url, headers=headers, content=payload_bytes)
        if resp.status_code != 200:
            logger.error("HF endpoint error: %s", resp.text)
            raise HTTPException(status_code=502, detail="語音辨識失敗，請再試一次。")
        return {"text": resp.json().get("text", "")}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Transcription error: %s", exc)
        raise HTTPException(status_code=500, detail="語音處理失敗，請再試一次。")
