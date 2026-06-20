"""
EVA Assistant AuditCog runtime mixin.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import random
from typing import Any
import unicodedata

import discord
from discord import app_commands
from discord.ext import commands, tasks

from roseblade_bot import APP_NAME, APP_CODENAME
from roseblade_bot.chat_banter import CHAT_BANTER
from roseblade_bot.formatters import _display_name, _format_duration
from roseblade_bot.server_banner import ServerBannerRenderResult
from roseblade_bot.voice_guard import VOICE_GUARD


class AuditCogRuntimeMixin:
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
        if self.server_banner.is_enabled and not self.server_banner_scheduler.is_running():
            self.server_banner_scheduler.start()
        if self.config.enable_members_intent and self.config.nickname_prefix_rules and not self.nickname_sync_worker.is_running():
            self.nickname_sync_worker.start()
        if self.config.enable_members_intent and self.config.nickname_prefix_rules and not self.nickname_resync_scheduler.is_running():
            self.nickname_resync_scheduler.start()
        if self.config.protected_bans_enabled and not self.protected_ban_enforcer.is_running():
            self.protected_ban_enforcer.start()

    def cog_unload(self) -> None:
        if self.steam_digest_scheduler.is_running():
            self.steam_digest_scheduler.cancel()
        if self.server_banner_scheduler.is_running():
            self.server_banner_scheduler.cancel()
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
            await self.run_startup_server_banner_refresh()
            return

        for guild in self.bot.guilds:
            await self.bootstrap_guild(guild)
        await self.run_startup_protected_ban_check()
        await self.run_startup_server_banner_refresh()

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

    def _server_banner_state(self, guild_id: int) -> dict[str, Any]:
        return self.store.get_service_state(guild_id, "server_banner")

    async def refresh_guild_server_banner(
        self,
        guild: discord.Guild,
        *,
        force: bool,
        source: str,
        prepared: ServerBannerRenderResult | None = None,
    ) -> tuple[str, ServerBannerRenderResult | None]:
        state = self._server_banner_state(guild.id)
        now = discord.utils.utcnow()

        if not self.server_banner.is_enabled:
            state["last_status"] = "disabled"
            state["last_source"] = source
            self.store.set_service_state(guild.id, "server_banner", state)
            return ("disabled", None)

        if not force:
            last_run_raw = state.get("last_run_at")
            last_run: datetime | None = None
            if isinstance(last_run_raw, str):
                try:
                    last_run = datetime.fromisoformat(last_run_raw)
                except ValueError:
                    last_run = None
            if last_run is not None and now - last_run < timedelta(minutes=self.config.server_banner_update_minutes):
                return ("interval", None)

        if not any(feature in guild.features for feature in ("BANNER", "ANIMATED_BANNER")):
            state["last_run_at"] = now.isoformat()
            state["last_status"] = "unsupported"
            state["last_source"] = source
            state["last_error"] = "Серверу недоступен кастомный баннер."
            self.store.set_service_state(guild.id, "server_banner", state)
            return ("unsupported", None)

        try:
            prepared = prepared or await self.server_banner.render_banner(guild)
        except Exception as error:
            state["last_run_at"] = now.isoformat()
            state["last_status"] = "render_error"
            state["last_source"] = source
            state["last_error"] = str(error)
            self.store.set_service_state(guild.id, "server_banner", state)
            return ("render_error", None)

        if not force and state.get("last_signature") == prepared.signature:
            state["last_run_at"] = now.isoformat()
            state["last_status"] = "skipped_same_stats"
            state["last_source"] = source
            state["last_error"] = None
            self.store.set_service_state(guild.id, "server_banner", state)
            return ("skipped_same_stats", prepared)

        try:
            await guild.edit(
                banner=prepared.image_bytes,
                reason=f"EVA live banner refresh ({source})",
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            state["last_run_at"] = now.isoformat()
            state["last_status"] = "upload_error"
            state["last_source"] = source
            state["last_error"] = str(error)
            self.store.set_service_state(guild.id, "server_banner", state)
            return ("upload_error", prepared)

        state["last_run_at"] = now.isoformat()
        state["last_banner_at"] = now.isoformat()
        state["last_status"] = "updated"
        state["last_source"] = source
        state["last_signature"] = prepared.signature
        state["last_error"] = None
        state["last_online_count"] = prepared.stats.online_count
        self.store.set_service_state(guild.id, "server_banner", state)
        return ("updated", prepared)

    async def run_startup_server_banner_refresh(self) -> None:
        if not self.server_banner.is_enabled or self._server_banner_startup_refresh_done:
            return
        for guild in self.bot.guilds:
            await self.refresh_guild_server_banner(guild, force=True, source="startup")
        self._server_banner_startup_refresh_done = True

    @tasks.loop(minutes=1)
    async def server_banner_scheduler(self) -> None:
        if not self.server_banner.is_enabled:
            return
        for guild in self.bot.guilds:
            await self.refresh_guild_server_banner(guild, force=False, source="scheduler")

    @server_banner_scheduler.before_loop
    async def before_server_banner_scheduler(self) -> None:
        await self.bot.wait_until_ready()

    @server_banner_scheduler.error
    async def server_banner_scheduler_error(self, error: Exception) -> None:
        print(f"Server banner scheduler crashed: {error}")

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
