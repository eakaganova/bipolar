import asyncio
import base64
import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

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


class EntryStorage:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def append_entry(
        self,
        user_id: int,
        username: str | None,
        transcript: str,
        metrics: EmotionalMetrics,
    ) -> None:
        provider = self.settings.storage_provider.lower().strip()
        if provider == "github_csv":
            await self._append_entry_github_csv(user_id, username, transcript, metrics)
            return
        if provider == "local_csv":
            await asyncio.to_thread(self._append_entry_local_csv, user_id, username, transcript, metrics)
            return
        raise ValueError("Set STORAGE_PROVIDER to github_csv or local_csv")

    def _entry_dict(
        self,
        user_id: int,
        username: str | None,
        transcript: str,
        metrics: EmotionalMetrics,
    ) -> dict[str, Any]:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "telegram_user_id": user_id,
            "telegram_username": username or "",
            "transcript": transcript,
            **metrics_to_row(metrics),
        }

    def _append_entry_local_csv(
        self,
        user_id: int,
        username: str | None,
        transcript: str,
        metrics: EmotionalMetrics,
    ) -> None:
        path = Path(self.settings.local_csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists() and path.stat().st_size > 0
        with path.open("a", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=HEADERS)
            if not exists:
                writer.writeheader()
            writer.writerow(self._entry_dict(user_id, username, transcript, metrics))
        logger.info("Entry saved to local CSV for telegram_user_id=%s", user_id)

    async def _append_entry_github_csv(
        self,
        user_id: int,
        username: str | None,
        transcript: str,
        metrics: EmotionalMetrics,
    ) -> None:
        if not self.settings.github_token or not self.settings.github_repo:
            raise ValueError("Set GITHUB_TOKEN and GITHUB_REPO for github_csv storage")

        api_url = f"https://api.github.com/repos/{self.settings.github_repo}/contents/{self.settings.github_csv_path}"
        headers = {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "bipolar-voice-bot",
        }
        params = {"ref": self.settings.github_branch}
        current_csv = ""
        sha = None

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(api_url, params=params) as response:
                if response.status == 200:
                    payload = await response.json()
                    sha = payload.get("sha")
                    encoded = payload.get("content", "")
                    current_csv = base64.b64decode(encoded).decode("utf-8") if encoded else ""
                elif response.status != 404:
                    text = await response.text()
                    raise RuntimeError(f"GitHub CSV read failed: {response.status} {text}")

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=HEADERS)
            if current_csv.strip():
                output.write(current_csv)
                if not current_csv.endswith("\n"):
                    output.write("\n")
            else:
                writer.writeheader()

            writer.writerow(self._entry_dict(user_id, username, transcript, metrics))
            content = base64.b64encode(output.getvalue().encode("utf-8")).decode("ascii")

            body = {
                "message": "Add mood journal entry",
                "content": content,
                "branch": self.settings.github_branch,
            }
            if sha:
                body["sha"] = sha

            async with session.put(api_url, json=body) as response:
                text = await response.text()
                if response.status >= 400:
                    raise RuntimeError(f"GitHub CSV write failed: {response.status} {text}")
                logger.info("Entry saved to GitHub CSV for telegram_user_id=%s", user_id)
