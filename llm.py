import asyncio
import logging
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
            if json_only:
                system_prompt = (
                    system_prompt
                    + "\n\nCritical output rule: return a single raw JSON object only. "
                    + "No prose, no markdown, no code fences, no explanation before or after JSON."
                )
            response = await self.yandex_client.responses.create(
                model=self.settings.yandex_model_uri,
                temperature=temperature,
                instructions=system_prompt,
                input=user_prompt,
                max_output_tokens=(
                    self.settings.analysis_max_output_tokens
                    if json_only
                    else self.settings.reflection_max_output_tokens
                ),
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

    async def analyze_text(self, text: str) -> EmotionalMetrics:
        async def operation() -> EmotionalMetrics:
            content = await self._create_text_response(
                system_prompt=ANALYSIS_SYSTEM_PROMPT,
                user_prompt=ANALYSIS_USER_TEMPLATE.format(transcript=text),
                temperature=0,
                json_only=True,
            )
            metrics = validate_metrics(content)
            logger.info("Analysis completed: suicidality_flag=%s", metrics.suicidality_flag)
            return metrics

        try:
            return await self._with_retries("text analysis", operation)
        except Exception as exc:
            logger.exception("Structured analysis failed; falling back to low-confidence context request: %s", exc)
            return EmotionalMetrics(
                mood_score=None,
                energy_score=None,
                anxiety_score=None,
                sleep_hours=None,
                activation_level=None,
                depression_risk=None,
                mania_risk=None,
                suicidality_flag=False,
                medication_mentions=[],
                social_activity="",
                spending_behavior="",
                cognitive_speed=None,
                summary="Structured analysis failed; ask for more context.",
                confidence_level="low",
                needs_more_context=True,
                missing_context=[
                    "sleep",
                    "energy",
                    "anxiety",
                    "impulsivity",
                    "events before the state changed",
                ],
                follow_up_questions=[
                    "Как ты спал(а) последние 1-3 ночи?",
                    "Энергии сейчас больше, меньше или примерно как обычно?",
                    "Есть ли импульс резко что-то менять, писать, покупать или принимать решения?",
                ],
                sleep_pattern="not described",
                appetite_pattern="not described",
                irritability_signs="not described",
                thought_speed_signs="not described",
                impulsivity_signs="not described",
                productivity_pattern="not described",
                body_state="not described",
                trigger_events=[],
                protective_actions=[],
                warning_signs=[],
                pattern_hypothesis="insufficient context",
            )

    async def write_reflection(self, text: str, metrics: EmotionalMetrics, history_context: str) -> str:
        async def operation() -> str:
            response_text = await self._create_text_response(
                system_prompt=REFLECTION_SYSTEM_PROMPT,
                user_prompt=REFLECTION_USER_TEMPLATE.format(
                    transcript=text,
                    metrics_json=metrics_to_json(metrics),
                    history_context=history_context,
                ),
                temperature=0.6,
            )
            if not response_text:
                raise ValueError("Empty reflection")
            logger.info("Reflection completed, %s chars", len(response_text))
            return response_text

        return await self._with_retries("supportive reflection", operation)
