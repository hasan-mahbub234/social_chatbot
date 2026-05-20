"""Voice service — transcription and TTS via OpenAI."""
from typing import Optional
from app.services.openai_service import openai_service
from app.integrations.s3 import s3_service
from app.core.config import settings
from app.core.logging import get_logger
from uuid import uuid4

logger = get_logger(__name__)


class VoiceService:
    """Handle voice transcription and text-to-speech."""

    async def transcribe(self, audio_data: bytes, filename: str = "audio.mp3") -> dict:
        """Transcribe audio to text using Whisper."""
        try:
            text = await openai_service.transcribe(audio_data, filename)
            logger.info("audio_transcribed", length=len(audio_data))
            return {
                "transcription": text,
                "language": "en",
                "model": settings.WHISPER_MODEL,
            }
        except Exception as e:
            logger.error("transcription_failed", error=str(e))
            raise

    async def text_to_speech(self, text: str, voice: str = None) -> dict:
        """Convert text to speech audio."""
        try:
            audio_bytes = await openai_service.text_to_speech(text, voice)

            # Optionally upload to S3
            audio_key = None
            try:
                key = f"voice/tts/{uuid4()}.mp3"
                await s3_service.upload(audio_bytes, key, "audio/mpeg")
                audio_key = s3_service.get_presigned_url(key, expiry=3600)
            except Exception:
                pass  # S3 optional

            logger.info("tts_generated", text_length=len(text))
            return {
                "audio_url": audio_key,
                "audio_bytes": audio_bytes if not audio_key else None,
                "voice": voice or settings.TTS_VOICE,
                "model": settings.TTS_MODEL,
            }
        except Exception as e:
            logger.error("tts_failed", error=str(e))
            raise


voice_service = VoiceService()
