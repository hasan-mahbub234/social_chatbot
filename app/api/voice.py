"""Voice API routes."""
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.voice_service import voice_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Transcribe audio file to text using OpenAI Whisper."""
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

        result = await voice_service.transcribe(content, file.filename or "audio.mp3")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")


@router.post("/text-to-speech")
async def text_to_speech(
    text: str = Form(...),
    voice: str = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Convert text to speech audio."""
    try:
        if not text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text is required")

        result = await voice_service.text_to_speech(text, voice)
        return {
            "audio_url": result.get("audio_url"),
            "voice": result.get("voice"),
            "model": result.get("model"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail="TTS generation failed")
