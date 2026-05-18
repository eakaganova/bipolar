import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


class EmotionalMetrics(BaseModel):
    mood_score: int | None = Field(default=None, ge=1, le=10)
    energy_score: int | None = Field(default=None, ge=1, le=10)
    anxiety_score: int | None = Field(default=None, ge=1, le=10)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    activation_level: int | None = Field(default=None, ge=1, le=10)
    depression_risk: int | None = Field(default=None, ge=1, le=10)
    mania_risk: int | None = Field(default=None, ge=1, le=10)
    suicidality_flag: bool
    medication_mentions: list[str] = Field(default_factory=list)
    social_activity: str = ""
    spending_behavior: str = ""
    cognitive_speed: int | None = Field(default=None, ge=1, le=10)
    summary: str = ""
    confidence_level: str = "low"
    needs_more_context: bool = True
    missing_context: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    sleep_pattern: str = ""
    appetite_pattern: str = ""
    irritability_signs: str = ""
    thought_speed_signs: str = ""
    impulsivity_signs: str = ""
    productivity_pattern: str = ""
    body_state: str = ""
    trigger_events: list[str] = Field(default_factory=list)
    protective_actions: list[str] = Field(default_factory=list)
    warning_signs: list[str] = Field(default_factory=list)
    pattern_hypothesis: str = ""

    @field_validator("medication_mentions", mode="before")
    @classmethod
    def normalize_medications(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @field_validator(
        "missing_context",
        "follow_up_questions",
        "trigger_events",
        "protective_actions",
        "warning_signs",
        mode="before",
    )
    @classmethod
    def normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @field_validator("confidence_level", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> str:
        text = str(value or "low").strip().lower()
        return text if text in {"low", "medium", "high"} else "low"

    @field_validator(
        "social_activity",
        "spending_behavior",
        "summary",
        "sleep_pattern",
        "appetite_pattern",
        "irritability_signs",
        "thought_speed_signs",
        "impulsivity_signs",
        "productivity_pattern",
        "body_state",
        "pattern_hypothesis",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()


def extract_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        logger.warning("Direct JSON parsing failed; trying object extraction")

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response does not contain a JSON object")

    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON is not an object")
    return parsed


def validate_metrics(raw_text: str) -> EmotionalMetrics:
    data = extract_json_object(raw_text)
    try:
        return EmotionalMetrics.model_validate(data)
    except ValidationError as exc:
        logger.warning("Metrics validation failed: %s", exc)
        raise


def metrics_to_json(metrics: EmotionalMetrics) -> str:
    return json.dumps(metrics.model_dump(), ensure_ascii=False)


def metrics_to_row(metrics: EmotionalMetrics) -> dict[str, Any]:
    row = metrics.model_dump()
    row["medication_mentions"] = ", ".join(metrics.medication_mentions)
    return row
