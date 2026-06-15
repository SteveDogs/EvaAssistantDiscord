"""
EVA Assistant core bot logic and Discord event handlers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import random
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from roseblade_bot import APP_NAME, APP_CODENAME
from roseblade_bot.audit_definitions import CHANNEL_DEFINITIONS, EVENT_CHOICES, EVENT_DEFINITIONS
from roseblade_bot.audit_snapshots import (
    _automod_rule_snapshot,
    _channel_snapshot,
    _emoji_snapshot,
    _invite_entry_snapshot,
    _role_snapshot,
    _scheduled_event_snapshot,
    _soundboard_snapshot,
    _stage_snapshot,
    _sticker_snapshot,
    _thread_snapshot,
    _webhook_snapshot,
)
from roseblade_bot.audit_logger import AuditLogger
from roseblade_bot.chat_banter import CHAT_BANTER
from roseblade_bot.config import BotConfig, load_config
from roseblade_bot.formatters import (
    _bool_label,
    _display_name,
    _format_attachments,
    _format_deleted_message_body,
    _format_duration,
    _format_message_content,
    _format_reference,
    _message_jump_url,
    _parse_hex_color,
)
from roseblade_bot.message_handlers import (
    handle_on_message,
    handle_on_message_delete,
    handle_on_message_edit,
    handle_on_raw_bulk_message_delete,
    handle_on_raw_message_delete,
    handle_on_raw_message_edit,
)
from roseblade_bot.pubg_lookup import PubgLookupService
from roseblade_bot.storage import JsonStateStore
from roseblade_bot.voice_guard import VOICE_GUARD
from roseblade_bot.voice_handlers import handle_on_voice_state_update


class AuditCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: BotConfig, store: JsonStateStore) -> None:
        self.bot = bot
        self.config = config
        self.store = store
        self._bootstrapped_guild_ids: set[int] = set()
        self._voice_sessions: dict[tuple[int, int], datetime] = {}
        self._stream_sessions: dict[tuple[int, int], datetime] = {}
        self._camera_sessions: dict[tuple[int, int], datetime] = {}
        self._managed_nickname_updates: dict[tuple[int, int], datetime] = {}
        self._chat_banter_last_channel_reply: dict[tuple[int, int], datetime] = {}
        self._chat_banter_last_user_reply: dict[tuple[int, int], datetime] = {}
        self._chat_banter_last_channel_text: dict[tuple[int, int], str] = {}
        self._protected_voice_guard_recent: dict[tuple[int, int, int, int | None], datetime] = {}
        self.pubg_lookup = PubgLookupService(config)
        self.audit = AuditLogger(
            store=store,
            default_category_name=config.audit_category_name,
            default_category_id=config.audit_category_id,
            static_ignored_channel_ids=config.ignored_channel_ids,
        )

    @staticmethod
    def _session_key(member: discord.Member) -> tuple[int, int]:
        return (member.guild.id, member.id)

    def _start_session(
        self,
        bucket: dict[tuple[int, int], datetime],
        member: discord.Member,
        *,
        replace: bool = False,
    ) -> None:
        key = self._session_key(member)
        if replace or key not in bucket:
            bucket[key] = discord.utils.utcnow()

    def _stop_session(self, bucket: dict[tuple[int, int], datetime], member: discord.Member) -> str | None:
        return _format_duration(bucket.pop(self._session_key(member), None))

    def _remember_managed_nickname_update(self, member: discord.Member) -> None:
        self._managed_nickname_updates[self._session_key(member)] = discord.utils.utcnow()

    def _was_recent_managed_nickname_update(self, member: discord.Member, *, seconds: int = 10) -> bool:
        stamp = self._managed_nickname_updates.get(self._session_key(member))
        if stamp is None:
            return False
        return discord.utils.utcnow() - stamp <= timedelta(seconds=seconds)

    @staticmethod
    def _default_member_name(member: discord.Member) -> str:
        return (member.global_name or member.name).strip()

    def _configured_prefixes(self, member: discord.Member) -> list[str]:
        configured_roles = [
            role
            for role in member.roles
            if role.id in self.config.nickname_prefix_rules and not role.is_default()
        ]
        configured_roles.sort(key=lambda role: (-role.position, role.id))
        prefixes: list[str] = []
        for role in configured_roles:
            prefix = self.config.nickname_prefix_rules[role.id]
            if prefix not in prefixes:
                prefixes.append(prefix)
        return prefixes

    def _strip_known_prefixes(self, value: str) -> str:
        cleaned = value.strip()
        known_prefixes = sorted(set(self.config.nickname_prefix_rules.values()), key=len, reverse=True)
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in known_prefixes:
                if cleaned.startswith(f"{prefix} "):
                    cleaned = cleaned[len(prefix) + 1 :].lstrip()
                    changed = True
                    break
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix) :].lstrip()
                    changed = True
                    break
        return cleaned.strip()

    def _truncate_nickname(self, nickname: str) -> str:
        return nickname[:32].rstrip()

    def _desired_member_nickname(self, member: discord.Member) -> str | None:
        prefixes = self._configured_prefixes(member)
        raw_current = member.nick or self._default_member_name(member)
        base_name = self._strip_known_prefixes(raw_current) or self._default_member_name(member)

        if prefixes:
            prefix_text = " ".join(prefixes)
            desired = self._truncate_nickname(f"{prefix_text} {base_name}".strip())
            return desired or self._truncate_nickname(prefix_text)

        if member.nick is None:
            return None

        stripped_nick = self._strip_known_prefixes(member.nick)
        if not stripped_nick:
            return None
        if stripped_nick == self._default_member_name(member):
            return None
        return self._truncate_nickname(stripped_nick)

    async def enforce_member_nickname(self, member: discord.Member) -> bool:
        if member.bot or not self.config.nickname_prefix_rules:
            return False
        me = member.guild.me
        if me is None or not me.guild_permissions.manage_nicknames:
            return False
        if member == member.guild.owner:
            return False
        if member.top_role >= me.top_role:
            return False

        desired_nick = self._desired_member_nickname(member)
        if desired_nick == member.nick:
            return False
        if desired_nick is None and member.nick is None:
            return False

        try:
            self._remember_managed_nickname_update(member)
            await member.edit(
                nick=desired_nick,
                reason="EVA Assistant: синхронизация префикса ника по ролям",
            )
        except (discord.Forbidden, discord.HTTPException):
            return False
        return True

    @staticmethod
    def _format_voice_company(channel: discord.VoiceChannel | discord.StageChannel | None, member: discord.Member) -> str:
        if channel is None:
            return "Неизвестно"
        companions = [other for other in channel.members if other.id != member.id and not other.bot]
        if not companions:
            return "Сидел один. Король комнаты."
        labels = [other.mention for other in companions[:12]]
        if len(companions) > 12:
            labels.append(f"и ещё {len(companions) - 12}")
        return ", ".join(labels)

    async def _log_voice_session_finished(
        self,
        member: discord.Member,
        channel: discord.VoiceChannel | discord.StageChannel | None,
        *,
        duration: str | None,
        destination: discord.VoiceChannel | discord.StageChannel | None = None,
        actor: discord.abc.User | None = None,
        reason: str | None = None,
    ) -> None:
        if channel is None or duration is None:
            return

        description = (
            f"**{_display_name(member)}** покинул {channel.mention} после **{duration}** в эфире."
            if destination is None
            else f"**{_display_name(member)}** завершил сессию в {channel.mention} спустя **{duration}** и уехал в {destination.mention}."
        )
        fields: list[tuple[str, str, bool]] = [
            ("Канал", self.audit.format_channel(channel), False),
            ("Пробыл", duration, True),
            ("С кем сидел", self._format_voice_company(channel, member), False),
        ]
        if destination is not None:
            fields.append(("Куда ушёл", self.audit.format_channel(destination), False))

        await self.audit.send_event(
            member.guild,
            "member_voice_session_finished",
            description,
            actor=actor,
            target=member,
            reason=reason,
            fields=fields,
            show_actor_field=actor is not None,
            actor_label="Кто помог закончить сессию",
            target_label="Участник",
            thumbnail_target=member,
            related_channels=[channel, destination],
            related_users=[member, actor],
            include_case_id=False,
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
        if self.config.enable_members_intent and self.config.nickname_prefix_rules:
            for member in guild.members:
                await self.enforce_member_nickname(member)
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

    async def find_member_disconnect_entry(
        self,
        member: discord.Member,
        *,
        max_age_seconds: int = 10,
    ) -> discord.AuditLogEntry | None:
        deadline = discord.utils.utcnow() - timedelta(seconds=max_age_seconds)
        fallback: discord.AuditLogEntry | None = None
        try:
            async for entry in member.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_disconnect):
                if entry.created_at < deadline:
                    break
                if getattr(entry.target, "id", None) == member.id:
                    return entry
                extra = getattr(entry, "extra", None)
                extra_count = int(getattr(extra, "count", 0) or 0)
                if fallback is None and extra_count == 1:
                    fallback = entry
        except (discord.Forbidden, discord.HTTPException):
            return None

        return fallback

    async def fetch_message_excerpt(
        self,
        channel: discord.TextChannel | discord.Thread,
        message_id: int,
    ) -> list[tuple[str, str, bool]]:
        try:
            message = await channel.fetch_message(message_id)
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            return []

        fields: list[tuple[str, str, bool]] = [
            ("Сообщение", _format_deleted_message_body(message, message_content_intent_enabled=self.config.enable_message_content_intent), False),
        ]
        attachments = _format_attachments(message)
        if attachments:
            fields.append(("Вложения", attachments, False))
        reference = _format_reference(message)
        if reference:
            fields.append(("Ответ на", reference, False))
        return fields

    async def resolve_member(self, guild: discord.Guild, value: Any) -> discord.Member | None:
        member_id = getattr(value, "id", None)
        if member_id is None:
            return None
        member = guild.get_member(member_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(member_id)
        except (discord.Forbidden, discord.HTTPException):
            return None

    def is_audit_channel(self, guild: discord.Guild, channel: discord.abc.GuildChannel | discord.Thread | None) -> bool:
        if channel is None:
            return False
        saved = self.store.get_guild(guild.id)
        if int(channel.id) in {int(value) for value in saved["channels"].values()}:
            return True
        category_id = getattr(channel, "category_id", None)
        return category_id is not None and int(category_id) == int(saved.get("category_id") or 0)

    def get_ignored_channel_ids(self, guild_id: int) -> set[int]:
        return self.store.get_ignored_ids(guild_id, "channel_ids") | set(self.config.ignored_channel_ids)

    def get_protected_voice_guard_user_ids(self, guild: discord.Guild) -> set[int]:
        protected = set(self.config.protected_voice_guard_user_ids)
        protected.add(guild.owner_id)
        return protected

    def is_protected_voice_guard_target(self, member: discord.Member) -> bool:
        if not self.config.protected_voice_guard_enabled:
            return False
        return member.id in self.get_protected_voice_guard_user_ids(member.guild)

    def is_ignored_channel_id(self, guild_id: int, channel_id: int | None) -> bool:
        return channel_id is not None and int(channel_id) in self.get_ignored_channel_ids(guild_id)

    def is_ignored_channel(self, guild: discord.Guild, channel: discord.abc.GuildChannel | discord.Thread | None) -> bool:
        if channel is None:
            return False
        ignored_channel_ids = self.get_ignored_channel_ids(guild.id)
        ignored_category_ids = self.store.get_ignored_ids(guild.id, "category_ids")
        if int(channel.id) in ignored_channel_ids:
            return True
        parent_id = getattr(channel, "parent_id", None)
        if parent_id is not None and int(parent_id) in ignored_channel_ids:
            return True
        category_id = getattr(channel, "category_id", None)
        return category_id is not None and int(category_id) in ignored_category_ids

    def should_reply_with_banter(self, message: discord.Message) -> bool:
        if not self.config.chat_banter_enabled:
            return False
        if message.guild is None or message.author.bot:
            return False
        if not message.content or not message.content.strip():
            return False
        if message.type not in {discord.MessageType.default, discord.MessageType.reply}:
            return False
        if message.webhook_id is not None:
            return False
        if isinstance(message.channel, (discord.TextChannel, discord.Thread)) and self.is_ignored_channel(message.guild, message.channel):
            return False
        if isinstance(message.channel, (discord.TextChannel, discord.Thread)) and self.is_audit_channel(message.guild, message.channel):
            return False
        if not CHAT_BANTER.contains_trigger(message.content):
            return False

        now = discord.utils.utcnow()
        channel_key = (message.guild.id, message.channel.id)
        user_key = (message.guild.id, message.author.id)
        channel_stamp = self._chat_banter_last_channel_reply.get(channel_key)
        user_stamp = self._chat_banter_last_user_reply.get(user_key)
        if channel_stamp is not None and now - channel_stamp < timedelta(seconds=self.config.chat_banter_channel_cooldown_seconds):
            return False
        if user_stamp is not None and now - user_stamp < timedelta(seconds=self.config.chat_banter_user_cooldown_seconds):
            return False
        if random.random() > self.config.chat_banter_reply_chance:
            return False
        return True

    def remember_banter_reply(self, message: discord.Message, reply_text: str) -> None:
        now = discord.utils.utcnow()
        channel_key = (message.guild.id, message.channel.id)  # type: ignore[arg-type]
        user_key = (message.guild.id, message.author.id)  # type: ignore[arg-type]
        self._chat_banter_last_channel_reply[channel_key] = now
        self._chat_banter_last_user_reply[user_key] = now
        self._chat_banter_last_channel_text[channel_key] = reply_text

    async def maybe_trigger_protected_voice_guard(
        self,
        *,
        target: discord.Member,
        actor: discord.abc.User | None,
        source_channel: discord.VoiceChannel | discord.StageChannel | None,
        audit_entry_id: int | None = None,
    ) -> None:
        if actor is None or actor.bot:
            return
        if source_channel is None:
            return
        if not self.is_protected_voice_guard_target(target):
            return

        protected_ids = self.get_protected_voice_guard_user_ids(target.guild)
        if actor.id in protected_ids or actor.id == target.id or self.bot.user is None or actor.id == self.bot.user.id:
            return

        key = (target.guild.id, target.id, actor.id, audit_entry_id)
        stamp = self._protected_voice_guard_recent.get(key)
        now = discord.utils.utcnow()
        cooldown_seconds = 5 if audit_entry_id is None else 120
        if stamp is not None and now - stamp <= timedelta(seconds=cooldown_seconds):
            return
        self._protected_voice_guard_recent[key] = now

        actor_member = await self.resolve_member(target.guild, actor)
        actor_user: discord.abc.User = actor_member if actor_member is not None else actor
        warning_text = VOICE_GUARD.render_warning(
            target_name=_display_name(target),
            is_owner_target=target.id == target.guild.owner_id,
        )

        try:
            await actor_user.send(warning_text)
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass

        if actor_member is None or actor_member.voice.channel is None:
            return

        try:
            await actor_member.move_to(
                None,
                reason=(
                    "EVA protected voice guard: "
                    f"{target.display_name} is protected against forced disconnects."
                ),
            )
        except (discord.Forbidden, discord.HTTPException):
            return

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
        lines.append(f"Префиксы ников: `{len(self.config.nickname_prefix_rules)}`")
        protected_voice_guard_count = len(self.get_protected_voice_guard_user_ids(interaction.guild))
        lines.append(
            "Voice guard:"
            f" enabled={_bool_label(self.config.protected_voice_guard_enabled)},"
            f" protected={protected_voice_guard_count},"
            f" phrases={VOICE_GUARD.variants_count}"
        )
        lines.append(
            "Chat EVA:"
            f" enabled={_bool_label(self.config.chat_banter_enabled)},"
            f" chance={self.config.chat_banter_reply_chance:.2f},"
            f" variants={CHAT_BANTER.reply_variants_count}"
        )
        lines.append(
            "PUBG lookup:"
            f" enabled={_bool_label(self.config.pubg_lookup_enabled)},"
            f" configured={_bool_label(self.pubg_lookup.is_configured)},"
            f" channels={self.pubg_lookup.channel_count()},"
            f" roles={self.pubg_lookup.allowed_role_count()},"
            f" platform={self.config.pubg_platform},"
            f" ranked={_bool_label(self.config.pubg_lookup_include_ranked)},"
            f" lifetime={_bool_label(self.config.pubg_lookup_include_lifetime_stats)},"
            f" steam_key={_bool_label(self.pubg_lookup.has_steam_key())}"
        )
        ignored = saved["ignored"]
        ignored_channel_count = len(self.get_ignored_channel_ids(interaction.guild.id))
        lines.append(
            "Ignore:"
            f" channels={ignored_channel_count},"
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
        if action_value == 20:
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
        elif action_value == 21:
            removed = getattr(entry.extra, "members_removed", None)
            prune_days = getattr(entry.extra, "delete_member_days", None)
            fields = []
            if removed is not None:
                fields.append(("Сколько убрало", str(removed), True))
            if prune_days is not None:
                fields.append(("Неактивность от", f"{prune_days} дн.", True))
            await self.audit.send_event(
                guild,
                "members_pruned",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} устроил массовую чистку неактивных участников.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
                include_case_id=False,
            )
        elif action_value == 22:
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
                related_channel_ids=[getattr(target, "id", None)],
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
                related_channels=[target if isinstance(target, discord.abc.GuildChannel) else None],
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
                related_channels=[target if isinstance(target, discord.Thread) else None],
                related_channel_ids=[getattr(target, "id", None)],
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
                related_channels=[target if isinstance(target, discord.Thread) else None],
                related_channel_ids=[getattr(target, "id", None)],
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
                related_channels=[target if isinstance(target, discord.Thread) else None],
                related_channel_ids=[getattr(target, "id", None)],
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
            target_member = await self.resolve_member(guild, target)

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
                if target_member is not None:
                    await self.enforce_member_nickname(target_member)

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
                if target_member is not None:
                    await self.enforce_member_nickname(target_member)
        elif action_value == 28:
            await self.audit.send_event(
                guild,
                "bot_added",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} добавил на сервер бота **{_display_name(target)}**.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                fields=[
                    (
                        "Аккаунт бота создан",
                        discord.utils.format_dt(target.created_at, style="F")
                        if isinstance(target, (discord.Member, discord.User))
                        else "Неизвестно",
                        False,
                    )
                ],
                related_users=[entry.user, target],
                thumbnail_target=target,
            )
        elif action_value == 40:
            code, fields = _invite_entry_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "invite_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} выкатил приглашение **{code}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.target, "channel", None), getattr(entry.after, "channel", None)],
                related_users=[entry.user, getattr(entry.target, "inviter", None), getattr(entry.after, "inviter", None)],
            )
        elif action_value == 41:
            code, fields = _invite_entry_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "invite_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} освежил настройки приглашения **{code}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.target, "channel", None), getattr(entry.after, "channel", None)],
                related_users=[entry.user, getattr(entry.target, "inviter", None), getattr(entry.after, "inviter", None)],
            )
        elif action_value == 42:
            code, fields = _invite_entry_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "invite_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} прикрыл приглашение **{code}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.before, "channel", None), getattr(entry.target, "channel", None)],
                related_users=[entry.user, getattr(entry.before, "inviter", None), getattr(entry.target, "inviter", None)],
            )
        elif action_value == 60:
            emoji_name, fields = _emoji_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "emoji_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} добавил эмодзи **{discord.utils.escape_markdown(emoji_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 61:
            emoji_name, fields = _emoji_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "emoji_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил эмодзи **{discord.utils.escape_markdown(emoji_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 62:
            emoji_name, fields = _emoji_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "emoji_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} убрал эмодзи **{discord.utils.escape_markdown(emoji_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value in {74, 75}:
            channel = getattr(entry.extra, "channel", None)
            message_id = getattr(entry.extra, "message_id", None)
            action_key = "message_pinned" if action_value == 74 else "message_unpinned"
            action_text = "приколол" if action_value == 74 else "открепил"
            actor_label = "Кто закрепил" if action_value == 74 else "Кто открепил"
            fields: list[tuple[str, str, bool]] = []
            if channel is not None:
                fields.append(("Канал", self.audit.format_channel(channel), False))
            if message_id is not None:
                fields.append(("Message ID", f"`{message_id}`", True))
                if channel is not None and getattr(channel, "id", None) is not None:
                    fields.append(("Ссылка", _message_jump_url(guild.id, channel.id, message_id), False))
                    if isinstance(channel, (discord.TextChannel, discord.Thread)):
                        fields.extend(await self.fetch_message_excerpt(channel, message_id))
            await self.audit.send_event(
                guild,
                action_key,
                f"{_display_name(entry.user, 'Кто-то из стаффа')} {action_text} сообщение **{_display_name(target, 'без автора')}**.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                fields=fields,
                show_actor_field=True,
                show_target_field=target is not None,
                actor_label=actor_label,
                target_label="Чьё сообщение",
                thumbnail_target=target,
                related_channels=[channel],
                related_users=[entry.user, target],
                include_case_id=False,
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
        elif action_value == 83:
            stage_topic, fields = _stage_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "stage_instance_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} открыл сцену **{discord.utils.escape_markdown(stage_topic)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.extra, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 84:
            stage_topic, fields = _stage_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "stage_instance_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил сцену **{discord.utils.escape_markdown(stage_topic)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.extra, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 85:
            stage_topic, fields = _stage_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "stage_instance_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} закрыл сцену **{discord.utils.escape_markdown(stage_topic)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.extra, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 90:
            sticker_name, fields = _sticker_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "sticker_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} добавил стикер **{discord.utils.escape_markdown(sticker_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 91:
            sticker_name, fields = _sticker_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "sticker_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил стикер **{discord.utils.escape_markdown(sticker_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 92:
            sticker_name, fields = _sticker_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "sticker_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} убрал стикер **{discord.utils.escape_markdown(sticker_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 100:
            event_name, fields = _scheduled_event_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "scheduled_event_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} создал событие **{discord.utils.escape_markdown(event_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.target, "channel", None), getattr(entry.after, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 101:
            event_name, fields = _scheduled_event_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "scheduled_event_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил событие **{discord.utils.escape_markdown(event_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.target, "channel", None), getattr(entry.after, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 102:
            event_name, fields = _scheduled_event_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "scheduled_event_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} отменил событие **{discord.utils.escape_markdown(event_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.before, "channel", None), getattr(entry.target, "channel", None)],
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
        elif action_value == 130:
            sound_name, fields = _soundboard_snapshot(entry)
            await self.audit.send_event(
                guild,
                "soundboard_sound_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} добавил звук **{discord.utils.escape_markdown(sound_name)}** на саунд-панель.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 131:
            sound_name, fields = _soundboard_snapshot(entry)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "soundboard_sound_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил звук **{discord.utils.escape_markdown(sound_name)}** на саунд-панели.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 132:
            sound_name, fields = _soundboard_snapshot(entry)
            await self.audit.send_event(
                guild,
                "soundboard_sound_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} убрал звук **{discord.utils.escape_markdown(sound_name)}** с саунд-панели.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 140:
            rule_name, fields = _automod_rule_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "automod_rule_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} создал правило автомода **{discord.utils.escape_markdown(rule_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 141:
            rule_name, fields = _automod_rule_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "automod_rule_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} подкрутил правило автомода **{discord.utils.escape_markdown(rule_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 142:
            rule_name, fields = _automod_rule_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "automod_rule_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} снял с дежурства правило автомода **{discord.utils.escape_markdown(rule_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value in {143, 144, 145, 146}:
            extra = entry.extra
            channel = getattr(extra, "channel", None)
            rule_name = getattr(extra, "automod_rule_name", "Неизвестное правило")
            trigger_type = getattr(extra, "automod_rule_trigger_type", None)
            key_map = {
                143: "automod_action_blocked",
                144: "automod_action_flagged",
                145: "automod_action_timeout",
                146: "automod_action_quarantined",
            }
            description_map = {
                143: f"Автомод остановил сообщение участника **{_display_name(target)}** ещё на подлёте.",
                144: f"Автомод поднял флаг на участника **{_display_name(target)}** и позвал модерацию посмотреть.",
                145: f"Автомод выдал тайм-аут участнику **{_display_name(target)}**.",
                146: f"Автомод ограничил взаимодействия участнику **{_display_name(target)}**.",
            }
            fields = [
                ("Правило", f"**{discord.utils.escape_markdown(str(rule_name))}**", False),
                ("Триггер", self.audit.format_change_value(trigger_type) if trigger_type is not None else "Неизвестно", True),
            ]
            if channel is not None:
                fields.append(("Канал", self.audit.format_channel(channel), False))
            await self.audit.send_event(
                guild,
                key_map[action_value],
                description_map[action_value],
                actor=entry.user if entry.user is not None else None,
                target=target,
                reason=entry.reason,
                fields=fields,
                show_actor_field=False,
                show_target_field=target is not None,
                target_label="Участник",
                thumbnail_target=target,
                related_channels=[channel],
                related_users=[entry.user, target],
                include_case_id=action_value in {145, 146},
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
        await self.enforce_member_nickname(member)
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
        skip_nickname_log = self._was_recent_managed_nickname_update(after)

        if before.nick != after.nick and not skip_nickname_log:
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

        if before.nick != after.nick or before.roles != after.roles:
            await self.enforce_member_nickname(after)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await handle_on_message(self, message)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        await handle_on_message_delete(self, message)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        await handle_on_raw_message_delete(self, payload)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        await handle_on_raw_bulk_message_delete(self, payload)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        await handle_on_message_edit(self, before, after)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        await handle_on_raw_message_edit(self, payload)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        await handle_on_voice_state_update(self, member, before, after)


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
