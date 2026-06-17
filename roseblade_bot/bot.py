"""
EVA Assistant core bot logic and Discord event handlers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import date, datetime, timedelta
import random
from typing import Any
import unicodedata

import discord
from discord import app_commands
from discord.ext import commands, tasks

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
from roseblade_bot.steam_digest import SteamDigestService
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
        self._nickname_sync_queue: deque[tuple[int, int]] = deque()
        self._nickname_sync_pending: set[tuple[int, int]] = set()
        self._chat_banter_last_channel_reply: dict[tuple[int, int], datetime] = {}
        self._chat_banter_last_user_reply: dict[tuple[int, int], datetime] = {}
        self._chat_banter_last_channel_text: dict[tuple[int, int], str] = {}
        self._protected_voice_guard_recent: dict[tuple[int, int, int, int | None], datetime] = {}
        self._protected_ban_startup_check_done = False
        self.pubg_lookup = PubgLookupService(config)
        self.steam_digest = SteamDigestService(config)
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

    @staticmethod
    def _normalize_prefix_token(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        return "".join(ch for ch in normalized if ch not in {"\ufe0e", "\ufe0f"}).strip()

    def _prefix_variants(self, prefix: str) -> list[str]:
        variants: list[str] = []
        seen: set[str] = set()
        for candidate in (prefix.strip(), self._normalize_prefix_token(prefix)):
            cleaned = candidate.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                variants.append(cleaned)
        variants.sort(key=len, reverse=True)
        return variants

    def _nickname_prefix_signature(self) -> str:
        role_chunks = [
            f"{role_id}={self._normalize_prefix_token(prefix)}"
            for role_id, prefix in sorted(self.config.nickname_prefix_rules.items())
        ]
        legacy_chunks = [self._normalize_prefix_token(prefix) for prefix in sorted(self.config.nickname_prefix_legacy_prefixes)]
        excluded_chunks = [str(user_id) for user_id in sorted(self.config.nickname_prefix_excluded_user_ids)]
        return "|".join(role_chunks) + "::" + "|".join(legacy_chunks) + "::" + "|".join(excluded_chunks)

    def _nickname_prefix_state(self, guild_id: int) -> dict[str, Any]:
        return self.store.get_service_state(guild_id, "nickname_prefix")

    def _persist_known_nickname_prefixes(self, guild_id: int) -> set[str]:
        state = self._nickname_prefix_state(guild_id)
        known_prefixes = {str(value).strip() for value in state.get("known_prefixes", []) if str(value).strip()}
        known_prefixes.update(prefix.strip() for prefix in self.config.nickname_prefix_rules.values() if prefix.strip())
        known_prefixes.update(prefix.strip() for prefix in self.config.nickname_prefix_legacy_prefixes if prefix.strip())
        updated = sorted(known_prefixes)
        if updated != state.get("known_prefixes", []):
            state["known_prefixes"] = updated
            self.store.set_service_state(guild_id, "nickname_prefix", state)
        return set(updated)

    def _known_nickname_prefixes(self, guild_id: int) -> list[str]:
        known_prefixes = self._persist_known_nickname_prefixes(guild_id)
        variants: list[str] = []
        seen_variants: set[str] = set()
        for prefix in known_prefixes:
            for variant in self._prefix_variants(prefix):
                if variant not in seen_variants:
                    seen_variants.add(variant)
                    variants.append(variant)
        variants.sort(key=len, reverse=True)
        return variants

    def queue_member_nickname_sync(self, member: discord.Member) -> bool:
        key = self._session_key(member)
        if key in self._nickname_sync_pending:
            return False
        self._nickname_sync_pending.add(key)
        self._nickname_sync_queue.append(key)
        return True

    def _configured_prefix(self, member: discord.Member) -> str | None:
        configured_roles = [
            role
            for role in member.roles
            if role.id in self.config.nickname_prefix_rules and not role.is_default()
        ]
        if not configured_roles:
            return None
        configured_roles.sort(key=lambda role: (-role.position, -role.id))
        return self.config.nickname_prefix_rules[configured_roles[0].id]

    def _strip_known_prefixes(self, guild_id: int, value: str) -> str:
        cleaned = value.strip()
        known_prefixes = self._known_nickname_prefixes(guild_id)
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
        prefix = self._configured_prefix(member)
        raw_current = member.nick or self._default_member_name(member)
        base_name = self._strip_known_prefixes(member.guild.id, raw_current) or self._default_member_name(member)

        if prefix:
            desired = self._truncate_nickname(f"{prefix} {base_name}".strip())
            return desired or self._truncate_nickname(prefix)

        if member.nick is None:
            return None

        stripped_nick = self._strip_known_prefixes(member.guild.id, member.nick)
        if not stripped_nick:
            return None
        if stripped_nick == self._default_member_name(member):
            return None
        return self._truncate_nickname(stripped_nick)

    def _member_should_participate_in_nickname_sync(self, member: discord.Member) -> bool:
        if member.bot or member.id in self.config.nickname_prefix_excluded_user_ids:
            return False
        if any(role.id in self.config.nickname_prefix_rules for role in member.roles if not role.is_default()):
            return True
        if member.nick:
            for prefix in self._known_nickname_prefixes(member.guild.id):
                if member.nick.startswith(prefix) or member.nick.startswith(f"{prefix} "):
                    return True
        return False

    async def queue_guild_nickname_resync(
        self,
        guild: discord.Guild,
        *,
        reason: str,
        full: bool,
    ) -> int:
        if not self.config.enable_members_intent or not self.config.nickname_prefix_rules:
            return 0
        self._persist_known_nickname_prefixes(guild.id)
        if not guild.chunked:
            try:
                await guild.chunk(cache=True)
            except (discord.Forbidden, discord.HTTPException):
                pass

        queued = 0
        for member in guild.members:
            if full or self._member_should_participate_in_nickname_sync(member):
                if self.queue_member_nickname_sync(member):
                    queued += 1

        state = self._nickname_prefix_state(guild.id)
        state["last_queue_reason"] = reason
        state["last_queue_at"] = discord.utils.utcnow().isoformat()
        state["last_queue_size"] = queued
        self.store.set_service_state(guild.id, "nickname_prefix", state)
        return queued

    async def enforce_member_nickname(self, member: discord.Member) -> bool:
        if member.bot or not self.config.nickname_prefix_rules:
            return False
        if member.id in self.config.nickname_prefix_excluded_user_ids:
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
            await member.edit(
                nick=desired_nick,
                reason="EVA Assistant: синхронизация префикса ника по ролям",
            )
        except (discord.Forbidden, discord.HTTPException):
            return False
        self._remember_managed_nickname_update(member)
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
        if self.steam_digest.is_configured and not self.steam_digest_scheduler.is_running():
            self.steam_digest_scheduler.start()
        if self.config.enable_members_intent and self.config.nickname_prefix_rules and not self.nickname_sync_worker.is_running():
            self.nickname_sync_worker.start()
        if self.config.enable_members_intent and self.config.nickname_prefix_rules and not self.nickname_resync_scheduler.is_running():
            self.nickname_resync_scheduler.start()
        if self.config.protected_bans_enabled and not self.protected_ban_enforcer.is_running():
            self.protected_ban_enforcer.start()

    def cog_unload(self) -> None:
        if self.steam_digest_scheduler.is_running():
            self.steam_digest_scheduler.cancel()
        if self.nickname_sync_worker.is_running():
            self.nickname_sync_worker.cancel()
        if self.nickname_resync_scheduler.is_running():
            self.nickname_resync_scheduler.cancel()
        if self.protected_ban_enforcer.is_running():
            self.protected_ban_enforcer.cancel()

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
            await self.run_startup_protected_ban_check()
            return

        for guild in self.bot.guilds:
            await self.bootstrap_guild(guild)
        await self.run_startup_protected_ban_check()

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
            service_state = self._nickname_prefix_state(guild.id)
            signature = self._nickname_prefix_signature()
            self._persist_known_nickname_prefixes(guild.id)
            if service_state.get("signature") != signature:
                queued = await self.queue_guild_nickname_resync(
                    guild,
                    reason="config_signature_changed",
                    full=True,
                )
                service_state["signature"] = signature
                service_state["last_bootstrap_queue_at"] = discord.utils.utcnow().isoformat()
                service_state["last_bootstrap_queue_size"] = queued
                self.store.set_service_state(guild.id, "nickname_prefix", service_state)
        self._bootstrapped_guild_ids.add(guild.id)

    @tasks.loop(seconds=1.5)
    async def nickname_sync_worker(self) -> None:
        if not self._nickname_sync_queue:
            return
        guild_id, user_id = self._nickname_sync_queue.popleft()
        self._nickname_sync_pending.discard((guild_id, user_id))

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return

        member: discord.Member | None = None
        if self.config.enable_members_intent:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                member = guild.get_member(user_id)
        else:
            member = guild.get_member(user_id)
        if member is None:
            return

        await self.enforce_member_nickname(member)

    @tasks.loop(minutes=5)
    async def nickname_resync_scheduler(self) -> None:
        if not self.config.enable_members_intent or not self.config.nickname_prefix_rules:
            return
        if self.config.nickname_prefix_resync_minutes <= 0:
            return

        now = discord.utils.utcnow()
        for guild in self.bot.guilds:
            state = self._nickname_prefix_state(guild.id)
            last_scan_raw = state.get("last_resync_scan_at")
            last_scan: datetime | None = None
            if isinstance(last_scan_raw, str):
                try:
                    last_scan = datetime.fromisoformat(last_scan_raw)
                except ValueError:
                    last_scan = None
            if last_scan is not None and now - last_scan < timedelta(minutes=self.config.nickname_prefix_resync_minutes):
                continue

            queued = await self.queue_guild_nickname_resync(
                guild,
                reason="periodic_resync",
                full=False,
            )
            state = self._nickname_prefix_state(guild.id)
            state["last_resync_scan_at"] = now.isoformat()
            state["last_resync_scan_queued"] = queued
            self.store.set_service_state(guild.id, "nickname_prefix", state)

    async def enforce_protected_bans(self, *, force: bool, source: str) -> dict[int, int]:
        if not self.config.protected_bans_enabled:
            return {}
        if not force and self.config.protected_bans_enforce_minutes <= 0:
            return {}

        restored_by_guild: dict[int, int] = {}
        now = discord.utils.utcnow()
        for guild in self.bot.guilds:
            state = self._protected_bans_state(guild.id)
            if not force:
                last_run_raw = state.get("last_enforce_at")
                last_run: datetime | None = None
                if isinstance(last_run_raw, str):
                    try:
                        last_run = datetime.fromisoformat(last_run_raw)
                    except ValueError:
                        last_run = None
                if last_run is not None and now - last_run < timedelta(minutes=self.config.protected_bans_enforce_minutes):
                    continue

            restored = 0
            entries = list(self._protected_ban_entries(guild.id).values())
            for entry in entries:
                user_id = int(entry.get("user_id", 0) or 0)
                if user_id <= 0:
                    continue
                try:
                    await guild.fetch_ban(discord.Object(id=user_id))
                    continue
                except discord.NotFound:
                    pass
                except (discord.Forbidden, discord.HTTPException):
                    continue

                try:
                    await guild.ban(
                        discord.Object(id=user_id),
                        reason="EVA protected perma-ban: периодическая проверка вернула бан обратно",
                    )
                    restored += 1
                except (discord.Forbidden, discord.HTTPException):
                    continue

            state = self._protected_bans_state(guild.id)
            state["last_enforce_at"] = now.isoformat()
            state["last_enforce_restored"] = restored
            state["last_enforce_source"] = source
            self.store.set_service_state(guild.id, "protected_bans", state)
            restored_by_guild[guild.id] = restored

        return restored_by_guild

    async def run_startup_protected_ban_check(self) -> None:
        if not self.config.protected_bans_enabled or self._protected_ban_startup_check_done:
            return
        if self.config.protected_bans_auto_capture:
            for guild in self.bot.guilds:
                await self.sync_current_bans_to_protected(guild)
        await self.enforce_protected_bans(force=True, source="startup")
        self._protected_ban_startup_check_done = True

    @tasks.loop(minutes=1)
    async def protected_ban_enforcer(self) -> None:
        await self.enforce_protected_bans(force=False, source="scheduler")

    @tasks.loop(minutes=1)
    async def steam_digest_scheduler(self) -> None:
        if not self.steam_digest.is_configured:
            return

        now = datetime.now(self.steam_digest.timezone)
        if not self.steam_digest.is_due(now):
            return

        target_channels: list[discord.TextChannel] = []
        today = self.steam_digest.local_today(now, self.steam_digest.timezone)
        for channel_id in sorted(self.config.steam_digest_channel_ids):
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except (discord.Forbidden, discord.HTTPException):
                    continue
            if not isinstance(channel, discord.TextChannel):
                continue
            if self._steam_digest_was_sent_today(channel.guild.id, channel.id, today):
                continue
            target_channels.append(channel)

        if not target_channels:
            return

        try:
            report = await self.steam_digest.build_report()
        except Exception as error:
            print(f"Steam digest build failed: {error}")
            return

        for channel in target_channels:
            embed = self.steam_digest.build_embed(report)
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                continue
            self._mark_steam_digest_sent(channel.guild.id, channel.id, today)

    @steam_digest_scheduler.before_loop
    async def before_steam_digest_scheduler(self) -> None:
        await self.bot.wait_until_ready()

    @steam_digest_scheduler.error
    async def steam_digest_scheduler_error(self, error: Exception) -> None:
        print(f"Steam digest scheduler crashed: {error}")

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

    def _protected_bans_state(self, guild_id: int) -> dict[str, Any]:
        return self.store.get_service_state(guild_id, "protected_bans")

    def _protected_ban_entries(self, guild_id: int) -> dict[str, dict[str, Any]]:
        state = self._protected_bans_state(guild_id)
        entries = state.get("entries")
        if not isinstance(entries, dict):
            entries = {}
            state["entries"] = entries
            self.store.set_service_state(guild_id, "protected_bans", state)
        return entries

    def is_protected_ban(self, guild_id: int, user_id: int) -> bool:
        return str(user_id) in self._protected_ban_entries(guild_id)

    def protected_ban_count(self, guild_id: int) -> int:
        return len(self._protected_ban_entries(guild_id))

    def upsert_protected_ban(
        self,
        guild: discord.Guild,
        user: discord.abc.User,
        *,
        actor: discord.abc.User | None = None,
        reason: str | None = None,
        source: str,
    ) -> None:
        state = self._protected_bans_state(guild.id)
        entries = self._protected_ban_entries(guild.id)
        key = str(user.id)
        previous = entries.get(key, {})
        entries[key] = {
            "user_id": int(user.id),
            "username": str(user),
            "display_name": self.audit.display_name(user),
            "reason": reason or previous.get("reason"),
            "protected_at": previous.get("protected_at") or discord.utils.utcnow().isoformat(),
            "last_ban_at": discord.utils.utcnow().isoformat(),
            "protected_by_id": getattr(actor, "id", None) or previous.get("protected_by_id"),
            "protected_by_name": self.audit.display_name(actor) if actor is not None else previous.get("protected_by_name"),
            "source": source,
        }
        state["entries"] = entries
        self.store.set_service_state(guild.id, "protected_bans", state)

    def remove_protected_ban(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        state = self._protected_bans_state(guild_id)
        entries = self._protected_ban_entries(guild_id)
        removed = entries.pop(str(user_id), None)
        state["entries"] = entries
        self.store.set_service_state(guild_id, "protected_bans", state)
        return removed

    def protected_ban_entry(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        return self._protected_ban_entries(guild_id).get(str(user_id))

    async def _ensure_owner_only(self, interaction: discord.Interaction) -> bool:
        assert interaction.guild is not None
        if interaction.user.id == interaction.guild.owner_id:
            return True
        message = "Эта команда только для владельца сервера."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        return False

    @staticmethod
    def _parse_user_id(raw_value: str) -> int:
        digits = "".join(ch for ch in raw_value if ch.isdigit())
        if not digits:
            raise ValueError("user_id")
        return int(digits)

    async def _fetch_recent_unban_entry(
        self,
        guild: discord.Guild,
        target_id: int,
        *,
        attempts: int = 3,
        delay_seconds: float = 1.0,
    ) -> discord.AuditLogEntry | None:
        for attempt in range(attempts):
            entry = await self.audit.fetch_recent_audit_entry(
                guild,
                actions=[discord.AuditLogAction.member_ban_remove],
                target_id=target_id,
                max_age_seconds=30,
            )
            if entry is not None:
                return entry
            if attempt + 1 < attempts:
                await asyncio.sleep(delay_seconds)
        return None

    async def sync_current_bans_to_protected(self, guild: discord.Guild, *, actor: discord.abc.User | None = None) -> int:
        count = 0
        async for ban_entry in guild.bans(limit=None):
            before = self.protected_ban_count(guild.id)
            self.upsert_protected_ban(
                guild,
                ban_entry.user,
                actor=actor,
                reason=ban_entry.reason,
                source="sync_current_bans",
            )
            after = self.protected_ban_count(guild.id)
            if after > before:
                count += 1
        return count

    def _steam_digest_last_sent_by_channel(self, guild_id: int) -> dict[str, str]:
        service_state = self.store.get_service_state(guild_id, "steam_digest")
        channel_dates = service_state.get("last_sent_by_channel")
        if not isinstance(channel_dates, dict):
            channel_dates = {}
            service_state["last_sent_by_channel"] = channel_dates
            self.store.set_service_state(guild_id, "steam_digest", service_state)
        return {str(key): str(value) for key, value in channel_dates.items()}

    def _steam_digest_was_sent_today(self, guild_id: int, channel_id: int, today: date) -> bool:
        last_sent = self._steam_digest_last_sent_by_channel(guild_id).get(str(channel_id))
        return last_sent == today.isoformat()

    def _mark_steam_digest_sent(self, guild_id: int, channel_id: int, today: date) -> None:
        service_state = self.store.get_service_state(guild_id, "steam_digest")
        channel_dates = service_state.get("last_sent_by_channel")
        if not isinstance(channel_dates, dict):
            channel_dates = {}
        channel_dates[str(channel_id)] = today.isoformat()
        service_state["last_sent_by_channel"] = channel_dates
        self.store.set_service_state(guild_id, "steam_digest", service_state)

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

    @staticmethod
    def _banter_snippet(text: str, *, limit: int = 96) -> str:
        single_line = " ".join(text.split())
        if len(single_line) <= limit:
            return single_line
        return single_line[: limit - 3] + "..."

    def log_banter_decision(
        self,
        message: discord.Message,
        *,
        decision: str,
        reason: str,
    ) -> None:
        guild_id = message.guild.id if message.guild is not None else "dm"
        channel_id = getattr(message.channel, "id", "unknown")
        user_id = getattr(message.author, "id", "unknown")
        print(
            "[EVA][banter]"
            f" decision={decision}"
            f" reason={reason}"
            f" guild={guild_id}"
            f" channel={channel_id}"
            f" user={user_id}"
            f" content={self._banter_snippet(message.content)!r}"
        )

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
        has_trigger = CHAT_BANTER.contains_trigger(message.content)
        if isinstance(message.channel, (discord.TextChannel, discord.Thread)) and self.is_ignored_channel(message.guild, message.channel):
            if has_trigger:
                self.log_banter_decision(message, decision="skip", reason="ignored_channel")
            return False
        if isinstance(message.channel, (discord.TextChannel, discord.Thread)) and self.is_audit_channel(message.guild, message.channel):
            if has_trigger:
                self.log_banter_decision(message, decision="skip", reason="audit_channel")
            return False
        if not has_trigger:
            return False

        now = discord.utils.utcnow()
        channel_key = (message.guild.id, message.channel.id)
        user_key = (message.guild.id, message.author.id)
        channel_stamp = self._chat_banter_last_channel_reply.get(channel_key)
        user_stamp = self._chat_banter_last_user_reply.get(user_key)
        if channel_stamp is not None and now - channel_stamp < timedelta(seconds=self.config.chat_banter_channel_cooldown_seconds):
            self.log_banter_decision(message, decision="skip", reason="channel_cooldown")
            return False
        if user_stamp is not None and now - user_stamp < timedelta(seconds=self.config.chat_banter_user_cooldown_seconds):
            self.log_banter_decision(message, decision="skip", reason="user_cooldown")
            return False
        if random.random() > self.config.chat_banter_reply_chance:
            self.log_banter_decision(
                message,
                decision="skip",
                reason=f"chance_{self.config.chat_banter_reply_chance:.2f}",
            )
            return False
        self.log_banter_decision(message, decision="pass", reason="trigger_matched")
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
        # Discord audit log for disconnects can lag and briefly return the previous entry again.
        # Keep the cooldown short so repeated real disconnects after a rejoin still trigger the guard.
        cooldown_seconds = 5
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
        nickname_state = self._nickname_prefix_state(interaction.guild.id)
        protected_bans_state = self._protected_bans_state(interaction.guild.id)

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
        lines.append(
            "Nick sync:"
            f" legacy={len(self.config.nickname_prefix_legacy_prefixes)},"
            f" excluded={len(self.config.nickname_prefix_excluded_user_ids)},"
            f" interval={self.config.nickname_prefix_resync_minutes}m,"
            f" pending={len(self._nickname_sync_queue)},"
            f" last_reason={nickname_state.get('last_queue_reason', 'n/a')}"
        )
        lines.append(
            "Protected bans:"
            f" enabled={_bool_label(self.config.protected_bans_enabled)},"
            f" auto_capture={_bool_label(self.config.protected_bans_auto_capture)},"
            f" count={self.protected_ban_count(interaction.guild.id)},"
            f" enforce={self.config.protected_bans_enforce_minutes}m,"
            f" last_restore={protected_bans_state.get('last_enforce_restored', 0)}"
        )
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
        lines.append(
            "Steam digest:"
            f" enabled={_bool_label(self.config.steam_digest_enabled)},"
            f" configured={_bool_label(self.steam_digest.is_configured)},"
            f" channels={self.steam_digest.channel_count()},"
            f" schedule={self.steam_digest.schedule_label()},"
            f" top={self.config.steam_digest_top_count},"
            f" support={_bool_label(self.config.steam_digest_include_support_stats)}"
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

    @app_commands.command(name="nick_resync", description="Поставить пересборку ник-префиксов в очередь")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def nick_resync(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        queued = await self.queue_guild_nickname_resync(
            interaction.guild,
            reason="manual_resync",
            full=False,
        )
        await interaction.followup.send(
            (
                f"Поставила в очередь **{queued}** участников для пересинхронизации ников. "
                f"Worker идёт по одному участнику примерно раз в **1.5 сек**."
            ),
            ephemeral=True,
        )

    @app_commands.command(name="protected_bans_sync", description="Синхронизировать текущий бан-лист в owner-only защиту")
    @app_commands.guild_only()
    async def protected_bans_sync(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not await self._ensure_owner_only(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not self.config.protected_bans_enabled:
            await interaction.followup.send(
                "Защищённые пермабаны сейчас выключены в конфиге.",
                ephemeral=True,
            )
            return

        added = await self.sync_current_bans_to_protected(interaction.guild, actor=interaction.user)
        await interaction.followup.send(
            f"Синхронизировала текущий бан-лист. В owner-only защиту добавлено **{added}** банов.",
            ephemeral=True,
        )

    @app_commands.command(name="protected_bans_list", description="Показать owner-only список защищённых пермабанов")
    @app_commands.guild_only()
    async def protected_bans_list(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not await self._ensure_owner_only(interaction):
            return
        entries = list(self._protected_ban_entries(interaction.guild.id).values())
        if not entries:
            await interaction.response.send_message("Список защищённых пермабанов сейчас пуст.", ephemeral=True)
            return

        lines = []
        for entry in entries[:40]:
            user_id = int(entry.get("user_id", 0) or 0)
            label = str(entry.get("display_name") or entry.get("username") or user_id)
            reason = str(entry.get("reason") or "без причины")
            lines.append(f"`{user_id}` • {label} • {reason}")
        message = "\n".join(lines)
        if len(entries) > 40:
            message += f"\n... и ещё {len(entries) - 40}"
        await interaction.response.send_message(message[:1900], ephemeral=True)

    @app_commands.command(name="protected_unban", description="Снять owner-only защиту и разбанить пользователя")
    @app_commands.describe(user_id="ID пользователя или упоминание", reason="Причина разбана")
    @app_commands.guild_only()
    async def protected_unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str | None = None,
    ) -> None:
        assert interaction.guild is not None
        if not await self._ensure_owner_only(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            target_id = self._parse_user_id(user_id)
        except ValueError:
            await interaction.followup.send("Не смогла распознать `user_id`.", ephemeral=True)
            return

        removed = self.remove_protected_ban(interaction.guild.id, target_id)
        try:
            await interaction.guild.unban(
                discord.Object(id=target_id),
                reason=reason or f"EVA protected unban by owner {interaction.user}",
            )
        except discord.NotFound:
            await interaction.followup.send(
                "Этого пользователя уже нет в бан-листе. Защиту я всё равно сняла." if removed else "Этого пользователя уже нет в бан-листе.",
                ephemeral=True,
            )
            return
        except (discord.Forbidden, discord.HTTPException) as error:
            if removed is not None:
                state = self._protected_bans_state(interaction.guild.id)
                entries = self._protected_ban_entries(interaction.guild.id)
                entries[str(target_id)] = removed
                state["entries"] = entries
                self.store.set_service_state(interaction.guild.id, "protected_bans", state)
            await interaction.followup.send(f"Не смогла разбанить пользователя: {error}", ephemeral=True)
            return

        await interaction.followup.send(
            f"Пользователь `{target_id}` снят с owner-only защиты и разбанен.",
            ephemeral=True,
        )

    @app_commands.command(name="steam_digest_now", description="Отправить тестовый Steam-дайджест в текущий канал")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def steam_digest_now(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not self.steam_digest.is_configured:
            await interaction.followup.send(
                "Steam-дайджест сейчас выключен или для него не заданы каналы в конфиге.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if channel is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.followup.send(
                "В этот тип канала я тестовый дайджест не отправлю. Нужен обычный текстовый канал или ветка.",
                ephemeral=True,
            )
            return

        try:
            report = await self.steam_digest.build_report()
            embed = self.steam_digest.build_embed(report)
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as error:
            await interaction.followup.send(f"Не смогла отправить дайджест: {error}", ephemeral=True)
            return
        except Exception as error:
            await interaction.followup.send(f"Не смогла собрать Steam-дайджест: {error}", ephemeral=True)
            return

        await interaction.followup.send("Тестовый Steam-дайджест отправлен в этот канал.", ephemeral=True)

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
            if (
                self.config.protected_bans_enabled
                and self.config.protected_bans_auto_capture
                and isinstance(target, (discord.User, discord.Member))
            ):
                self.upsert_protected_ban(
                    guild,
                    target,
                    actor=entry.user,
                    reason=entry.reason,
                    source="audit_ban",
                )
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
            if self.config.protected_bans_enabled and target_id and self.is_protected_ban(guild.id, target_id):
                if entry.user is not None and entry.user.id == guild.owner_id:
                    self.remove_protected_ban(guild.id, target_id)
                    fields = [("Статус защиты", "Снята владельцем сервера", False)]
                    await self.audit.send_event(
                        guild,
                        "member_unbanned",
                        f"{_display_name(entry.user, 'Владелец сервера')} лично вытащил **{_display_name(target)}** из owner-only бан-листа.",
                        actor=entry.user,
                        target=target,
                        reason=entry.reason,
                        fields=fields,
                        related_users=[entry.user, target],
                    )
                    return

                try:
                    await guild.ban(
                        target,
                        reason=(
                            "EVA protected perma-ban: "
                            f"неавторизованный разбан пользователем {_display_name(entry.user, 'Неизвестно')}"
                        ),
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

                fields = [
                    ("Кто может разбанить", "Только владелец сервера", False),
                ]
                protected_entry = self.protected_ban_entry(guild.id, target_id)
                protected_reason = None if protected_entry is None else protected_entry.get("reason")
                if protected_reason:
                    fields.append(("Изначальная причина бана", str(protected_reason), False))
                await self.audit.send_event(
                    guild,
                    "protected_ban_restored",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} попытался разбанить **{_display_name(target)}**, но Ева вернула бан обратно.",
                    actor=entry.user,
                    target=target,
                    reason=entry.reason,
                    fields=fields,
                    related_users=[entry.user, target],
                    show_actor_field=True,
                    show_target_field=True,
                )
                return
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
                    self.queue_member_nickname_sync(target_member)

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
                    self.queue_member_nickname_sync(target_member)
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
        self.queue_member_nickname_sync(member)
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
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        if not self.config.protected_bans_enabled or not self.config.protected_bans_auto_capture:
            return
        self.upsert_protected_ban(
            guild,
            user,
            source="member_ban_event",
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
            self.queue_member_nickname_sync(after)

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
