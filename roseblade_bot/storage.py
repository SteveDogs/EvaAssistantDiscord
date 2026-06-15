"""
EVA Assistant persistent state storage.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


DEFAULT_STATE: dict[str, Any] = {"guilds": {}}


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return deepcopy(DEFAULT_STATE)

        try:
            with self.path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            return deepcopy(DEFAULT_STATE)

        if not isinstance(payload, dict):
            return deepcopy(DEFAULT_STATE)

        payload.setdefault("guilds", {})
        return payload

    def save(self) -> None:
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(self._state, file, ensure_ascii=False, indent=2)

    def get_guild(self, guild_id: int) -> dict[str, Any]:
        guild_key = str(guild_id)
        guilds = self._state.setdefault("guilds", {})
        guild = guilds.setdefault(
            guild_key,
            {
                "category_id": None,
                "channels": {},
                "colors": {},
                "enabled_events": {},
                "ignored": {
                    "channel_ids": [],
                    "category_ids": [],
                    "user_ids": [],
                    "role_ids": [],
                },
                "next_case_id": 1,
            },
        )
        guild.setdefault("channels", {})
        guild.setdefault("colors", {})
        guild.setdefault("enabled_events", {})
        ignored = guild.setdefault("ignored", {})
        ignored.setdefault("channel_ids", [])
        ignored.setdefault("category_ids", [])
        ignored.setdefault("user_ids", [])
        ignored.setdefault("role_ids", [])
        guild.setdefault("next_case_id", 1)
        return guild

    def update_guild(
        self,
        guild_id: int,
        *,
        category_id: int | None = None,
        channels: dict[str, int] | None = None,
        colors: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        guild = self.get_guild(guild_id)
        if category_id is not None:
            guild["category_id"] = category_id
        if channels:
            guild["channels"].update(channels)
        if colors:
            guild["colors"].update(colors)
        self.save()
        return guild

    def remove_color_override(self, guild_id: int, event_key: str) -> None:
        guild = self.get_guild(guild_id)
        guild["colors"].pop(event_key, None)
        self.save()

    def set_event_enabled(self, guild_id: int, event_key: str, enabled: bool) -> None:
        guild = self.get_guild(guild_id)
        guild["enabled_events"][event_key] = enabled
        self.save()

    def is_event_enabled(self, guild_id: int, event_key: str) -> bool:
        guild = self.get_guild(guild_id)
        return guild["enabled_events"].get(event_key, True)

    def get_ignored_ids(self, guild_id: int, ignore_key: str) -> set[int]:
        guild = self.get_guild(guild_id)
        return {int(value) for value in guild["ignored"].get(ignore_key, [])}

    def add_ignored_id(self, guild_id: int, ignore_key: str, object_id: int) -> None:
        guild = self.get_guild(guild_id)
        values = {int(value) for value in guild["ignored"].get(ignore_key, [])}
        values.add(int(object_id))
        guild["ignored"][ignore_key] = sorted(values)
        self.save()

    def remove_ignored_id(self, guild_id: int, ignore_key: str, object_id: int) -> None:
        guild = self.get_guild(guild_id)
        values = {int(value) for value in guild["ignored"].get(ignore_key, [])}
        values.discard(int(object_id))
        guild["ignored"][ignore_key] = sorted(values)
        self.save()

    def next_case_id(self, guild_id: int) -> int:
        guild = self.get_guild(guild_id)
        case_id = int(guild.get("next_case_id", 1))
        guild["next_case_id"] = case_id + 1
        self.save()
        return case_id
