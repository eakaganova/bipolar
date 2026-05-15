import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from openai import AsyncOpenAI

from analysis import EmotionalMetrics, metrics_to_json, validate_metrics
from config import get_settings
from prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    ANALYSIS_USER_TEMPLATE,
    REFLECTION_SYSTEM_PROMPT,
    REFLECTION_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.request_timeout_seconds,
            max_retries=0,
        )

    async def _with_retries(self, label: str, operation: Callable[[], Awaitable[T]]) -> T:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                logger.info("%s attempt %s/%s", label, attempt, self.settings.max_retries)
                return await operation()
            except Exception as exc:
                last_error = exc
                logger.warning("%s failed on attempt %s: %s", label, attempt, exc)
                if attempt < self.settings.max_retries:
                    await asyncio.sleep(1.5 * attempt)
        raise RuntimeError(f"{label} failed after retries") from last_error

    async def transcribe_voice(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        async def operation() -> str:
            suffix = Path(filename).suffix or ".ogg"
            with tempfile.NamedTemporaryFile(suffix=suffix) as audio_file:
                audio_file.write(audio_bytes)
                audio_file.flush()
                with open(audio_file.name, "rb") as file_obj:
                    transcript = await self.client.audio.transcriptions.create(
                        model=self.settings.openai_transcription_model,
                        file=file_obj,
                        response_format="text",
                    )
            text = str(transcript).strip()
            if not text:
                raise ValueError("Empty transcription")
            logger.info("Transcription completed, %s chars", len(text))
            return text

        return await self._with_retries("voice transcription", operation)

    async def analyze_transcript(self, transcript: str) -> EmotionalMetrics:
        async def operation() -> EmotionalMetrics:
            response = await self.client.chat.completions.create(
                model=self.settings.openai_analysis_model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": ANALYSIS_USER_TEMPLATE.format(transcript=transcript)},
                ],
            )
            content = response.choices[0].message.content or ""
            metrics = validate_metrics(content)
            logger.info("Analysis completed: suicidality_flag=%s", metrics.suicidality_flag)
            return metrics

        return await self._with_retries("transcript analysis", operation)

    async def write_reflection(self, transcript: str, metrics: EmotionalMetrics) -> str:
        async def operation() -> str:
            response = await self.client.chat.completions.create(
                model=self.settings.openai_reflection_model,
                temperature=0.6,
                messages=[
                    {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": REFLECTION_USER_TEMPLATE.format(
                            transcript=transcript,
                            metrics_json=metrics_to_json(metrics),
                        ),
                    },
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise ValueError("Empty reflection")
            logger.info("Reflection completed, %s chars", len(text))
            return text

        return await self._with_retries("supportive reflection", operation)
