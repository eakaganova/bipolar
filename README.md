# Bipolar Voice Bot MVP

Telegram MVP for voice-first emotional self-observation. The bot receives a voice message, transcribes it, extracts stable structured metrics with an LLM, saves the entry to CSV storage, and returns a short supportive reflection.

This is not a medical device, does not diagnose, and does not replace a clinician.

## Architecture

- `bot.py` - Telegram webhook server on `aiohttp`/`aiogram`, voice-message handling, statuses, graceful errors.
- `llm.py` - Yandex Realtime speech transcription, Yandex/OpenAI text LLM calls, retries.
- `analysis.py` - safe JSON extraction and Pydantic validation layer.
- `storage.py` - storage layer with `github_csv` for Render and `local_csv` for local testing.
- `prompts.py` - safety and JSON-stability prompts.
- `config.py` - environment variables and logging setup.

## Storage

No Google Sheets are required.

Render default:

```text
STORAGE_PROVIDER=github_csv
GITHUB_REPO=eakaganova/bipolar
GITHUB_BRANCH=data
GITHUB_CSV_PATH=data/entries.csv
GITHUB_TOKEN=<private GitHub token with contents read/write>
```

Use a private repository for real user entries because the CSV may contain sensitive notes. Prefer a separate `data` branch so every saved entry does not trigger a Render redeploy of `main`.

Local testing:

```text
STORAGE_PROVIDER=local_csv
LOCAL_CSV_PATH=data/entries.csv
```

CSV headers:

```text
created_at, telegram_user_id, telegram_username, transcript, mood_score, energy_score,
anxiety_score, sleep_hours, activation_level, depression_risk, mania_risk,
suicidality_flag, medication_mentions, social_activity, spending_behavior,
cognitive_speed, summary
```

## Render Deployment

1. Push this repository to GitHub.
2. Create a Python Web Service on Render.
3. Add environment variables from `.env.example`.
4. Set `PUBLIC_BASE_URL` to the Render service URL, for example `https://bipolar-voice-bot.onrender.com`.
5. Set `PYTHON_VERSION=3.11.9`.
6. Deploy. On startup, the app sets Telegram webhook automatically.

Render health checks use `GET /health`; Telegram updates go to `POST /webhook`.

## Required Environment Variables

- `TELEGRAM_BOT_TOKEN`
- `PUBLIC_BASE_URL`
- `TRANSCRIPTION_PROVIDER=yandex`
- `LLM_PROVIDER=yandex`
- `YANDEX_CLOUD_FOLDER`
- `YANDEX_CLOUD_API_KEY`
- `YANDEX_CLOUD_MODEL=gpt-oss-120b/latest`
- `YANDEX_SPEECH_MODEL=speech-realtime-250923/latest`
- `YANDEX_REALTIME_WSS_URL=wss://llm.api.cloud.yandex.net/v1/realtime`
- `STORAGE_PROVIDER=github_csv`
- `GITHUB_REPO`
- `GITHUB_BRANCH`
- `GITHUB_CSV_PATH`
- `GITHUB_TOKEN`

When both providers are Yandex, `OPENAI_API_KEY` is not required. Telegram voice files are converted from OGG/Opus to LPCM with `ffmpeg`; Render installs it from `apt.txt`.

## Processing Flow

1. User sends a Telegram voice message.
2. Bot replies with `расшифровываю голосовое`.
3. Bot downloads audio and transcribes it with Yandex Realtime.
4. Bot changes status to `анализирую состояние`.
5. LLM returns JSON only.
6. `analysis.py` validates the JSON.
7. Bot changes status to `сохраняю запись`.
8. Entry is appended to CSV storage.
9. Second LLM writes a short empathetic response.
10. Bot sends the response to the user.

## Next Product Steps

- Weekly summaries.
- Charts.
- Phase-shift signal detection.
- PDF export for psychiatrist appointments.
- Semantic memory.
- Long-term trend analysis.
