import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import gspread

from analysis import EmotionalMetrics, metrics_to_row
from config import get_settings

logger = logging.getLogger(__name__)


HEADERS = [
    "created_at",
    "telegram_user_id",
    "telegram_username",
    "transcript",
    "mood_score",
    "energy_score",
    "anxiety_score",
    "sleep_hours",
    "activation_level",
    "depression_risk",
    "mania_risk",
    "suicidality_flag",
    "medication_mentions",
    "social_activity",
    "spending_behavior",
    "cognitive_speed",
    "summary",
]


class SheetsStorage:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._worksheet = None

    def _connect(self) -> Any:
        if self._worksheet is not None:
            return self._worksheet

        credentials = self.settings.google_credentials()
        if isinstance(credentials, dict):
            client = gspread.service_account_from_dict(credentials)
        else:
            client = gspread.service_account(filename=credentials)

        spreadsheet = client.open_by_key(self.settings.google_sheet_id)
        self._worksheet = spreadsheet.worksheet(self.settings.google_worksheet_name)
        self._ensure_headers()
        logger.info("Connected to Google Sheets worksheet %s", self.settings.google_worksheet_name)
        return self._worksheet

    def _ensure_headers(self) -> None:
        current_headers = self._worksheet.row_values(1)
        if current_headers != HEADERS:
            self._worksheet.update("A1:Q1", [HEADERS])
            logger.info("Google Sheets headers created or refreshed")

    def _append_entry_sync(
        self,
        user_id: int,
        username: str | None,
        transcript: str,
        metrics: EmotionalMetrics,
    ) -> None:
        worksheet = self._connect()
        metric_row = metrics_to_row(metrics)
        row = [
            datetime.now(timezone.utc).isoformat(),
            user_id,
            username or "",
            transcript,
            metric_row["mood_score"],
            metric_row["energy_score"],
            metric_row["anxiety_score"],
            metric_row["sleep_hours"],
            metric_row["activation_level"],
            metric_row["depression_risk"],
            metric_row["mania_risk"],
            metric_row["suicidality_flag"],
            metric_row["medication_mentions"],
            metric_row["social_activity"],
            metric_row["spending_behavior"],
            metric_row["cognitive_speed"],
            metric_row["summary"],
        ]
        worksheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info("Entry saved for telegram_user_id=%s", user_id)

    async def append_entry(
        self,
        user_id: int,
        username: str | None,
        transcript: str,
        metrics: EmotionalMetrics,
    ) -> None:
        await asyncio.to_thread(self._append_entry_sync, user_id, username, transcript, metrics)
