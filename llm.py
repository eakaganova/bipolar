import asyncio
import base64
import json
import logging
import tempfile
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

import aiohttp
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
        self.transcription_client = self._make_openai_client()
        self.openai_client = self._make_openai_client()
        self.yandex_client = self._make_yandex_client()

    def _make_openai_client(self) -> AsyncOpenAI | None:
        if not self.settings.openai_api_key:
            return None
        return AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.request_timeout_seconds,
            max_retries=0,
        )

    def _make_yandex_client(self) -> AsyncOpenAI | None:
        if not self.settings.yandex_cloud_api_key or not self.settings.yandex_cloud_folder:
            return None
        return AsyncOpenAI(
            api_key=self.settings.yandex_cloud_api_key,
            base_url=self.settings.yandex_cloud_base_url,
            project=self.settings.yandex_cloud_folder,
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
        provider = self.settings.transcription_provider.lower().strip()
        if provider == "yandex":
            return await self._with_retries(
                "yandex realtime transcription",
                lambda: self._transcribe_voice_yandex_realtime(audio_bytes, filename),
            )
        return await self._with_retries(
            "voice transcription",
            lambda: self._transcribe_voice_openai(audio_bytes, filename),
        )

    async def _transcribe_voice_openai(self, audio_bytes: bytes, filename: str) -> str:
        async def operation() -> str:
            if self.transcription_client is None:
                raise RuntimeError("OPENAI_API_KEY is required for Whisper voice transcription")

            suffix = Path(filename).suffix or ".ogg"
            with tempfile.NamedTemporaryFile(suffix=suffix) as audio_file:
                audio_file.write(audio_bytes)
                audio_file.flush()
                with open(audio_file.name, "rb") as file_obj:
                    transcript = await self.transcription_client.audio.transcriptions.create(
                        model=self.settings.openai_transcription_model,
                        file=file_obj,
                        response_format="text",
                    )
            text = str(transcript).strip()
            if not text:
                raise ValueError("Empty transcription")
            logger.info("Transcription completed, %s chars", len(text))
            return text

        return await operation()

    async def _convert_to_pcm(self, audio_bytes: bytes, filename: str) -> bytes:
        suffix = Path(filename).suffix or ".ogg"
        with tempfile.NamedTemporaryFile(suffix=suffix) as input_file:
            input_file.write(audio_bytes)
            input_file.flush()
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                input_file.name,
                "-f",
                "s16le",
                "-acodec",
                "pcm_s16le",
                "-ac",
                "1",
                "-ar",
                str(self.settings.yandex_speech_input_rate),
                "pipe:1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error = stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg audio conversion failed: {error}")
        if not stdout:
            raise RuntimeError("ffmpeg produced empty PCM audio")
        return stdout

    async def _transcribe_voice_yandex_realtime(self, audio_bytes: bytes, filename: str) -> str:
        if not self.settings.yandex_cloud_api_key or not self.settings.yandex_cloud_folder:
            raise RuntimeError("Set YANDEX_CLOUD_FOLDER and YANDEX_CLOUD_API_KEY for Yandex speech transcription")

        pcm_audio = await self._convert_to_pcm(audio_bytes, filename)
        model_url = f"{self.settings.yandex_realtime_wss_url}?model={self.settings.yandex_speech_model_uri}"
        headers = {"Authorization": f"Api-Key {self.settings.yandex_cloud_api_key}"}
        transcript_parts: list[str] = []
        response_parts: list[str] = []

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(model_url, headers=headers, heartbeat=20.0) as ws:
                logger.info("Connected to Yandex Realtime API for transcription")
                await ws.send_json(
                    {
                        "type": "session.update",
                        "session": {
                            "instructions": (
                                "You are a speech transcription service. Return only the verbatim "
                                "transcript of the user's Russian audio. Do not add advice or comments."
                            ),
                            "output_modalities": ["text"],
                            "audio": {
                                "input": {
                                    "format": {
                                        "type": "audio/pcm",
                                        "rate": self.settings.yandex_speech_input_rate,
                                    },
                                    "languages": [self.settings.yandex_speech_language],
                                    "turn_detection": {
                                        "type": "server_vad",
                                        "threshold": 0.5,
                                        "silence_duration_ms": 400,
                                    },
                                }
                            },
                        },
                    }
                )

                chunk_size = self.settings.yandex_speech_input_rate
                for offset in range(0, len(pcm_audio), chunk_size):
                    chunk = pcm_audio[offset : offset + chunk_size]
                    await ws.send_json(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(chunk).decode("ascii"),
                        }
                    )

                await ws.send_json({"type": "input_audio_buffer.commit"})
                await ws.send_json({"type": "response.create"})

                deadline = asyncio.get_running_loop().time() + self.settings.request_timeout_seconds
                while asyncio.get_running_loop().time() < deadline:
                    timeout = max(0.1, deadline - asyncio.get_running_loop().time())
                    msg = await ws.receive(timeout=timeout)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        payload = json.loads(msg.data)
                        event_type = payload.get("type")

                        if event_type == "conversation.item.input_audio_transcription.completed":
                            transcript = (payload.get("transcript") or "").strip()
                            if transcript:
                                transcript_parts.append(transcript)

                        if event_type == "response.output_text.delta":
                            delta = payload.get("delta") or ""
                            if delta:
                                response_parts.append(delta)

                        if event_type in {"response.done", "response.completed"}:
                            break

                        if event_type == "error":
                            raise RuntimeError(f"Yandex Realtime API error: {payload}")

                    elif msg.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                        break

        text = " ".join(transcript_parts).strip() or "".join(response_parts).strip()
        if not text:
            raise RuntimeError("Yandex Realtime API returned empty transcription")
        logger.info("Yandex transcription completed, %s chars", len(text))
        return text

    async def _create_text_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        json_only: bool = False,
    ) -> str:
        provider = self.settings.llm_provider.lower().strip()

        if provider == "yandex":
            if self.yandex_client is None:
                raise RuntimeError("Set YANDEX_CLOUD_FOLDER and YANDEX_CLOUD_API_KEY for Yandex LLM")
            response = await self.yandex_client.responses.create(
                model=self.settings.yandex_model_uri,
                temperature=temperature,
                instructions=system_prompt,
                input=user_prompt,
                max_output_tokens=900 if json_only else 500,
            )
            text = getattr(response, "output_text", "") or ""
            return text.strip()

        if self.openai_client is None:
            raise RuntimeError("Set OPENAI_API_KEY or switch LLM_PROVIDER to yandex")

        kwargs = {}
        if json_only:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.openai_client.chat.completions.create(
            model=self.settings.openai_analysis_model if json_only else self.settings.openai_reflection_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **kwargs,
        )
        return (response.choices[0].message.content or "").strip()

    async def analyze_transcript(self, transcript: str) -> EmotionalMetrics:
        async def operation() -> EmotionalMetrics:
            content = await self._create_text_response(
                system_prompt=ANALYSIS_SYSTEM_PROMPT,
                user_prompt=ANALYSIS_USER_TEMPLATE.format(transcript=transcript),
                temperature=0,
                json_only=True,
            )
            metrics = validate_metrics(content)
            logger.info("Analysis completed: suicidality_flag=%s", metrics.suicidality_flag)
            return metrics

        return await self._with_retries("transcript analysis", operation)

    async def write_reflection(self, transcript: str, metrics: EmotionalMetrics) -> str:
        async def operation() -> str:
            text = await self._create_text_response(
                system_prompt=REFLECTION_SYSTEM_PROMPT,
                user_prompt=REFLECTION_USER_TEMPLATE.format(
                    transcript=transcript,
                    metrics_json=metrics_to_json(metrics),
                ),
                temperature=0.6,
            )
            if not text:
                raise ValueError("Empty reflection")
            logger.info("Reflection completed, %s chars", len(text))
            return text

        return await self._with_retries("supportive reflection", operation)
