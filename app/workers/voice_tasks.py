"""Voice processing background tasks."""
from app.workers.celery_config import celery_app
from app.core.logging import get_logger
import asyncio

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=2, queue="voice")
def transcribe_audio(self, audio_data: bytes, filename: str = "audio.mp3"):
    """Transcribe audio file asynchronously."""
    try:
        from app.services.voice_service import voice_service
        result = asyncio.get_event_loop().run_until_complete(
            voice_service.transcribe(audio_data, filename)
        )
        logger.info("audio_transcribed_async")
        return result
    except Exception as exc:
        logger.error("transcribe_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=10)


@celery_app.task(bind=True, max_retries=2, queue="voice")
def generate_speech(self, text: str, voice: str = None):
    """Generate TTS audio asynchronously."""
    try:
        from app.services.voice_service import voice_service
        result = asyncio.get_event_loop().run_until_complete(
            voice_service.text_to_speech(text, voice)
        )
        logger.info("tts_generated_async")
        return {"status": "success", "audio_url": result.get("audio_url")}
    except Exception as exc:
        logger.error("tts_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=10)
