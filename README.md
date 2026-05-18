# Bipolar Text Bot MVP

Telegram MVP for text-first emotional self-observation. The user writes a short text message, the bot extracts structured metrics with an LLM, saves only metrics to CSV storage, and returns a short supportive reflection.

This is not a medical device, does not diagnose, and does not replace a clinician.

## Architecture

- `bot.py` - Telegram webhook server, text-message handling, statuses, graceful errors.
- `llm.py` - Yandex/OpenAI text LLM calls and retries.
- `analysis.py` - safe JSON extraction and Pydantic validation layer.
- `storage.py` - `github_csv` storage for Render and `local_csv` for local testing. It stores metrics only, not the original user text.
- `prompts.py` - safety and JSON-stability prompts.
- `config.py` - environment variables and logging setup.

## Render Environment

```text
PYTHON_VERSION=3.11.9
TELEGRAM_BOT_TOKEN=<telegram bot token>
PUBLIC_BASE_URL=https://bipolar-k8ur.onrender.com

LLM_PROVIDER=yandex
YANDEX_CLOUD_FOLDER=<folder id>
YANDEX_CLOUD_API_KEY=<api key>
YANDEX_CLOUD_MODEL=gpt-oss-120b/latest
YANDEX_CLOUD_BASE_URL=https://ai.api.cloud.yandex.net/v1
REFLECTION_MAX_OUTPUT_TOKENS=1200
DEBUG_ERRORS=false

STORAGE_PROVIDER=github_csv
GITHUB_REPO=eakaganova/bipolar
GITHUB_BRANCH=data
GITHUB_CSV_PATH=data/entries.csv
GITHUB_TOKEN=<private GitHub token with contents read/write>
```

Use a private repository for real user entries because the CSV may contain sensitive notes. Prefer a separate `data` branch so saved entries do not trigger Render redeploys from `main`.

## Processing Flow

1. User sends a text message.
2. Bot replies with `анализирую состояние`.
3. LLM returns JSON only.
4. `analysis.py` validates the JSON.
5. Bot changes status to `сохраняю запись`.
6. Metrics are appended to CSV storage. The original text is not saved.
7. Second LLM writes a short empathetic response.
8. Bot sends the response to the user.

## Local Testing

```text
STORAGE_PROVIDER=local_csv
LOCAL_CSV_PATH=data/entries.csv
```

Then run:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

## CSV Headers

```text
created_at, telegram_user_id, telegram_username, mood_score, energy_score,
anxiety_score, sleep_hours, activation_level, depression_risk, mania_risk,
suicidality_flag, medication_mentions, social_activity, spending_behavior,
cognitive_speed, confidence_level, needs_more_context, missing_context,
sleep_pattern, appetite_pattern, irritability_signs, thought_speed_signs,
impulsivity_signs, productivity_pattern, body_state, trigger_events,
protective_actions, warning_signs, pattern_hypothesis
```

## Next Product Steps

- Weekly summaries.
- Charts.
- Phase-shift signal detection.
- PDF export for psychiatrist appointments.
- Semantic memory.
- Long-term trend analysis.
