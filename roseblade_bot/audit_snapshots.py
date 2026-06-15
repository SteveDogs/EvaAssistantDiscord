"""
EVA Assistant audit entry snapshot helpers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import discord

from roseblade_bot.audit_logger import AuditLogger
from roseblade_bot.formatters import _named_id_block


def _channel_snapshot(entry: discord.AuditLogEntry, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    if entry.action == discord.AuditLogAction.channel_delete:
        source = entry.before
    elif entry.action == discord.AuditLogAction.channel_create:
        source = entry.after
    else:
        source = entry.target or entry.after or entry.before

    channel_id = getattr(entry.target, "id", None)
    name = getattr(source, "name", None) or (f"ID {channel_id}" if channel_id else "канал")
    fields: list[tuple[str, str, bool]] = [("Канал", _named_id_block(name, channel_id), False)]

    channel_type = getattr(source, "type", None)
    if channel_type is not None:
        fields.append(("Тип", audit.format_channel_type(channel_type), True))

    category = getattr(source, "category", None)
    if category is not None:
        fields.append(("Категория", audit.format_entity(category), True))

    topic = getattr(source, "topic", None)
    if topic:
        fields.append(("Тема", audit.shorten(topic, 1024), False))

    return name, fields


def _thread_snapshot(entry: discord.AuditLogEntry, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    if entry.action == discord.AuditLogAction.thread_delete:
        source = entry.before
    elif entry.action == discord.AuditLogAction.thread_create:
        source = entry.after
    else:
        source = entry.target or entry.after or entry.before

    thread_id = getattr(entry.target, "id", None)
    name = getattr(source, "name", None) or (f"ID {thread_id}" if thread_id else "ветка")
    fields: list[tuple[str, str, bool]] = [("Ветка", _named_id_block(name, thread_id), False)]

    parent = getattr(source, "parent", None)
    if parent is not None:
        fields.append(("Родительский канал", audit.format_entity(parent), False))

    archived = getattr(source, "archived", None)
    if archived is not None:
        fields.append(("Архив", "Да" if archived else "Нет", True))

    return name, fields


def _role_snapshot(entry: discord.AuditLogEntry) -> tuple[str, list[tuple[str, str, bool]]]:
    if entry.action == discord.AuditLogAction.role_delete:
        source = entry.before
    elif entry.action == discord.AuditLogAction.role_create:
        source = entry.after
    else:
        source = entry.target or entry.after or entry.before

    role_id = getattr(entry.target, "id", None)
    name = getattr(source, "name", None) or (f"ID {role_id}" if role_id else "роль")
    fields: list[tuple[str, str, bool]] = [("Роль", _named_id_block(name, role_id), False)]

    colour = getattr(source, "colour", None) or getattr(source, "color", None)
    if isinstance(colour, discord.Colour) and colour.value:
        fields.append(("Цвет", f"`#{colour.value:06X}`", True))

    mentionable = getattr(source, "mentionable", None)
    if mentionable is not None:
        fields.append(("Упоминание", "Да" if mentionable else "Нет", True))

    hoist = getattr(source, "hoist", None)
    if hoist is not None:
        fields.append(("Отдельно в списке", "Да" if hoist else "Нет", True))

    return name, fields


def _webhook_snapshot(target: Any, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    webhook_id = getattr(target, "id", None)
    name = getattr(target, "name", None) or (f"ID {webhook_id}" if webhook_id else "вебхук")
    fields: list[tuple[str, str, bool]] = [("Вебхук", _named_id_block(name, webhook_id), False)]

    channel = getattr(target, "channel", None)
    if channel is not None:
        fields.append(("Канал", audit.format_entity(channel), False))

    return name, fields


def _invite_entry_snapshot(entry: discord.AuditLogEntry, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    if entry.action == discord.AuditLogAction.invite_delete:
        source = entry.before
    else:
        source = entry.target or entry.after or entry.before
    code = getattr(source, "code", None) or "unknown"
    fields: list[tuple[str, str, bool]] = [("Код", f"`{code}`", False)]

    channel = getattr(source, "channel", None)
    if channel is not None:
        fields.append(("Канал", audit.format_entity(channel), False))

    inviter = getattr(source, "inviter", None)
    if inviter is not None:
        fields.append(("Создатель", audit.format_entity(inviter), False))

    max_age = getattr(source, "max_age", None)
    if isinstance(max_age, int):
        fields.append(("Срок", "Без срока" if max_age == 0 else f"{max_age} сек", True))

    max_uses = getattr(source, "max_uses", None)
    if isinstance(max_uses, int):
        fields.append(("Использований", "Без лимита" if max_uses == 0 else str(max_uses), True))

    return code, fields


def _emoji_snapshot(entry: discord.AuditLogEntry, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    if entry.action == discord.AuditLogAction.emoji_delete:
        source = entry.before
    elif entry.action == discord.AuditLogAction.emoji_create:
        source = entry.after
    else:
        source = entry.target or entry.after or entry.before

    emoji_id = getattr(entry.target, "id", None)
    name = getattr(source, "name", None) or (f"emoji-{emoji_id}" if emoji_id else "эмодзи")
    fields: list[tuple[str, str, bool]] = [("Эмодзи", _named_id_block(name, emoji_id), False)]

    preview = str(entry.target) if isinstance(entry.target, discord.Emoji) else None
    if preview:
        fields.append(("Превью", preview, True))

    roles = list(getattr(source, "roles", []) or [])
    if roles:
        fields.append(("Доступно ролям", audit.format_entity(roles), False))

    return name, fields


def _sticker_snapshot(entry: discord.AuditLogEntry, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    if entry.action == discord.AuditLogAction.sticker_delete:
        source = entry.before
    elif entry.action == discord.AuditLogAction.sticker_create:
        source = entry.after
    else:
        source = entry.target or entry.after or entry.before

    sticker_id = getattr(entry.target, "id", None)
    name = getattr(source, "name", None) or (f"sticker-{sticker_id}" if sticker_id else "стикер")
    fields: list[tuple[str, str, bool]] = [("Стикер", _named_id_block(name, sticker_id), False)]

    emoji = getattr(source, "emoji", None)
    if emoji:
        fields.append(("Эмодзи", str(emoji), True))

    description = getattr(source, "description", None)
    if description:
        fields.append(("Описание", audit.shorten(description, 1024), False))

    format_type = getattr(source, "format", None) or getattr(source, "format_type", None)
    if format_type is not None:
        fields.append(("Формат", audit.format_change_value(format_type), True))

    return name, fields


def _soundboard_snapshot(entry: discord.AuditLogEntry) -> tuple[str, list[tuple[str, str, bool]]]:
    if entry.action == discord.AuditLogAction.soundboard_sound_delete:
        source = entry.before
    elif entry.action == discord.AuditLogAction.soundboard_sound_create:
        source = entry.after
    else:
        source = entry.after or entry.before

    sound_id = getattr(entry.target, "id", None)
    name = getattr(source, "name", None) or (f"sound-{sound_id}" if sound_id else "звук")
    fields: list[tuple[str, str, bool]] = [("Звук", _named_id_block(name, sound_id), False)]

    emoji_name = getattr(source, "emoji_name", None)
    if emoji_name:
        fields.append(("Эмодзи", emoji_name, True))

    volume = getattr(source, "volume", None)
    if isinstance(volume, (int, float)):
        fields.append(("Громкость", f"{round(float(volume) * 100)}%", True))

    available = getattr(source, "available", None)
    if isinstance(available, bool):
        fields.append(("Доступен", "Да" if available else "Нет", True))

    return name, fields


def _stage_snapshot(entry: discord.AuditLogEntry, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    source = entry.target or entry.after or entry.before
    channel = getattr(entry.extra, "channel", None)
    topic = getattr(source, "topic", None) or (channel.name if channel is not None else "Сцена")
    fields: list[tuple[str, str, bool]] = []
    if channel is not None:
        fields.append(("Сцена", audit.format_channel(channel), False))

    privacy_level = getattr(source, "privacy_level", None) or getattr(entry.after, "privacy_level", None)
    if privacy_level is not None:
        fields.append(("Приватность", audit.format_change_value(privacy_level), True))

    return topic, fields


def _scheduled_event_snapshot(entry: discord.AuditLogEntry, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    if entry.action == discord.AuditLogAction.scheduled_event_delete:
        source = entry.before
    elif entry.action == discord.AuditLogAction.scheduled_event_create:
        source = entry.after
    else:
        source = entry.target or entry.after or entry.before

    event_id = getattr(entry.target, "id", None)
    name = getattr(source, "name", None) or (f"event-{event_id}" if event_id else "событие")
    fields: list[tuple[str, str, bool]] = [("Событие", _named_id_block(name, event_id), False)]

    channel = getattr(source, "channel", None)
    if channel is not None:
        fields.append(("Канал", audit.format_entity(channel), False))

    location = getattr(source, "location", None)
    if isinstance(location, str) and location.strip():
        fields.append(("Локация", location.strip(), False))

    scheduled_start = getattr(source, "scheduled_start_time", None)
    if isinstance(scheduled_start, datetime):
        fields.append(("Старт", discord.utils.format_dt(scheduled_start, style="F"), False))

    scheduled_end = getattr(source, "scheduled_end_time", None)
    if isinstance(scheduled_end, datetime):
        fields.append(("Финиш", discord.utils.format_dt(scheduled_end, style="F"), False))

    status = getattr(source, "status", None)
    if status is not None:
        fields.append(("Статус", audit.format_change_value(status), True))

    entity_type = getattr(source, "entity_type", None)
    if entity_type is not None:
        fields.append(("Тип", audit.format_change_value(entity_type), True))

    return name, fields


def _automod_rule_snapshot(entry: discord.AuditLogEntry, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    if entry.action == discord.AuditLogAction.automod_rule_delete:
        source = entry.before
    elif entry.action == discord.AuditLogAction.automod_rule_create:
        source = entry.after
    else:
        source = entry.target or entry.after or entry.before

    rule_id = getattr(entry.target, "id", None)
    name = getattr(source, "name", None) or (f"rule-{rule_id}" if rule_id else "правило")
    fields: list[tuple[str, str, bool]] = [("Правило", _named_id_block(name, rule_id), False)]

    trigger_type = getattr(source, "trigger_type", None)
    if trigger_type is not None:
        fields.append(("Триггер", audit.format_change_value(trigger_type), True))

    event_type = getattr(source, "event_type", None)
    if event_type is not None:
        fields.append(("Тип проверки", audit.format_change_value(event_type), True))

    actions = getattr(source, "actions", None)
    if actions:
        fields.append(("Действия", audit.format_change_value(list(actions)), False))

    exempt_channels = getattr(source, "exempt_channels", None)
    if exempt_channels:
        fields.append(("Исключённые каналы", audit.format_change_value(list(exempt_channels)), False))

    exempt_roles = getattr(source, "exempt_roles", None)
    if exempt_roles:
        fields.append(("Исключённые роли", audit.format_change_value(list(exempt_roles)), False))

    return name, fields
