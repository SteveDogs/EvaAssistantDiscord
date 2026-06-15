"""
EVA Assistant core bot logic and Discord event handlers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from roseblade_bot import APP_NAME, APP_CODENAME
from roseblade_bot.audit_definitions import CHANNEL_DEFINITIONS, EVENT_CHOICES, EVENT_DEFINITIONS
from roseblade_bot.audit_logger import AuditLogger
from roseblade_bot.config import BotConfig, load_config
from roseblade_bot.storage import JsonStateStore


def _format_message_content(content: str | None) -> str:
    if not content:
        return "_Пусто или нет доступа к содержимому._"
    shortened = content.strip()
    if not shortened:
        return "_Пусто или нет доступа к содержимому._"
    if len(shortened) > 1000:
        return shortened[:997] + "..."
    return shortened


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
        "self_stream": "Стрим",
        "self_video": "Камера",
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
        "Стрим: включено": "запустил стрим",
        "Стрим: выключено": "остановил стрим",
        "Камера: включено": "включил камеру",
        "Камера: выключено": "выключил камеру",
        "Подавление: включено": "попал под подавление",
        "Подавление: выключено": "вышел из подавления",
    }
    actions = [mapping.get(change, change.lower()) for change in changes]
    return _human_join(actions)


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


def _invite_snapshot(target: Any, audit: AuditLogger) -> tuple[str, list[tuple[str, str, bool]]]:
    code = getattr(target, "code", None) or "unknown"
    fields: list[tuple[str, str, bool]] = [("Код", f"`{code}`", False)]

    channel = getattr(target, "channel", None)
    if channel is not None:
        fields.append(("Канал", audit.format_entity(channel), False))

    inviter = getattr(target, "inviter", None)
    if inviter is not None:
        fields.append(("Создатель", audit.format_entity(inviter), False))

    return code, fields


class AuditCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: BotConfig, store: JsonStateStore) -> None:
        self.bot = bot
        self.config = config
        self.store = store
        self._bootstrapped_guild_ids: set[int] = set()
        self.audit = AuditLogger(
            store=store,
            default_category_name=config.audit_category_name,
            default_category_id=config.audit_category_id,
        )

    async def cog_load(self) -> None:
        self.bot.tree.on_error = self.on_app_command_error

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, app_commands.MissingPermissions):
            text = "Для этой команды нужны права администратора."
        else:
            text = f"Ошибка: {original}"

        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"{APP_NAME} ({APP_CODENAME}) connected as {self.bot.user} ({self.bot.user.id})")
        if self.config.guild_id:
            guild = self.bot.get_guild(self.config.guild_id)
            if guild is not None:
                await self.bootstrap_guild(guild)
            return

        for guild in self.bot.guilds:
            await self.bootstrap_guild(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.bootstrap_guild(guild)

    async def bootstrap_guild(self, guild: discord.Guild) -> None:
        if guild.id in self._bootstrapped_guild_ids:
            return

        if self.config.guild_id is None:
            try:
                self.bot.tree.copy_global_to(guild=guild)
                await self.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass

        await self.audit.ensure_guild_setup(guild, category_id=self.config.audit_category_id)
        self._bootstrapped_guild_ids.add(guild.id)

    async def find_message_delete_entry(
        self,
        message: discord.Message,
        *,
        max_age_seconds: int = 10,
    ) -> discord.AuditLogEntry | None:
        if message.guild is None:
            return None

        deadline = discord.utils.utcnow() - timedelta(seconds=max_age_seconds)
        try:
            async for entry in message.guild.audit_logs(limit=10, action=discord.AuditLogAction.message_delete):
                if entry.created_at < deadline:
                    break
                extra = getattr(entry, "extra", None)
                extra_channel = getattr(extra, "channel", None)
                extra_count = int(getattr(extra, "count", 0) or 0)
                if getattr(entry.target, "id", None) != message.author.id:
                    continue
                if getattr(extra_channel, "id", None) != message.channel.id:
                    continue
                if extra_count < 1:
                    continue
                return entry
        except (discord.Forbidden, discord.HTTPException):
            return None

        return None

    async def find_raw_message_delete_entry(
        self,
        guild: discord.Guild,
        channel_id: int,
        *,
        max_age_seconds: int = 8,
    ) -> discord.AuditLogEntry | None:
        deadline = discord.utils.utcnow() - timedelta(seconds=max_age_seconds)
        try:
            async for entry in guild.audit_logs(limit=8, action=discord.AuditLogAction.message_delete):
                if entry.created_at < deadline:
                    break
                extra = getattr(entry, "extra", None)
                extra_channel = getattr(extra, "channel", None)
                extra_count = int(getattr(extra, "count", 0) or 0)
                if getattr(extra_channel, "id", None) != channel_id:
                    continue
                if extra_count < 1:
                    continue
                return entry
        except (discord.Forbidden, discord.HTTPException):
            return None

        return None

    async def find_member_move_entry(
        self,
        member: discord.Member,
        destination: discord.VoiceChannel | discord.StageChannel,
        *,
        max_age_seconds: int = 8,
    ) -> discord.AuditLogEntry | None:
        deadline = discord.utils.utcnow() - timedelta(seconds=max_age_seconds)
        fallback: discord.AuditLogEntry | None = None
        try:
            async for entry in member.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_move):
                if entry.created_at < deadline:
                    break
                extra = getattr(entry, "extra", None)
                extra_channel = getattr(extra, "channel", None)
                extra_count = int(getattr(extra, "count", 0) or 0)
                if getattr(extra_channel, "id", None) != destination.id:
                    continue
                if getattr(entry.target, "id", None) == member.id:
                    return entry
                if fallback is None and extra_count == 1:
                    fallback = entry
        except (discord.Forbidden, discord.HTTPException):
            return None

        return fallback

    @app_commands.command(name="audit_setup", description="Создать категорию и каналы для аудита")
    @app_commands.describe(category_name="Название категории аудита")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_setup(
        self,
        interaction: discord.Interaction,
        category_name: str | None = None,
    ) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        category, channels = await self.audit.ensure_guild_setup(interaction.guild, category_name=category_name)
        lines = [f"Категория: {category.name}"]
        for key, channel in channels.items():
            lines.append(f"{CHANNEL_DEFINITIONS[key].name}: {channel.mention}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="audit_status", description="Показать текущую конфигурацию аудит-логов")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        saved = self.store.get_guild(interaction.guild.id)

        lines = [f"Категория ID: `{saved.get('category_id')}`"]
        for key, definition in CHANNEL_DEFINITIONS.items():
            channel_id = saved["channels"].get(key)
            channel = interaction.guild.get_channel(channel_id or 0)
            channel_value = channel.mention if isinstance(channel, discord.TextChannel) else "не настроен"
            lines.append(f"{definition.name}: {channel_value}")
        lines.append("")
        lines.append(f"Переопределённых цветов: `{len(saved['colors'])}`")
        disabled_events = [key for key, enabled in saved["enabled_events"].items() if not enabled]
        lines.append(f"Отключённых событий: `{len(disabled_events)}`")
        lines.append(
            "Intents:"
            f" members={_bool_label(self.config.enable_members_intent)},"
            f" message_content={_bool_label(self.config.enable_message_content_intent)}"
        )
        ignored = saved["ignored"]
        lines.append(
            "Ignore:"
            f" channels={len(ignored['channel_ids'])},"
            f" categories={len(ignored['category_ids'])},"
            f" users={len(ignored['user_ids'])},"
            f" roles={len(ignored['role_ids'])}"
        )

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="audit_events", description="Список ключей событий для настройки цветов")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_events(self, interaction: discord.Interaction) -> None:
        lines = []
        for event_key in EVENT_CHOICES:
            event = EVENT_DEFINITIONS[event_key]
            lines.append(f"`{event_key}` -> {event.title} / {CHANNEL_DEFINITIONS[event.channel_key].name}")
        message = "\n".join(lines)
        await interaction.response.send_message(message[:1990], ephemeral=True)

    @app_commands.command(name="audit_set_color", description="Задать цвет для конкретного события")
    @app_commands.describe(
        event_key="Ключ события, см. /audit_events",
        color="HEX цвет вроде #FFAA00 или слово default",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_set_color(
        self,
        interaction: discord.Interaction,
        event_key: str,
        color: str,
    ) -> None:
        assert interaction.guild is not None

        if event_key not in EVENT_DEFINITIONS:
            await interaction.response.send_message(
                "Неизвестный ключ события. Сначала посмотри /audit_events.",
                ephemeral=True,
            )
            return

        try:
            parsed = _parse_hex_color(color)
        except ValueError:
            await interaction.response.send_message(
                "Неверный цвет. Используй формат `#RRGGBB` или `default`.",
                ephemeral=True,
            )
            return

        if parsed == -1:
            self.store.remove_color_override(interaction.guild.id, event_key)
            await interaction.response.send_message(
                f"Цвет события `{event_key}` сброшен к значению по умолчанию.",
                ephemeral=True,
            )
            return

        self.store.update_guild(interaction.guild.id, colors={event_key: parsed})
        await interaction.response.send_message(
            f"Для события `{event_key}` установлен цвет `#{parsed:06X}`.",
            ephemeral=True,
        )

    async def event_key_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        del interaction
        current_lower = current.lower()
        matches = [
            app_commands.Choice(name=f"{key} - {EVENT_DEFINITIONS[key].title}", value=key)
            for key in EVENT_CHOICES
            if current_lower in key.lower() or current_lower in EVENT_DEFINITIONS[key].title.lower()
        ]
        return matches[:25]

    async def channel_key_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        del interaction
        current_lower = current.lower()
        matches = [
            app_commands.Choice(name=f"{key} - {CHANNEL_DEFINITIONS[key].name}", value=key)
            for key in sorted(CHANNEL_DEFINITIONS)
            if current_lower in key.lower() or current_lower in CHANNEL_DEFINITIONS[key].name.lower()
        ]
        return matches[:25]

    @audit_set_color.autocomplete("event_key")
    async def audit_set_color_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self.event_key_autocomplete(interaction, current)

    @app_commands.command(name="audit_toggle", description="Включить или выключить конкретный лог")
    @app_commands.describe(event_key="Ключ события, см. /audit_events", enabled="Вкл или выкл")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_toggle(
        self,
        interaction: discord.Interaction,
        event_key: str,
        enabled: bool,
    ) -> None:
        assert interaction.guild is not None
        if event_key not in EVENT_DEFINITIONS:
            await interaction.response.send_message("Неизвестный ключ события.", ephemeral=True)
            return
        self.store.set_event_enabled(interaction.guild.id, event_key, enabled)
        await interaction.response.send_message(
            f"Событие `{event_key}` теперь {_bool_label(enabled)}.",
            ephemeral=True,
        )

    @audit_toggle.autocomplete("event_key")
    async def audit_toggle_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self.event_key_autocomplete(interaction, current)

    @app_commands.command(name="audit_bind", description="Привязать лог-категорию к конкретному текстовому каналу")
    @app_commands.describe(channel_key="Ключ лог-категории", channel="Канал, куда отправлять эти логи")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_bind(
        self,
        interaction: discord.Interaction,
        channel_key: str,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild is not None
        if channel_key not in CHANNEL_DEFINITIONS:
            await interaction.response.send_message("Неизвестный ключ лог-категории.", ephemeral=True)
            return
        self.store.update_guild(interaction.guild.id, channels={channel_key: channel.id})
        await interaction.response.send_message(
            f"Логи `{CHANNEL_DEFINITIONS[channel_key].name}` теперь идут в {channel.mention}.",
            ephemeral=True,
        )

    @audit_bind.autocomplete("channel_key")
    async def audit_bind_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self.channel_key_autocomplete(interaction, current)

    @app_commands.command(name="audit_export", description="Выгрузить историю логов этого сервера в JSON")
    @app_commands.describe(limit="Сколько последних записей выгрузить")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_export(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 1000] = 100) -> None:
        assert interaction.guild is not None
        audit_file = self.audit.export_history(interaction.guild.id, limit=limit)
        await interaction.response.send_message(
            content=f"Экспорт последних `{limit}` записей.",
            file=audit_file,
            ephemeral=True,
        )

    @app_commands.command(name="audit_ignore_channel", description="Игнорировать события из канала")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_ignore_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel) -> None:
        assert interaction.guild is not None
        self.store.add_ignored_id(interaction.guild.id, "channel_ids", channel.id)
        await interaction.response.send_message(f"Канал {channel.mention} добавлен в ignore.", ephemeral=True)

    @app_commands.command(name="audit_unignore_channel", description="Снять ignore с канала")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_unignore_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel) -> None:
        assert interaction.guild is not None
        self.store.remove_ignored_id(interaction.guild.id, "channel_ids", channel.id)
        await interaction.response.send_message(f"Канал {channel.mention} убран из ignore.", ephemeral=True)

    @app_commands.command(name="audit_ignore_category", description="Игнорировать события из категории")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_ignore_category(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        assert interaction.guild is not None
        self.store.add_ignored_id(interaction.guild.id, "category_ids", category.id)
        await interaction.response.send_message(f"Категория **{category.name}** добавлена в ignore.", ephemeral=True)

    @app_commands.command(name="audit_unignore_category", description="Снять ignore с категории")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_unignore_category(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        assert interaction.guild is not None
        self.store.remove_ignored_id(interaction.guild.id, "category_ids", category.id)
        await interaction.response.send_message(f"Категория **{category.name}** убрана из ignore.", ephemeral=True)

    @app_commands.command(name="audit_ignore_user", description="Игнорировать события пользователя")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_ignore_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        self.store.add_ignored_id(interaction.guild.id, "user_ids", member.id)
        await interaction.response.send_message(f"Пользователь {member.mention} добавлен в ignore.", ephemeral=True)

    @app_commands.command(name="audit_unignore_user", description="Снять ignore с пользователя")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_unignore_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        self.store.remove_ignored_id(interaction.guild.id, "user_ids", member.id)
        await interaction.response.send_message(f"Пользователь {member.mention} убран из ignore.", ephemeral=True)

    @app_commands.command(name="audit_ignore_role", description="Игнорировать события роли")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_ignore_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        assert interaction.guild is not None
        self.store.add_ignored_id(interaction.guild.id, "role_ids", role.id)
        await interaction.response.send_message(f"Роль {role.mention} добавлена в ignore.", ephemeral=True)

    @app_commands.command(name="audit_unignore_role", description="Снять ignore с роли")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_unignore_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        assert interaction.guild is not None
        self.store.remove_ignored_id(interaction.guild.id, "role_ids", role.id)
        await interaction.response.send_message(f"Роль {role.mention} убрана из ignore.", ephemeral=True)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        guild = entry.guild
        if not self.store.get_guild(guild.id)["channels"]:
            return

        action = entry.action
        action_value = getattr(action, "value", None)
        target = entry.target

        # Compare by raw audit action value to avoid enum alias inconsistencies across discord.py builds.
        if action_value == 22:
            target_id = getattr(target, "id", 0)
            if target_id:
                self.audit.remember_recent(guild.id, "member_banned", target_id)
            await self.audit.send_event(
                guild,
                "member_banned",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} отправил **{_display_name(target)}** отдыхать в бан-лист.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                related_users=[entry.user, target],
            )
        elif action_value == 23:
            target_id = getattr(target, "id", 0)
            if target_id:
                self.audit.remember_recent(guild.id, "member_unbanned", target_id)
            await self.audit.send_event(
                guild,
                "member_unbanned",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} вернул **{_display_name(target)}** из бан-листа.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                related_users=[entry.user, target],
            )
        elif action_value == 20:
            target_id = getattr(target, "id", 0)
            if target_id:
                self.audit.remember_recent(guild.id, "member_kicked", target_id)
            await self.audit.send_event(
                guild,
                "member_kicked",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} показал **{_display_name(target)}** дверь сервера.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                related_users=[entry.user, target],
            )
        elif action_value == 10:
            channel_name, fields = _channel_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "channel_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} открыл канал **{discord.utils.escape_markdown(channel_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.abc.GuildChannel) else None],
                related_users=[entry.user],
            )
        elif action_value == 12:
            channel_name, fields = _channel_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "channel_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} снёс канал **{discord.utils.escape_markdown(channel_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 11:
            channel_name, fields = _channel_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "channel_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} подкрутил канал **{discord.utils.escape_markdown(channel_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.abc.GuildChannel) else None],
                related_users=[entry.user],
            )
        elif action_value in {13, 14, 15}:
            changes = self.audit.describe_changes(entry)
            fields = [("Канал", self.audit.format_entity(target), False)] if target is not None else []
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "channel_permissions_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} перекроил доступы к каналу.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.abc.GuildChannel) else None],
                related_users=[entry.user],
            )
        elif action_value == 110:
            thread_name, fields = _thread_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "thread_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} завёл ветку **{discord.utils.escape_markdown(thread_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 112:
            thread_name, fields = _thread_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "thread_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} прикрыл ветку **{discord.utils.escape_markdown(thread_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 111:
            thread_name, fields = _thread_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "thread_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил ветку **{discord.utils.escape_markdown(thread_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 30:
            role_name, fields = _role_snapshot(entry)
            await self.audit.send_event(
                guild,
                "role_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} создал роль **{discord.utils.escape_markdown(role_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_roles=[target if isinstance(target, discord.Role) else None],
                related_users=[entry.user],
            )
        elif action_value == 32:
            role_name, fields = _role_snapshot(entry)
            await self.audit.send_event(
                guild,
                "role_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} отправил роль **{discord.utils.escape_markdown(role_name)}** в архив забвения.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_roles=[target if isinstance(target, discord.Role) else None],
                related_users=[entry.user],
            )
        elif action_value == 31:
            role_name, fields = _role_snapshot(entry)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "role_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил роль **{discord.utils.escape_markdown(role_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_roles=[target if isinstance(target, discord.Role) else None],
                related_users=[entry.user],
            )
        elif action_value == 25:
            added_roles = list(getattr(entry.after, "roles", []) or [])
            removed_roles = list(getattr(entry.before, "roles", []) or [])
            target_id = getattr(target, "id", 0)

            if added_roles:
                if target_id:
                    self.audit.remember_recent(guild.id, "member_role_added", target_id)
                await self.audit.send_event(
                    guild,
                    "member_role_added",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} накинул роли участнику **{_display_name(target)}**.",
                    actor=entry.user,
                    target=target,
                    reason=entry.reason,
                    fields=[("Какие роли прилетели", self.audit.format_entity(added_roles), False)],
                    show_actor_field=True,
                    show_target_field=True,
                    actor_label="Кто навёл движ",
                    target_label="Кому прилетело",
                    thumbnail_target=target,
                    related_users=[entry.user, target],
                    related_roles=added_roles,
                )

            if removed_roles:
                if target_id:
                    self.audit.remember_recent(guild.id, "member_role_removed", target_id)
                await self.audit.send_event(
                    guild,
                    "member_role_removed",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} снял роли с участника **{_display_name(target)}**.",
                    actor=entry.user,
                    target=target,
                    reason=entry.reason,
                    fields=[("Что именно улетело", self.audit.format_entity(removed_roles), False)],
                    show_actor_field=True,
                    show_target_field=True,
                    actor_label="Кто навёл движ",
                    target_label="Кого разжаловали",
                    thumbnail_target=target,
                    related_users=[entry.user, target],
                    related_roles=removed_roles,
                )
        elif action_value == 40:
            code, fields = _invite_snapshot(target, self.audit)
            await self.audit.send_event(
                guild,
                "invite_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} выкатил приглашение **{code}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(target, "channel", None)],
                related_users=[entry.user, getattr(target, "inviter", None)],
            )
        elif action_value == 42:
            code, fields = _invite_snapshot(target, self.audit)
            await self.audit.send_event(
                guild,
                "invite_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} прикрыл приглашение **{code}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(target, "channel", None)],
                related_users=[entry.user, getattr(target, "inviter", None)],
            )
        elif action_value == 1:
            changes = self.audit.describe_changes(entry)
            fields: list[tuple[str, str, bool]] = []
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "server_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} снова крутил гайки сервера.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 50:
            webhook_name, fields = _webhook_snapshot(target, self.audit)
            await self.audit.send_event(
                guild,
                "webhook_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} создал вебхук **{discord.utils.escape_markdown(webhook_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(target, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 52:
            webhook_name, fields = _webhook_snapshot(target, self.audit)
            await self.audit.send_event(
                guild,
                "webhook_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} удалил вебхук **{discord.utils.escape_markdown(webhook_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(target, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 51:
            webhook_name, fields = _webhook_snapshot(target, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "webhook_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил вебхук **{discord.utils.escape_markdown(webhook_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(target, "channel", None)],
                related_users=[entry.user],
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        age = discord.utils.utcnow() - member.created_at
        await self.audit.send_event(
            member.guild,
            "member_joined",
            f"На сервер залетел **{_display_name(member)}**. Добро пожаловать в движ.",
            target=member,
            fields=[
                ("Аккаунт создан", discord.utils.format_dt(member.created_at, style="F"), False),
                ("Возраст аккаунта", discord.utils.format_dt(member.created_at, style="R"), False),
            ],
            related_users=[member],
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return

        if self.audit.was_recent(member.guild.id, "member_kicked", member.id, seconds=10):
            return
        if self.audit.was_recent(member.guild.id, "member_banned", member.id, seconds=10):
            return

        await self.audit.send_event(
            member.guild,
            "member_left",
            f"**{_display_name(member)}** покинул сервер. Вышел красиво или просто растворился в тумане.",
            target=member,
            fields=[
                (
                    "Присоединился к серверу",
                    discord.utils.format_dt(member.joined_at, style="F") if member.joined_at else "Неизвестно",
                    False,
                ),
                (
                    "Роли",
                    ", ".join(role.mention for role in member.roles if not role.is_default()) or "Нет ролей",
                    False,
                ),
            ],
            related_users=[member],
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot:
            return

        guild = after.guild

        if before.nick != after.nick:
            entry = await self.audit.fetch_recent_audit_entry(
                guild,
                actions=[discord.AuditLogAction.member_update],
                target_id=after.id,
                max_age_seconds=15,
            )
            await self.audit.send_event(
                guild,
                "nickname_changed",
                f"Участник **{_display_name(before)}** теперь проходит как **{_display_name(after)}**.",
                actor=entry.user if entry else None,
                target=after,
                reason=entry.reason if entry else None,
                related_users=[after, entry.user if entry else None],
            )

        before_roles = {role.id: role for role in before.roles if not role.is_default()}
        after_roles = {role.id: role for role in after.roles if not role.is_default()}
        added_roles = [role for role_id, role in after_roles.items() if role_id not in before_roles]
        removed_roles = [role for role_id, role in before_roles.items() if role_id not in after_roles]
        if self.audit.was_recent(guild.id, "member_role_added", after.id, seconds=10):
            added_roles = []
        if self.audit.was_recent(guild.id, "member_role_removed", after.id, seconds=10):
            removed_roles = []
        if added_roles or removed_roles:
            entry = await self.audit.fetch_recent_audit_entry(
                guild,
                actions=[discord.AuditLogAction.member_role_update],
                target_id=after.id,
                max_age_seconds=15,
            )
            if added_roles:
                await self.audit.send_event(
                    guild,
                    "member_role_added",
                    f"Участнику **{_display_name(after)}** накинули новые роли.",
                    actor=entry.user if entry else None,
                    target=after,
                    reason=entry.reason if entry else None,
                    fields=[("Какие роли прилетели", self.audit.format_entity(added_roles), False)],
                    show_actor_field=entry is not None,
                    show_target_field=True,
                    actor_label="Кто навёл движ",
                    target_label="Кому прилетело",
                    thumbnail_target=after,
                    related_users=[after, entry.user if entry else None],
                    related_roles=added_roles,
                )
            if removed_roles:
                await self.audit.send_event(
                    guild,
                    "member_role_removed",
                    f"С участника **{_display_name(after)}** сняли роли.",
                    actor=entry.user if entry else None,
                    target=after,
                    reason=entry.reason if entry else None,
                    fields=[("Что именно улетело", self.audit.format_entity(removed_roles), False)],
                    show_actor_field=entry is not None,
                    show_target_field=True,
                    actor_label="Кто навёл движ",
                    target_label="Кого разжаловали",
                    thumbnail_target=after,
                    related_users=[after, entry.user if entry else None],
                    related_roles=removed_roles,
                )

        if before.timed_out_until != after.timed_out_until:
            entry = await self.audit.fetch_recent_audit_entry(
                guild,
                actions=[
                    discord.AuditLogAction.member_update,
                    discord.AuditLogAction.automod_timeout_member,
                ],
                target_id=after.id,
                max_age_seconds=15,
            )
            if after.timed_out_until is not None:
                self.audit.remember_recent(guild.id, "member_timeout_applied", after.id)
                await self.audit.send_event(
                    guild,
                    "member_timeout_applied",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} отправил **{_display_name(after)}** посидеть в тайм-ауте.",
                    actor=entry.user if entry else None,
                    target=after,
                    reason=entry.reason if entry else None,
                    fields=[
                        (
                            "До",
                            discord.utils.format_dt(after.timed_out_until, style="F"),
                            False,
                        )
                    ],
                    related_users=[after, entry.user if entry else None],
                )
            else:
                self.audit.remember_recent(guild.id, "member_timeout_removed", after.id)
                await self.audit.send_event(
                    guild,
                    "member_timeout_removed",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} вернул **{_display_name(after)}** из тайм-аута.",
                    actor=entry.user if entry else None,
                    target=after,
                    reason=entry.reason if entry else None,
                    related_users=[after, entry.user if entry else None],
                )

        if before.premium_since != after.premium_since and after.premium_since is not None:
            await self.audit.send_event(
                guild,
                "server_boosted",
                f"**{_display_name(after)}** бустанул сервер. Красиво зашёл.",
                target=after,
                fields=[("С", discord.utils.format_dt(after.premium_since, style="F"), False)],
                related_users=[after],
            )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        entry = await self.find_message_delete_entry(message)
        fields = [
            ("Канал", message.channel.mention, False),
            ("Message ID", f"`{message.id}`", False),
            ("Сообщение", _format_deleted_message_body(message, message_content_intent_enabled=self.config.enable_message_content_intent), False),
            ("Отправлено", discord.utils.format_dt(message.created_at, style="F"), False),
        ]
        attachments = _format_attachments(message)
        if attachments:
            fields.append(("Вложения", attachments, False))
        reference = _format_reference(message)
        if reference:
            fields.append(("Ответ на", reference, False))
        if entry is None:
            fields.append(
                (
                    "Кто удалил",
                    "Audit Log не дал точного исполнителя. Обычно это значит, что сообщение удалил сам автор или запись ещё не успела появиться у Discord.",
                    False,
                )
            )
        await self.audit.send_event(
            message.guild,
            "message_deleted",
            (
                f"{_display_name(entry.user, 'Кто-то из стаффа')} подчистил сообщение "
                f"**{_display_name(message.author)}** в {message.channel.mention}."
                if entry is not None
                else f"Сообщение **{_display_name(message.author)}** исчезло из {message.channel.mention}."
            ),
            actor=entry.user if entry else None,
            target=message.author,
            reason=entry.reason if entry else None,
            fields=fields,
            show_actor_field=entry is not None,
            show_target_field=True,
            actor_label="Кто подчистил",
            target_label="Автор сообщения",
            thumbnail_target=message.author,
            related_channels=[message.channel],
            related_users=[message.author, entry.user if entry else None],
        )

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.cached_message is not None or payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(payload.channel_id)
        channel_value = channel.mention if isinstance(channel, discord.TextChannel) else f"`{payload.channel_id}`"
        entry = await self.find_raw_message_delete_entry(guild, payload.channel_id)
        fields: list[tuple[str, str, bool]] = [
            ("Канал", channel_value, False),
            ("Message ID", f"`{payload.message_id}`", False),
        ]
        if entry is not None and entry.target is not None:
            fields.append(("Автор сообщения", self.audit.format_entity(entry.target), False))
        fields.append(
            (
                "Почему нет текста",
                "Сообщение не попало в кэш бота. Для показа удалённого текста бот должен заранее видеть сообщение и хранить его в памяти.",
                False,
            )
        )
        await self.audit.send_event(
            guild,
            "message_deleted",
            (
                f"{_display_name(entry.user, 'Кто-то из стаффа')} снёс сообщение, но текст ускользнул из кэша."
                if entry is not None
                else "Сообщение удалили, но его текст не успел осесть в памяти бота."
            ),
            actor=entry.user if entry else None,
            target=entry.target if entry and entry.target is not None else None,
            reason=entry.reason if entry else None,
            fields=fields,
            show_actor_field=entry is not None,
            show_target_field=entry is not None and entry.target is not None,
            actor_label="Кто подчистил",
            target_label="Автор сообщения",
            thumbnail_target=entry.target if entry and entry.target is not None else None,
            related_channels=[channel] if isinstance(channel, discord.abc.GuildChannel) else None,
            related_users=[entry.user if entry else None, entry.target if entry else None],
        )

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(payload.channel_id)
        cached_messages = [message for message in payload.cached_messages if not message.author.bot]
        fields: list[tuple[str, str, bool]] = [
            ("Канал", channel.mention if isinstance(channel, discord.TextChannel) else f"`{payload.channel_id}`", False),
            ("Количество", str(len(payload.message_ids)), True),
            ("Из кэша", str(len(cached_messages)), True),
        ]
        await self.audit.send_event(
            guild,
            "message_deleted",
            "В канале устроили массовую зачистку сообщений.",
            fields=fields,
            related_channels=[channel] if isinstance(channel, discord.abc.GuildChannel) else None,
            include_case_id=False,
        )

        if cached_messages:
            transcript_lines = []
            for message in cached_messages[:50]:
                transcript_lines.append(
                    f"[{message.created_at.isoformat()}] {message.author} ({message.author.id}): {message.content}"
                )
            transcript = io.BytesIO("\n".join(transcript_lines).encode("utf-8"))
            transcript.seek(0)
            log_channel = await self.audit.get_channel_for_event(guild, "message_deleted")
            if log_channel is not None:
                await log_channel.send(
                    content="Транскрипт удалённых сообщений:",
                    file=discord.File(transcript, filename=f"bulk-delete-{payload.channel_id}.txt"),
                )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild is None or before.author.bot:
            return
        if before.content == after.content and before.attachments == after.attachments:
            return
        fields = [
            ("Автор", self.audit.format_entity(before.author), False),
            ("Канал", before.channel.mention, False),
            ("До", _format_message_content(before.content), False),
            ("После", _format_message_content(after.content), False),
            ("Ссылка", after.jump_url, False),
        ]
        before_attachments = _format_attachments(before)
        after_attachments = _format_attachments(after)
        if before_attachments or after_attachments:
            fields.append(("Вложения до", before_attachments or "Нет", False))
            fields.append(("Вложения после", after_attachments or "Нет", False))
        reference = _format_reference(after)
        if reference:
            fields.append(("Ответ на", reference, False))
        await self.audit.send_event(
            before.guild,
            "message_edited",
            f"**{_display_name(before.author)}** переписал сообщение в {before.channel.mention}. Версия 2.0 готова.",
            target=before.author,
            fields=fields,
            show_target_field=False,
            thumbnail_target=before.author,
            related_channels=[before.channel],
            related_users=[before.author],
        )

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.cached_message is not None or payload.guild_id is None:
            return
        if "content" not in payload.data:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(payload.channel_id)
        channel_value = channel.mention if isinstance(channel, discord.TextChannel) else f"`{payload.channel_id}`"
        await self.audit.send_event(
            guild,
            "message_edited",
            "Сообщение переписали, но старая версия успела улизнуть из кэша.",
            fields=[
                ("Канал", channel_value, False),
                ("Message ID", f"`{payload.message_id}`", False),
                ("После", _format_message_content(payload.data.get("content")), False),
                (
                    "Почему нет старого текста",
                    "Бот не сохранил старую версию в кэше. Для лучшего покрытия держим увеличенный кэш, но старые сообщения и рестарты всё равно могут выпадать.",
                    False,
                ),
            ],
            related_channels=[channel] if isinstance(channel, discord.abc.GuildChannel) else None,
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        guild = member.guild

        if before.channel != after.channel:
            if before.channel is not None and after.channel is None:
                if self.audit.was_recent(guild.id, "member_disconnected", member.id, seconds=8):
                    return
                entry = await self.audit.fetch_recent_audit_entry(
                    guild,
                    actions=[discord.AuditLogAction.member_disconnect],
                    target_id=member.id,
                    max_age_seconds=8,
                )
                if entry is not None:
                    self.audit.remember_recent(guild.id, "member_disconnected", member.id)
                    await self.audit.send_event(
                        guild,
                        "member_disconnected",
                        f"{_display_name(entry.user, 'Кто-то из стаффа')} выдернул **{_display_name(member)}** из войса.",
                        actor=entry.user,
                        target=member,
                        reason=entry.reason,
                        fields=[
                            ("Кто навёл движ", self.audit.format_entity(entry.user), False),
                            ("Участник", self.audit.format_entity(member), False),
                            ("Канал", self.audit.format_channel(before.channel), False),
                        ],
                        show_target_field=False,
                        thumbnail_target=member,
                        related_channels=[before.channel],
                        related_users=[member, entry.user],
                    )
                    return
                await self.audit.send_event(
                    guild,
                    "member_voice_left",
                    f"**{_display_name(member)}** вышел из войса.",
                    target=member,
                    fields=[("Канал", self.audit.format_channel(before.channel), False)],
                    related_channels=[before.channel],
                    related_users=[member],
                )
                return

            if before.channel is None and after.channel is not None:
                await self.audit.send_event(
                    guild,
                    "member_voice_joined",
                    f"**{_display_name(member)}** залетел в войс.",
                    target=member,
                    fields=[("Канал", self.audit.format_channel(after.channel), False)],
                    related_channels=[after.channel],
                    related_users=[member],
                )
                return

            if before.channel is not None and after.channel is not None:
                if self.audit.was_recent(guild.id, "member_moved", member.id, seconds=8):
                    return
                entry = await self.find_member_move_entry(member, after.channel, max_age_seconds=8)
                if entry is not None:
                    self.audit.remember_recent(guild.id, "member_moved", member.id)
                    await self.audit.send_event(
                        guild,
                        "member_moved",
                        (
                            f"{_display_name(entry.user, 'Кто-то из стаффа')} перетащил **{_display_name(member)}** "
                            f"из {before.channel.mention} в {after.channel.mention}."
                        ),
                        actor=entry.user,
                        target=member,
                        reason=entry.reason,
                        fields=[
                            ("Модератор", self.audit.format_entity(entry.user), False),
                            ("Участник", self.audit.format_entity(member), False),
                            ("Из канала", self.audit.format_channel(before.channel), True),
                            ("В канал", self.audit.format_channel(after.channel), True),
                        ],
                        show_target_field=False,
                        thumbnail_target=member,
                        related_channels=[before.channel, after.channel],
                        related_users=[member, entry.user],
                    )
                    return
                await self.audit.send_event(
                    guild,
                    "member_voice_switched",
                    f"**{_display_name(member)}** сам переехал между войсами.",
                    target=member,
                    fields=[
                        ("Из", self.audit.format_channel(before.channel), True),
                        ("В", self.audit.format_channel(after.channel), True),
                    ],
                    related_channels=[before.channel, after.channel],
                    related_users=[member],
                )
                return

        moderation_changes = _format_voice_moderation_flags(before, after)
        active_channel = after.channel or before.channel
        if moderation_changes and active_channel is not None:
            entry = await self.audit.fetch_recent_audit_entry(
                guild,
                actions=[discord.AuditLogAction.member_update],
                target_id=member.id,
                max_age_seconds=8,
            )
            await self.audit.send_event(
                guild,
                "member_voice_moderation_changed",
                (
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} "
                    f"{_voice_moderation_summary(moderation_changes)} участнику **{_display_name(member)}**."
                ),
                actor=entry.user if entry else None,
                target=member,
                reason=entry.reason if entry else None,
                fields=[
                    ("Кто навёл движ", self.audit.format_entity(entry.user) if entry else "Неизвестно", False),
                    ("Участник", self.audit.format_entity(member), False),
                    ("Канал", self.audit.format_channel(active_channel), False),
                    ("Изменения", "\n".join(moderation_changes), False),
                ],
                show_target_field=False,
                thumbnail_target=member,
                related_channels=[active_channel],
                related_users=[member, entry.user if entry else None],
            )

        state_changes = _format_voice_flags(before, after)
        if state_changes and active_channel is not None:
            await self.audit.send_event(
                guild,
                "member_voice_state_changed",
                f"**{_display_name(member)}** в войсе { _voice_state_summary(state_changes) }.",
                target=member,
                fields=[
                    ("Канал", self.audit.format_channel(active_channel), False),
                    ("Изменения", "\n".join(state_changes), False),
                ],
                related_channels=[active_channel],
                related_users=[member],
            )


def build_bot(config: BotConfig) -> commands.Bot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = config.enable_members_intent
    intents.guild_messages = True
    intents.message_content = config.enable_message_content_intent
    intents.voice_states = True

    bot = commands.Bot(command_prefix="!", intents=intents, max_messages=10000)
    store = JsonStateStore(config.state_file)
    cog = AuditCog(bot, config, store)

    async def setup() -> None:
        await bot.add_cog(cog)
        if config.guild_id:
            guild = discord.Object(id=config.guild_id)
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        else:
            await bot.tree.sync()

    bot.setup_hook = setup
    return bot


def main() -> None:
    config = load_config()
    bot = build_bot(config)
    bot.run(config.token)
