"""
EVA Assistant audit history service.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import io
import json
from typing import Any, Callable

import discord

from roseblade_bot.storage import JsonStateStore


class AuditHistoryService:
    def __init__(self, store: JsonStateStore, *, display_name: Callable[[Any], str]) -> None:
        self.store = store
        self.display_name = display_name
        self.history_path = store.path.parent / "audit_history.jsonl"
        self._recent_events: dict[tuple[int, str, int], datetime] = {}

    def remember_recent(self, guild_id: int, event_key: str, target_id: int) -> None:
        self._recent_events[(guild_id, event_key, target_id)] = discord.utils.utcnow()

    def was_recent(self, guild_id: int, event_key: str, target_id: int, *, seconds: int = 10) -> bool:
        stamp = self._recent_events.get((guild_id, event_key, target_id))
        if stamp is None:
            return False
        return discord.utils.utcnow() - stamp <= timedelta(seconds=seconds)

    def append_history(
        self,
        *,
        guild: discord.Guild,
        event_key: str,
        description: str,
        actor: discord.abc.User | None,
        target: Any,
        channel: discord.TextChannel,
    ) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": discord.utils.utcnow().isoformat(),
            "guild_id": guild.id,
            "guild_name": guild.name,
            "event_key": event_key,
            "description": description,
            "actor_id": getattr(actor, "id", None),
            "actor_name": self.display_name(actor) if actor is not None else None,
            "target_id": getattr(target, "id", None),
            "target_name": self.display_name(target) if target is not None else None,
            "log_channel_id": channel.id,
            "log_channel_name": channel.name,
        }
        with self.history_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def export_history(self, guild_id: int, *, limit: int = 100) -> discord.File:
        entries: list[dict[str, Any]] = []
        if self.history_path.exists():
            for raw_line in self.history_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                try:
                    item = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if item.get("guild_id") == guild_id:
                    entries.append(item)

        selected = entries[-limit:]
        buffer = io.BytesIO()
        buffer.write(json.dumps(selected, ensure_ascii=False, indent=2).encode("utf-8"))
        buffer.seek(0)
        return discord.File(buffer, filename=f"eva-audit-history-{guild_id}.json")
