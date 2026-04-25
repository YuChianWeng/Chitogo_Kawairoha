from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/speech", tags=["speech"])


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict[str, str]:
    api_key = os.getenv("HF_API_KEY")
    endpoint_url = os.getenv("HF_ENDPOINT_URL")
    if not api_key or not endpoint_url:
        raise HTTPException(status_code=500, detail="語音辨識服務未設定。")

    audio_bytes = await file.read()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "audio/wav"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint_url, headers=headers, content=audio_bytes)
        if resp.status_code != 200:
            logger.error("HF endpoint error: %s", resp.text)
            raise HTTPException(status_code=502, detail="語音辨識失敗，請再試一次。")
        return {"text": resp.json().get("text", "")}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Transcription error: %s", exc)
        raise HTTPException(status_code=500, detail="語音處理失敗，請再試一次。")
