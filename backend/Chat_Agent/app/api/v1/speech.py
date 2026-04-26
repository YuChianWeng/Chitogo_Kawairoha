from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/speech", tags=["speech"])
_HF_TIMEOUT = httpx.Timeout(90.0, connect=10.0)
_HF_RETRY_STATUSES = {502, 503, 504}
_HF_RETRY_DELAYS_SECONDS = (1.0, 2.0)


async def _to_wav(audio_bytes: bytes, src_mime: str) -> bytes:
    """Convert any browser audio format to 16kHz mono WAV via ffmpeg."""
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


def _truncate_body(text: str, limit: int = 300) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def _is_retryable_response(response: httpx.Response) -> bool:
    return response.status_code in _HF_RETRY_STATUSES


async def _post_to_hf(endpoint_url: str, headers: dict[str, str], wav_bytes: bytes) -> httpx.Response:
    async with httpx.AsyncClient(timeout=_HF_TIMEOUT) as client:
        last_response: httpx.Response | None = None
        for attempt, delay in enumerate((0.0, *_HF_RETRY_DELAYS_SECONDS), start=1):
            if delay > 0:
                await asyncio.sleep(delay)
            response = await client.post(endpoint_url, headers=headers, content=wav_bytes)
            if response.status_code == 200:
                return response

            last_response = response
            logger.warning(
                "HF endpoint returned status=%s on attempt=%s body=%s",
                response.status_code,
                attempt,
                _truncate_body(response.text),
            )
            if not _is_retryable_response(response):
                return response

        assert last_response is not None
        return last_response


@router.post("/transcribe")
async def transcribe_audio(request: Request, file: UploadFile = File(...)) -> dict[str, str]:
    settings = request.app.state.settings
    api_key = settings.hf_api_key
    endpoint_url = settings.hf_endpoint_url
    if not api_key or not endpoint_url:
        raise HTTPException(status_code=500, detail="語音辨識服務未設定。")

    audio_bytes = await file.read()
    src_mime = file.content_type or "audio/webm"
    try:
        wav_bytes = await _to_wav(audio_bytes, src_mime)
    except Exception as exc:
        logger.error("Audio conversion error: %s", exc)
        raise HTTPException(status_code=422, detail="音頻格式無法處理，請再試一次。")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "audio/wav",
        "X-Wait-For-Model": "true",
    }
    try:
        resp = await _post_to_hf(endpoint_url, headers=headers, wav_bytes=wav_bytes)
        if resp.status_code == 503:
            raise HTTPException(status_code=503, detail="語音辨識模型啟動中，請稍後再試一次。")
        if resp.status_code != 200:
            logger.error(
                "HF endpoint error: status=%s body=%s",
                resp.status_code,
                _truncate_body(resp.text),
            )
            raise HTTPException(status_code=502, detail="語音辨識失敗，請再試一次。")

        payload = resp.json()
        text = payload.get("text", "")
        if not isinstance(text, str):
            logger.error("HF endpoint returned invalid payload: %s", _truncate_body(resp.text))
            raise HTTPException(status_code=502, detail="語音辨識失敗，請再試一次。")
        return {"text": text}
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        logger.error("Transcription upstream timeout: %s", exc)
        raise HTTPException(status_code=504, detail="語音辨識服務逾時，請稍後再試一次。")
    except ValueError as exc:
        logger.error("Invalid transcription response: %s", exc)
        raise HTTPException(status_code=502, detail="語音辨識失敗，請再試一次。")
    except Exception as exc:
        logger.error("Transcription error: %s", exc)
        raise HTTPException(status_code=500, detail="語音處理失敗，請再試一次。")
