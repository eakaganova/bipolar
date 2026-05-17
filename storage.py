import asyncio
import base64
import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from analysis import EmotionalMetrics
from config import get_settings

logger = logging.getLogger(__name__)


HEADERS = [
    "created_at",
    "telegram_user_id",
    "telegram_username",
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

    async def get_recent_entries(self, user_id: int, limit: int = 100) -> list[dict[str, Any]]:
        provider = self.settings.storage_provider.lower().strip()
        if provider == "github_csv":
            rows = await self._read_github_csv()
        elif provider == "local_csv":
            rows = await asyncio.to_thread(self._read_local_csv)
        else:
            raise ValueError("Set STORAGE_PROVIDER to github_csv or local_csv")

        user_rows = [
            row
            for row in rows
            if str(row.get("telegram_user_id", "")).strip() == str(user_id)
        ]
        return user_rows[-limit:]

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
            "mood_score": metrics.mood_score,
            "energy_score": metrics.energy_score,
            "anxiety_score": metrics.anxiety_score,
            "sleep_hours": metrics.sleep_hours,
            "activation_level": metrics.activation_level,
            "depression_risk": metrics.depression_risk,
            "mania_risk": metrics.mania_risk,
            "suicidality_flag": metrics.suicidality_flag,
            "medication_mentions": ", ".join(metrics.medication_mentions),
            "social_activity": metrics.social_activity,
            "spending_behavior": metrics.spending_behavior,
            "cognitive_speed": metrics.cognitive_speed,
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
        existing_rows = self._read_local_csv()
        existing_rows.append(self._entry_dict(user_id, username, transcript, metrics))
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=HEADERS)
            writer.writeheader()
            for row in existing_rows:
                writer.writerow({field: row.get(field, "") for field in HEADERS})
        logger.info("Entry saved to local CSV for telegram_user_id=%s", user_id)

    def _read_local_csv(self) -> list[dict[str, Any]]:
        path = Path(self.settings.local_csv_path)
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", newline="", encoding="utf-8") as csv_file:
            return list(csv.DictReader(csv_file))

    async def _read_github_csv(self) -> list[dict[str, Any]]:
        if not self.settings.github_token or not self.settings.github_repo:
            raise ValueError("Set GITHUB_TOKEN and GITHUB_REPO for github_csv storage")

        api_url = f"https://api.github.com/repos/{self.settings.github_repo}/contents/{self.settings.github_csv_path}"
        headers = {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "bipolar-text-bot",
        }
        params = {"ref": self.settings.github_branch}

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(api_url, params=params) as response:
                if response.status == 404:
                    return []
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(f"GitHub CSV read failed: {response.status} {text}")
                payload = await response.json()
                encoded = payload.get("content", "")
                current_csv = base64.b64decode(encoded).decode("utf-8") if encoded else ""

        if not current_csv.strip():
            return []
        return list(csv.DictReader(io.StringIO(current_csv)))

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
            "User-Agent": "bipolar-text-bot",
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

            existing_rows = list(csv.DictReader(io.StringIO(current_csv))) if current_csv.strip() else []
            existing_rows.append(self._entry_dict(user_id, username, transcript, metrics))

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=HEADERS)
            writer.writeheader()
            for row in existing_rows:
                writer.writerow({field: row.get(field, "") for field in HEADERS})
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
