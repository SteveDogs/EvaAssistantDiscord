"""
EVA Assistant formatting helpers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import discord


def _format_message_content(content: str | None) -> str:
    if not content:
        return "_Пусто или нет доступа к содержимому._"
    shortened = content.strip()
    if not shortened:
        return "_Пусто или нет доступа к содержимому._"
    if len(shortened) > 1000:
        return shortened[:997] + "..."
    escaped = discord.utils.escape_mentions(discord.utils.escape_markdown(shortened))
    return "\n".join(f"> {line}" if line else "> " for line in escaped.splitlines()) or "> "


def _format_deleted_message_body(
    message: discord.Message,
    *,
    message_content_intent_enabled: bool,
) -> str:
    if message.content and message.content.strip():
        return _format_message_content(message.content)
    if message.attachments:
        return "_Сообщение было без текста. Смотри вложения ниже._"
    if not message_content_intent_enabled:
        return "_Discord не отдал текст сообщения, потому что у бота выключен Message Content Intent._"
    return "_Сообщение было пустым или содержимое не сохранилось в кэше._"


def _format_attachments(message: discord.Message) -> str | None:
    if not message.attachments:
        return None
    parts = []
    for attachment in message.attachments[:6]:
        parts.append(f"[{attachment.filename}]({attachment.url})")
    return "\n".join(parts)


def _format_reference(message: discord.Message) -> str | None:
    reference = message.reference
    if reference is None:
        return None
    resolved = reference.resolved
    if isinstance(resolved, discord.Message):
        author = resolved.author.display_name if resolved.author else "Неизвестно"
        content = _format_message_content(resolved.content)
        return f"Ответ на **{discord.utils.escape_markdown(author)}**\n{content}"
    if reference.message_id:
        return f"Ответ на сообщение `{reference.message_id}`"
    return None


def _format_voice_flags(before: discord.VoiceState, after: discord.VoiceState) -> list[str]:
    labels = {
        "self_mute": "Сам себе выключил микрофон",
        "self_deaf": "Сам себе выключил звук",
        "suppress": "Подавление",
    }

    changes: list[str] = []
    for attr, label in labels.items():
        old_value = getattr(before, attr)
        new_value = getattr(after, attr)
        if old_value != new_value:
            status = "включено" if new_value else "выключено"
            changes.append(f"{label}: {status}")
    return changes


def _format_voice_moderation_flags(before: discord.VoiceState, after: discord.VoiceState) -> list[str]:
    labels = {
        "mute": "Серверный мут",
        "deaf": "Серверный заглушен",
    }

    changes: list[str] = []
    for attr, label in labels.items():
        old_value = getattr(before, attr)
        new_value = getattr(after, attr)
        if old_value != new_value:
            status = "включён" if new_value else "снят"
            changes.append(f"{label}: {status}")
    return changes


def _parse_hex_color(raw_value: str) -> int:
    cleaned = raw_value.strip().lower()
    if cleaned == "default":
        return -1
    cleaned = cleaned.removeprefix("#")
    if len(cleaned) != 6:
        raise ValueError("Color must be in HEX format, for example #FFAA00.")
    return int(cleaned, 16)


def _named_id_block(name: str | None, object_id: int | None, *, include_id: bool = False) -> str:
    resolved_name = discord.utils.escape_markdown(name or "Неизвестно")
    lines = [f"**{resolved_name}**"]
    if include_id and object_id is not None:
        lines.append(f"`{object_id}`")
    return "\n".join(lines)


def _bool_label(value: bool) -> str:
    return "включено" if value else "выключено"


def _display_name(value: Any, fallback: str = "Неизвестно") -> str:
    if value is None:
        return fallback
    if isinstance(value, (discord.Member, discord.User)):
        return discord.utils.escape_markdown(value.display_name)
    raw_name = getattr(value, "name", None)
    if raw_name:
        return discord.utils.escape_markdown(str(raw_name))
    return discord.utils.escape_markdown(str(value))


def _human_join(parts: Sequence[str]) -> str:
    cleaned = [part for part in parts if part]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} и {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])} и {cleaned[-1]}"


def _voice_moderation_summary(changes: Sequence[str]) -> str:
    mapping = {
        "Серверный мут: включён": "отключил микрофон",
        "Серверный мут: снят": "вернул микрофон",
        "Серверный заглушен: включён": "отключил звук",
        "Серверный заглушен: снят": "вернул звук",
    }
    actions = [mapping.get(change, change.lower()) for change in changes]
    return _human_join(actions)


def _voice_state_summary(changes: Sequence[str]) -> str:
    mapping = {
        "Сам себе выключил микрофон: включено": "выключил себе микрофон",
        "Сам себе выключил микрофон: выключено": "включил себе микрофон",
        "Сам себе выключил звук: включено": "отключил себе звук",
        "Сам себе выключил звук: выключено": "вернул себе звук",
        "Подавление: включено": "попал под подавление",
        "Подавление: выключено": "вышел из подавления",
    }
    actions = [mapping.get(change, change.lower()) for change in changes]
    return _human_join(actions)


def _format_duration(started_at: datetime | None) -> str | None:
    if started_at is None:
        return None
    delta = discord.utils.utcnow() - started_at
    total_seconds = max(int(delta.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if seconds or not parts:
        parts.append(f"{seconds} сек")
    return " ".join(parts)


def _message_jump_url(guild_id: int, channel_id: int, message_id: int) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
