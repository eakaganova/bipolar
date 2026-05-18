from statistics import mean
from typing import Any

from analysis import EmotionalMetrics


NUMERIC_FIELDS = [
    "mood_score",
    "energy_score",
    "anxiety_score",
    "sleep_hours",
    "activation_level",
    "depression_risk",
    "mania_risk",
    "cognitive_speed",
]

PATTERN_FIELDS = [
    "sleep_pattern",
    "appetite_pattern",
    "irritability_signs",
    "thought_speed_signs",
    "impulsivity_signs",
    "productivity_pattern",
    "body_state",
    "trigger_events",
    "protective_actions",
    "warning_signs",
    "pattern_hypothesis",
]


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _trend_word(delta: float) -> str:
    if delta >= 1:
        return "higher"
    if delta <= -1:
        return "lower"
    return "about the same"


def _format_delta(delta: float) -> str:
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.1f}"


def build_history_context(history: list[dict[str, Any]], current_metrics: EmotionalMetrics) -> str:
    if not history:
        return (
            "No previous entries are available for this user yet. "
            "Do not infer long-term dynamics; analyze only the current entry."
        )

    history = history[-100:]
    current = current_metrics.model_dump()
    lines = [f"Previous entries available: {len(history)}."]

    latest = history[-1]
    last_question = str(latest.get("bot_question", "")).strip()
    if last_question:
        lines.append(f"Last question the bot asked the user: {last_question}")
        lines.append("The current user message may be an answer to that question. Use it as dialogue continuity if relevant.")

    lines.append("Current entry compared with the latest previous entry:")
    for field in NUMERIC_FIELDS:
        previous_value = _to_float(latest.get(field))
        current_value = _to_float(current.get(field))
        if previous_value is None or current_value is None:
            continue
        delta = current_value - previous_value
        lines.append(f"- {field}: {current_value:g} now vs {previous_value:g} before ({_format_delta(delta)}, {_trend_word(delta)}).")

    recent = history[-7:]
    older = history[-14:-7]
    if recent:
        lines.append("Recent baseline from previous entries:")
        for field in NUMERIC_FIELDS:
            recent_values = [_to_float(row.get(field)) for row in recent]
            recent_values = [value for value in recent_values if value is not None]
            if not recent_values:
                continue
            recent_avg = mean(recent_values)
            current_value = _to_float(current.get(field))
            if current_value is None:
                lines.append(f"- {field}: recent average {recent_avg:.1f}.")
                continue
            delta = current_value - recent_avg
            lines.append(f"- {field}: current {current_value:g}, recent average {recent_avg:.1f} ({_format_delta(delta)}).")

    if older:
        lines.append("Recent 7 previous entries compared with the 7 entries before them:")
        for field in NUMERIC_FIELDS:
            recent_values = [_to_float(row.get(field)) for row in recent]
            older_values = [_to_float(row.get(field)) for row in older]
            recent_values = [value for value in recent_values if value is not None]
            older_values = [value for value in older_values if value is not None]
            if not recent_values or not older_values:
                continue
            delta = mean(recent_values) - mean(older_values)
            lines.append(f"- {field}: recent average shifted by {_format_delta(delta)}.")

    pattern_lines = []
    for row in history[-10:]:
        parts = []
        for field in PATTERN_FIELDS:
            value = str(row.get(field, "")).strip()
            if value:
                parts.append(f"{field}={value[:120]}")
        if parts:
            pattern_lines.append("; ".join(parts))

    if pattern_lines:
        lines.append("Recent structured symptom/pattern notes from previous entries:")
        for line in pattern_lines[-5:]:
            lines.append(f"- {line}")

    return "\n".join(lines)
