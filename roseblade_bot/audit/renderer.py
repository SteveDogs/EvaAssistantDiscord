"""
EVA Assistant audit embed renderer.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import random
from typing import Any

import discord

from roseblade_bot import EMBED_FOOTER
from roseblade_bot.audit.constants import CHANGE_LABELS, IGNORED_CHANGE_ATTRS, REASON_EVENT_KEYS
from roseblade_bot.audit_definitions import EVENT_DEFINITIONS
from roseblade_bot.audit.models import AuditEventPayload
from roseblade_bot.phrases import PHRASES


class AuditRenderer:
    @staticmethod
    def pick_flavor(event_key: str) -> str:
        return random.choice(PHRASES.flavor_texts.get(event_key, PHRASES.default_eva_lines))

    @staticmethod
    def pick_missing_reason_line() -> str:
        return random.choice(PHRASES.no_reason_lines)

    @staticmethod
    def shorten(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 3] + "..."

    @staticmethod
    def display_name(value: Any) -> str:
        if value is None:
            return "Неизвестно"
        if isinstance(value, (discord.Member, discord.User)):
            return value.display_name
        if isinstance(value, discord.Role):
            return value.name
        if isinstance(value, discord.AutoModRule):
            return value.name
        if isinstance(value, discord.ScheduledEvent):
            return value.name
        if isinstance(value, discord.StageInstance):
            return value.topic
        if isinstance(value, discord.SoundboardSound):
            return value.name
        if isinstance(value, discord.GuildSticker):
            return value.name
        if isinstance(value, discord.Emoji):
            return value.name
        if isinstance(value, (discord.Thread, discord.abc.GuildChannel)):
            return getattr(value, "name", f"ID {value.id}")
        if isinstance(value, discord.Webhook):
            return value.name or f"Webhook {value.id}"
        if isinstance(value, discord.Invite):
            return value.code
        if isinstance(value, discord.Object):
            return f"ID {value.id}"
        return str(value)

    @staticmethod
    def entity_image_url(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (discord.Member, discord.User)):
            return value.display_avatar.url
        if isinstance(value, discord.Webhook) and value.avatar is not None:
            return value.avatar.url
        if isinstance(value, discord.Role) and isinstance(value.display_icon, discord.Asset):
            return value.display_icon.url
        return None

    @staticmethod
    def label_for_entity(value: Any) -> str:
        if isinstance(value, (discord.Member, discord.User)):
            return "Участник"
        if isinstance(value, discord.Role):
            return "Роль"
        if isinstance(value, discord.AutoModRule):
            return "Правило"
        if isinstance(value, discord.ScheduledEvent):
            return "Событие"
        if isinstance(value, discord.StageInstance):
            return "Сцена"
        if isinstance(value, discord.SoundboardSound):
            return "Звук"
        if isinstance(value, discord.GuildSticker):
            return "Стикер"
        if isinstance(value, discord.Emoji):
            return "Эмодзи"
        if isinstance(value, discord.Thread):
            return "Ветка"
        if isinstance(value, discord.abc.GuildChannel):
            return "Канал"
        if isinstance(value, discord.Webhook):
            return "Вебхук"
        if isinstance(value, discord.Invite):
            return "Приглашение"
        return "Объект"

    @staticmethod
    def format_channel(channel: discord.abc.GuildChannel | discord.Thread | None, *, include_id: bool = False) -> str:
        if channel is None:
            return "Неизвестно"
        if hasattr(channel, "mention"):
            lines = [channel.mention]
            if include_id:
                lines.append(f"`{channel.id}`")
            return "\n".join(lines)
        return f"`{getattr(channel, 'name', 'unknown')}`"

    @staticmethod
    def format_channel_type(value: Any) -> str:
        mapping = {
            getattr(discord.ChannelType, "text", None): "Текстовый",
            getattr(discord.ChannelType, "voice", None): "Голосовой",
            getattr(discord.ChannelType, "category", None): "Категория",
            getattr(discord.ChannelType, "news", None): "Новостной",
            getattr(discord.ChannelType, "forum", None): "Форум",
            getattr(discord.ChannelType, "stage_voice", None): "Сцена",
            getattr(discord.ChannelType, "public_thread", None): "Публичная ветка",
            getattr(discord.ChannelType, "private_thread", None): "Приватная ветка",
            getattr(discord.ChannelType, "news_thread", None): "Новостная ветка",
        }
        return mapping.get(value, str(value))

    @staticmethod
    def format_enum(value: Enum) -> str:
        mapping = {
            getattr(discord.EventStatus, "scheduled", None): "Запланировано",
            getattr(discord.EventStatus, "active", None): "Активно",
            getattr(discord.EventStatus, "completed", None): "Завершено",
            getattr(discord.EventStatus, "canceled", None): "Отменено",
            getattr(discord.EntityType, "stage_instance", None): "Сцена",
            getattr(discord.EntityType, "voice", None): "Голосовой канал",
            getattr(discord.EntityType, "external", None): "Внешнее событие",
            getattr(discord.PrivacyLevel, "guild_only", None): "Только сервер",
            getattr(discord.AutoModRuleTriggerType, "keyword", None): "Ключевые слова",
            getattr(discord.AutoModRuleTriggerType, "harmful_link", None): "Опасные ссылки",
            getattr(discord.AutoModRuleTriggerType, "spam", None): "Спам",
            getattr(discord.AutoModRuleTriggerType, "keyword_preset", None): "Наборы слов",
            getattr(discord.AutoModRuleTriggerType, "mention_spam", None): "Спам упоминаниями",
            getattr(discord.AutoModRuleTriggerType, "member_profile", None): "Профиль участника",
            getattr(discord.AutoModRuleEventType, "message_send", None): "Отправка сообщения",
            getattr(discord.AutoModRuleEventType, "member_update", None): "Изменение профиля",
            getattr(discord.AutoModRuleActionType, "block_message", None): "Блокировка сообщения",
            getattr(discord.AutoModRuleActionType, "send_alert_message", None): "Сигнал в канал",
            getattr(discord.AutoModRuleActionType, "timeout", None): "Тайм-аут",
            getattr(discord.AutoModRuleActionType, "block_member_interactions", None): "Блокировка взаимодействий",
            getattr(discord.StickerFormatType, "png", None): "PNG",
            getattr(discord.StickerFormatType, "apng", None): "APNG",
            getattr(discord.StickerFormatType, "lottie", None): "Lottie",
            getattr(discord.StickerFormatType, "gif", None): "GIF",
            getattr(discord.VideoQualityMode, "auto", None): "Авто",
            getattr(discord.VideoQualityMode, "full", None): "Максимум",
            getattr(discord.ForumLayoutType, "not_set", None): "По умолчанию",
            getattr(discord.ForumLayoutType, "list_view", None): "Список",
            getattr(discord.ForumLayoutType, "gallery_view", None): "Галерея",
            getattr(discord.ForumOrderType, "latest_activity", None): "По активности",
            getattr(discord.ForumOrderType, "creation_date", None): "По дате создания",
        }
        if value in mapping:
            return mapping[value]
        return value.name.replace("_", " ").capitalize()

    @staticmethod
    def format_automod_action(value: discord.AutoModRuleAction) -> str:
        action_type = getattr(value, "type", None)
        label = AuditRenderer.format_enum(action_type) if isinstance(action_type, Enum) else str(action_type)
        parts = [label]
        channel_id = getattr(value, "channel_id", None)
        duration = getattr(value, "duration", None)
        custom_message = getattr(value, "custom_message", None)
        if channel_id:
            parts.append(f"канал `{channel_id}`")
        if duration:
            parts.append(f"длительность {duration}")
        if custom_message:
            parts.append(f"сообщение: {custom_message}")
        return " • ".join(parts)

    @staticmethod
    def format_change_value(value: Any) -> str:
        if value is None:
            return "Не задано"
        if isinstance(value, bool):
            return "Да" if value else "Нет"
        if isinstance(value, datetime):
            return discord.utils.format_dt(value, style="F")
        if isinstance(value, discord.ChannelType):
            return AuditRenderer.format_channel_type(value)
        if isinstance(value, Enum):
            return AuditRenderer.format_enum(value)
        if isinstance(value, discord.AutoModRuleAction):
            return AuditRenderer.format_automod_action(value)
        if isinstance(value, discord.PartialEmoji):
            return str(value) if str(value) else (value.name or "Эмодзи")
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            return value or "Пусто"
        if isinstance(value, list):
            return ", ".join(AuditRenderer.format_change_value(item) for item in value) or "Нет"
        return AuditRenderer.format_entity(value)

    @staticmethod
    def format_entity(value: Any, *, include_id: bool = False) -> str:
        if value is None:
            return "Неизвестно"
        if isinstance(value, (discord.Member, discord.User)):
            lines = [f"**{discord.utils.escape_markdown(value.display_name)}**", value.mention]
            username = str(value)
            if username != value.display_name:
                lines.insert(1, username)
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.Role):
            lines = [f"**{value.name}**", value.mention]
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.AutoModRule):
            lines = [f"**{value.name}**"]
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.ScheduledEvent):
            lines = [f"**{value.name}**"]
            if value.url:
                lines.append(value.url)
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.StageInstance):
            lines = [f"**{value.topic}**"]
            channel = getattr(value, "channel", None)
            if channel is not None:
                lines.append(AuditRenderer.format_channel(channel))
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.SoundboardSound):
            lines = [f"**{value.name}**"]
            emoji = getattr(value, "emoji", None)
            if emoji:
                lines.append(str(emoji))
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.GuildSticker):
            lines = [f"**{value.name}**"]
            emoji = getattr(value, "emoji", None)
            if emoji:
                lines.append(emoji)
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.Emoji):
            lines = [f"**{value.name}**"]
            preview = str(value)
            if preview:
                lines.append(preview)
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.Thread):
            lines = [value.mention]
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.abc.GuildChannel):
            return AuditRenderer.format_channel(value, include_id=include_id)
        if isinstance(value, discord.Invite):
            channel_name = AuditRenderer.format_channel(value.channel, include_id=include_id)
            return f"**{value.code}**\nКанал:\n{channel_name}"
        if isinstance(value, discord.Webhook):
            lines = [f"**{value.name or 'Webhook'}**"]
            if include_id:
                lines.append(f"`{value.id}`")
            return "\n".join(lines)
        if isinstance(value, discord.Object):
            return f"`{value.id}`"
        if isinstance(value, list):
            return ", ".join(AuditRenderer.format_entity(item, include_id=include_id) for item in value) or "Нет"
        if isinstance(value, bool):
            return "Да" if value else "Нет"
        if isinstance(value, discord.Asset):
            return value.url
        if isinstance(value, discord.Colour):
            return f"`#{value.value:06X}`"
        if isinstance(value, discord.ChannelType):
            return AuditRenderer.format_channel_type(value)
        if isinstance(value, datetime):
            return discord.utils.format_dt(value, style="F")
        if isinstance(value, Enum):
            return AuditRenderer.format_enum(value)
        if isinstance(value, str):
            return value
        return f"`{value}`"

    @staticmethod
    def describe_changes(entry: discord.AuditLogEntry, *, limit: int = 8) -> str | None:
        changes: list[str] = []
        seen = 0
        try:
            for attr, after_value in entry.after:
                before_value = getattr(entry.before, attr, None)
                if before_value == after_value:
                    continue
                if attr in IGNORED_CHANGE_ATTRS:
                    continue
                changes.append(
                    f"**{CHANGE_LABELS.get(attr, attr)}**: "
                    f"{AuditRenderer.format_change_value(before_value)} → {AuditRenderer.format_change_value(after_value)}"
                )
                seen += 1
                if seen >= limit:
                    break
        except TypeError:
            return None
        return "\n".join(changes) if changes else None

    def build_embed(
        self,
        payload: AuditEventPayload,
        *,
        color: discord.Colour,
        case_id: int | None = None,
    ) -> discord.Embed:
        definition = EVENT_DEFINITIONS[payload.event_key]
        embed = discord.Embed(
            title=f"{definition.emoji} {definition.title}",
            description=payload.description,
            colour=color,
            timestamp=discord.utils.utcnow(),
        )

        actor = payload.actor
        if actor is not None:
            author_name = self.display_name(actor)
            author_icon = self.entity_image_url(actor)
            if author_icon:
                embed.set_author(name=author_name, icon_url=author_icon)
            else:
                embed.set_author(name=author_name)

        resolved_thumbnail = payload.thumbnail_target if payload.thumbnail_target is not None else payload.target
        thumbnail_url = self.entity_image_url(resolved_thumbnail)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        if actor is not None and payload.show_actor_field:
            embed.add_field(name=payload.actor_label, value=self.format_entity(actor), inline=False)
        if payload.target is not None and payload.show_target_field:
            embed.add_field(
                name=payload.target_label or self.label_for_entity(payload.target),
                value=self.format_entity(payload.target),
                inline=False,
            )
        if case_id is not None:
            embed.add_field(name="Кейс", value=f"`#{case_id}`", inline=True)
        if payload.reason:
            embed.add_field(name="За что", value=self.shorten(payload.reason, 1024), inline=False)
        elif actor is not None and payload.event_key in REASON_EVENT_KEYS:
            embed.add_field(name="За что", value=self.pick_missing_reason_line(), inline=False)

        for name, value, inline in payload.fields:
            embed.add_field(name=name, value=self.shorten(value, 1024), inline=inline)

        flavor_text = payload.flavor_text or self.pick_flavor(payload.event_key)
        if flavor_text:
            embed.add_field(name="Ева шепчет", value=self.shorten(flavor_text, 1024), inline=False)

        footer_text = f"{payload.guild.name} • {EMBED_FOOTER}"
        footer_icon = payload.guild.icon.url if payload.guild.icon else None
        embed.set_footer(text=footer_text, icon_url=footer_icon)
        return embed
