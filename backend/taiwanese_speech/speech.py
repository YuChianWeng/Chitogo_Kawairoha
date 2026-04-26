import os
import logging
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("HF_API_KEY")
ENDPOINT_URL = os.getenv("HF_ENDPOINT_URL")

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    if not API_KEY or not ENDPOINT_URL:
        raise HTTPException(status_code=500, detail="Hugging Face API credentials not configured.")

    try:
        audio_bytes = await file.read()
        content_type = file.content_type or "audio/wav"
        
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": content_type
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(ENDPOINT_URL, headers=headers, content=audio_bytes)
            
            if response.status_code != 200:
                logger.error(f"HF Endpoint Error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Voice transcription failed, please try again later.")
                
            result = response.json()
            
            return {"text": result.get("text", "")}

    except Exception as e:
        logger.error(f"Transcription failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Voice processing failed, please try again later.")