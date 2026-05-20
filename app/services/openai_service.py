"""OpenAI service — direct OpenAI API wrapper with retry and cost tracking."""
from openai import AsyncOpenAI
from typing import List, Dict, Optional
from app.core.config import settings
from app.core.constants import MODEL_PRICING
from app.core.logging import get_logger

logger = get_logger(__name__)


class OpenAIService:
    """Wrapper around OpenAI API with cost tracking."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = None,
    ) -> Dict:
        """Call chat completions API, return full response object."""
        model = model or settings.OPENAI_MODEL
        max_tokens = max_tokens or settings.MAX_OUTPUT_TOKENS

        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        usage = response.usage
        cost = self._calculate_cost(usage.prompt_tokens, usage.completion_tokens, model)

        logger.info(
            "openai_call",
            model=model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost=cost,
        )

        return {
            "content": response.choices[0].message.content,
            "model": model,
            "input_tokens": usage.prompt_tokens,
            "output_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cost": cost,
        }

    async def embed(self, text: str, model: str = None) -> List[float]:
        """Generate embedding via OpenAI API."""
        model = model or settings.OPENAI_EMBEDDINGS_MODEL
        response = await self.client.embeddings.create(input=text, model=model)
        return response.data[0].embedding

    async def transcribe(self, audio_data: bytes, filename: str = "audio.mp3") -> str:
        """Transcribe audio using Whisper."""
        import io
        audio_file = io.BytesIO(audio_data)
        audio_file.name = filename
        response = await self.client.audio.transcriptions.create(
            model=settings.WHISPER_MODEL,
            file=audio_file,
        )
        return response.text

    async def text_to_speech(self, text: str, voice: str = None) -> bytes:
        """Convert text to speech."""
        voice = voice or settings.TTS_VOICE
        response = await self.client.audio.speech.create(
            model=settings.TTS_MODEL,
            voice=voice,
            input=text,
        )
        return response.content

    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-4o-mini"))
        return (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]


openai_service = OpenAIService()
