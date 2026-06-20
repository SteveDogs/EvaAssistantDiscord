"""
EVA Assistant audit dispatcher.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import timedelta

import discord

from roseblade_bot.audit.constants import CASE_EVENT_KEYS
from roseblade_bot.audit.history import AuditHistoryService
from roseblade_bot.audit.models import AuditEventPayload
from roseblade_bot.audit.renderer import AuditRenderer
from roseblade_bot.audit_definitions import CHANNEL_DEFINITIONS, EVENT_DEFINITIONS
from roseblade_bot.storage import JsonStateStore


class AuditDispatcher:
    def __init__(
        self,
        *,
        store: JsonStateStore,
        renderer: AuditRenderer,
        history: AuditHistoryService,
        default_category_name: str,
        default_category_id: int | None = None,
        static_ignored_channel_ids: Iterable[int] = (),
    ) -> None:
        self.store = store
        self.renderer = renderer
        self.history = history
        self.default_category_name = default_category_name
        self.default_category_id = default_category_id
        self.static_ignored_channel_ids = {int(value) for value in static_ignored_channel_ids}

    async def ensure_guild_setup(
        self,
        guild: discord.Guild,
        *,
        category_name: str | None = None,
        category_id: int | None = None,
    ) -> tuple[discord.CategoryChannel, dict[str, discord.TextChannel]]:
        saved = self.store.get_guild(guild.id)
        wanted_category_name = category_name or self.default_category_name
        wanted_category_id = category_id or self.default_category_id

        category = None
        if wanted_category_id:
            channel_by_id = guild.get_channel(wanted_category_id)
            if isinstance(channel_by_id, discord.CategoryChannel):
                category = channel_by_id

        if category is None:
            category = guild.get_channel(saved.get("category_id") or 0)
        if not isinstance(category, discord.CategoryChannel):
            category = discord.utils.get(guild.categories, name=wanted_category_name)

        if category is None:
            category = await guild.create_category(
                wanted_category_name,
                reason="Настройка аудит-логов RoseBladeBot",
            )

        created_channels: dict[str, discord.TextChannel] = {}
        persisted_channels: dict[str, int] = {}
        for key, definition in CHANNEL_DEFINITIONS.items():
            channel_id = saved["channels"].get(key)
            channel = guild.get_channel(channel_id or 0)
            if not isinstance(channel, discord.TextChannel):
                channel = discord.utils.get(category.text_channels, name=definition.name)
            if channel is None:
                channel = await guild.create_text_channel(
                    definition.name,
                    category=category,
                    topic=definition.description,
                    reason="Настройка аудит-логов RoseBladeBot",
                )
            elif channel.category_id != category.id:
                await channel.edit(
                    category=category,
                    reason="Синхронизация аудит-каналов RoseBladeBot",
                )
            created_channels[key] = channel
            persisted_channels[key] = channel.id

        self.store.update_guild(
            guild.id,
            category_id=category.id,
            channels=persisted_channels,
        )
        return category, created_channels

    async def get_channel_for_event(
        self,
        guild: discord.Guild,
        event_key: str,
    ) -> discord.TextChannel | None:
        event_definition = EVENT_DEFINITIONS[event_key]
        saved = self.store.get_guild(guild.id)
        channel_id = saved["channels"].get(event_definition.channel_key)
        channel = guild.get_channel(channel_id or 0)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    def color_for_event(self, guild_id: int, event_key: str) -> discord.Colour:
        saved = self.store.get_guild(guild_id)
        color_value = saved["colors"].get(event_key, EVENT_DEFINITIONS[event_key].default_color)
        return discord.Colour(color_value)

    def should_log_event(
        self,
        guild: discord.Guild,
        event_key: str,
        *,
        related_channels: Sequence[discord.abc.GuildChannel | discord.Thread | None] = (),
        related_channel_ids: Sequence[int | None] = (),
        related_users: Sequence[discord.Member | discord.User | None] = (),
        related_roles: Sequence[discord.Role | None] = (),
    ) -> bool:
        if not self.store.is_event_enabled(guild.id, event_key):
            return False

        ignored_channel_ids = self.store.get_ignored_ids(guild.id, "channel_ids") | self.static_ignored_channel_ids
        ignored_category_ids = self.store.get_ignored_ids(guild.id, "category_ids")
        ignored_user_ids = self.store.get_ignored_ids(guild.id, "user_ids")
        ignored_role_ids = self.store.get_ignored_ids(guild.id, "role_ids")

        for channel_id in related_channel_ids:
            if channel_id is not None and int(channel_id) in ignored_channel_ids:
                return False

        for channel in related_channels:
            if channel is None:
                continue
            if int(channel.id) in ignored_channel_ids:
                return False
            parent_id = getattr(channel, "parent_id", None)
            if parent_id is not None and int(parent_id) in ignored_channel_ids:
                return False
            category_id = getattr(channel, "category_id", None)
            if category_id is not None and int(category_id) in ignored_category_ids:
                return False

        for user in related_users:
            if user is not None and int(user.id) in ignored_user_ids:
                return False

        for role in related_roles:
            if role is not None and int(role.id) in ignored_role_ids:
                return False

        return True

    async def send_event(self, payload: AuditEventPayload) -> None:
        if not self.should_log_event(
            payload.guild,
            payload.event_key,
            related_channels=payload.related_channels,
            related_channel_ids=payload.related_channel_ids,
            related_users=payload.related_users,
            related_roles=payload.related_roles,
        ):
            return

        channel = await self.get_channel_for_event(payload.guild, payload.event_key)
        if channel is None:
            return

        include_case_id = payload.include_case_id
        if include_case_id is None:
            include_case_id = payload.event_key in CASE_EVENT_KEYS
        case_id = self.store.next_case_id(payload.guild.id) if include_case_id else None
        embed = self.renderer.build_embed(
            payload,
            color=self.color_for_event(payload.guild.id, payload.event_key),
            case_id=case_id,
        )
        await channel.send(embed=embed)
        self.history.append_history(
            guild=payload.guild,
            event_key=payload.event_key,
            description=payload.description,
            actor=payload.actor,
            target=payload.target,
            channel=channel,
        )

    async def fetch_recent_audit_entry(
        self,
        guild: discord.Guild,
        *,
        actions: Iterable[discord.AuditLogAction],
        target_id: int | None = None,
        max_age_seconds: int = 15,
    ) -> discord.AuditLogEntry | None:
        deadline = discord.utils.utcnow() - timedelta(seconds=max_age_seconds)
        try:
            for action in actions:
                async for entry in guild.audit_logs(limit=6, action=action):
                    if entry.created_at < deadline:
                        break
                    candidate_target = getattr(entry.target, "id", None)
                    if target_id is not None and candidate_target != target_id:
                        continue
                    return entry
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None
