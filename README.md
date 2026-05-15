# Bipolar Voice Bot MVP

Telegram MVP for voice-first emotional self-observation. The bot receives a voice message, transcribes it, extracts stable structured metrics with an LLM, saves the entry to Google Sheets, and returns a short supportive reflection.

This is not a medical device, does not diagnose, and does not replace a clinician.

## Architecture

- `bot.py` - Telegram webhook server on `aiohttp`/`aiogram`, voice-message handling, user-facing statuses, graceful errors.
- `llm.py` - OpenAI Whisper or Yandex Realtime speech transcription, OpenAI or Yandex Cloud text LLM calls, JSON-only metrics extraction, supportive reflection generation, retries.
- `analysis.py` - safe JSON extraction and Pydantic validation layer.
- `sheets.py` - Google Sheets MVP database writer.
- `prompts.py` - medical-safety and JSON-stability prompts.
- `config.py` - environment variables and logging setup.

## Google Sheets Structure

Create a spreadsheet and a worksheet named `entries`.

Headers are created automatically in row 1:

```text
created_at, telegram_user_id, telegram_username, transcript, mood_score, energy_score,
anxiety_score, sleep_hours, activation_level, depression_risk, mania_risk,
suicidality_flag, medication_mentions, social_activity, spending_behavior,
cognitive_speed, summary
```

Share the spreadsheet with the `client_email` from your Google service account JSON.

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python bot.py
```

For local webhook testing, expose your local server with a tunnel and set `PUBLIC_BASE_URL` to the public HTTPS URL.

## Render Deployment

1. Push this repository to GitHub.
2. In Render, create a new Blueprint or Web Service from the repository.
3. Add environment variables from `.env.example`.
4. Set `PUBLIC_BASE_URL` to the deployed Render URL, for example `https://bipolar-voice-bot.onrender.com`.
5. Deploy. On startup, the app calls Telegram `setWebhook` automatically.
6. Render health checks use `GET /health`; Telegram updates go to `POST /webhook`.

## Required Environment Variables

- `TELEGRAM_BOT_TOKEN`
- `PUBLIC_BASE_URL`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON` or `GOOGLE_SERVICE_ACCOUNT_FILE`

For Yandex Cloud text generation, set:

- `TRANSCRIPTION_PROVIDER=yandex`
- `LLM_PROVIDER=yandex`
- `YANDEX_CLOUD_FOLDER`
- `YANDEX_CLOUD_API_KEY`
- `YANDEX_CLOUD_MODEL=gpt-oss-120b/latest`
- `YANDEX_SPEECH_MODEL=speech-realtime-250923/latest`
- `YANDEX_REALTIME_WSS_URL=wss://llm.api.cloud.yandex.net/v1/realtime`

When `TRANSCRIPTION_PROVIDER=yandex` and `LLM_PROVIDER=yandex`, `OPENAI_API_KEY` is not required. Telegram voice files are converted from OGG/Opus to LPCM with `ffmpeg`; Render installs it from `apt.txt`.

## Processing Flow

1. User sends a Telegram voice message.
2. Bot replies with `расшифровываю голосовое`.
3. Bot downloads audio and transcribes it with Whisper.
4. Bot changes status to `анализирую состояние`.
5. LLM returns JSON only.
6. `analysis.py` validates the JSON.
7. Bot changes status to `сохраняю запись`.
8. Entry is appended to Google Sheets.
9. Second LLM writes a short empathetic response.
10. Bot sends the response to the user.

## Next Product Steps

- Weekly summaries.
- Mood and risk charts.
- Phase-shift signal detection.
- PDF export for psychiatrist appointments.
- Semantic memory.
- Long-term trend analysis.
