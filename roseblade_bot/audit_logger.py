"""
EVA Assistant audit facade.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import discord

from roseblade_bot.audit.dispatcher import AuditDispatcher
from roseblade_bot.audit.history import AuditHistoryService
from roseblade_bot.audit.models import AuditEventPayload, EmbedField
from roseblade_bot.audit.renderer import AuditRenderer
from roseblade_bot.storage import JsonStateStore


class AuditLogger:
    display_name = staticmethod(AuditRenderer.display_name)
    describe_changes = staticmethod(AuditRenderer.describe_changes)
    entity_image_url = staticmethod(AuditRenderer.entity_image_url)
    format_automod_action = staticmethod(AuditRenderer.format_automod_action)
    format_change_value = staticmethod(AuditRenderer.format_change_value)
    format_channel = staticmethod(AuditRenderer.format_channel)
    format_channel_type = staticmethod(AuditRenderer.format_channel_type)
    format_entity = staticmethod(AuditRenderer.format_entity)
    format_enum = staticmethod(AuditRenderer.format_enum)
    label_for_entity = staticmethod(AuditRenderer.label_for_entity)
    pick_flavor = staticmethod(AuditRenderer.pick_flavor)
    pick_missing_reason_line = staticmethod(AuditRenderer.pick_missing_reason_line)
    shorten = staticmethod(AuditRenderer.shorten)

    def __init__(
        self,
        *,
        store: JsonStateStore,
        default_category_name: str,
        default_category_id: int | None = None,
        static_ignored_channel_ids: Iterable[int] = (),
    ) -> None:
        self.store = store
        self.default_category_name = default_category_name
        self.default_category_id = default_category_id
        self.static_ignored_channel_ids = {int(value) for value in static_ignored_channel_ids}
        self.renderer = AuditRenderer()
        self.history = AuditHistoryService(store, display_name=self.display_name)
        self.dispatcher = AuditDispatcher(
            store=store,
            renderer=self.renderer,
            history=self.history,
            default_category_name=default_category_name,
            default_category_id=default_category_id,
            static_ignored_channel_ids=static_ignored_channel_ids,
        )
        self.history_path = self.history.history_path

    def remember_recent(self, guild_id: int, event_key: str, target_id: int) -> None:
        self.history.remember_recent(guild_id, event_key, target_id)

    def was_recent(self, guild_id: int, event_key: str, target_id: int, *, seconds: int = 10) -> bool:
        return self.history.was_recent(guild_id, event_key, target_id, seconds=seconds)

    async def ensure_guild_setup(
        self,
        guild: discord.Guild,
        *,
        category_name: str | None = None,
        category_id: int | None = None,
    ) -> tuple[discord.CategoryChannel, dict[str, discord.TextChannel]]:
        return await self.dispatcher.ensure_guild_setup(
            guild,
            category_name=category_name,
            category_id=category_id,
        )

    async def get_channel_for_event(
        self,
        guild: discord.Guild,
        event_key: str,
    ) -> discord.TextChannel | None:
        return await self.dispatcher.get_channel_for_event(guild, event_key)

    def color_for_event(self, guild_id: int, event_key: str) -> discord.Colour:
        return self.dispatcher.color_for_event(guild_id, event_key)

    def should_log_event(
        self,
        guild: discord.Guild,
        event_key: str,
        *,
        related_channels: Sequence[discord.abc.GuildChannel | discord.Thread | None] | None = None,
        related_channel_ids: Sequence[int | None] | None = None,
        related_users: Sequence[discord.Member | discord.User | None] | None = None,
        related_roles: Sequence[discord.Role | None] | None = None,
    ) -> bool:
        return self.dispatcher.should_log_event(
            guild,
            event_key,
            related_channels=related_channels or (),
            related_channel_ids=related_channel_ids or (),
            related_users=related_users or (),
            related_roles=related_roles or (),
        )

    async def send_event(
        self,
        guild: discord.Guild,
        event_key: str,
        description: str,
        *,
        actor: discord.abc.User | None = None,
        target: Any | None = None,
        reason: str | None = None,
        fields: Sequence[EmbedField] | None = None,
        show_actor_field: bool = False,
        show_target_field: bool = True,
        actor_label: str = "Исполнитель",
        target_label: str | None = None,
        thumbnail_target: Any | None = None,
        related_channels: Sequence[discord.abc.GuildChannel | discord.Thread | None] | None = None,
        related_channel_ids: Sequence[int | None] | None = None,
        related_users: Sequence[discord.Member | discord.User | None] | None = None,
        related_roles: Sequence[discord.Role | None] | None = None,
        include_case_id: bool | None = None,
        flavor_text: str | None = None,
    ) -> None:
        payload = AuditEventPayload(
            guild=guild,
            event_key=event_key,
            description=description,
            actor=actor,
            target=target,
            reason=reason,
            fields=fields or (),
            show_actor_field=show_actor_field,
            show_target_field=show_target_field,
            actor_label=actor_label,
            target_label=target_label,
            thumbnail_target=thumbnail_target,
            related_channels=related_channels or (),
            related_channel_ids=related_channel_ids or (),
            related_users=related_users or (),
            related_roles=related_roles or (),
            include_case_id=include_case_id,
            flavor_text=flavor_text,
        )
        await self.dispatcher.send_event(payload)

    async def fetch_recent_audit_entry(
        self,
        guild: discord.Guild,
        *,
        actions: Iterable[discord.AuditLogAction],
        target_id: int | None = None,
        max_age_seconds: int = 15,
    ) -> discord.AuditLogEntry | None:
        return await self.dispatcher.fetch_recent_audit_entry(
            guild,
            actions=actions,
            target_id=target_id,
            max_age_seconds=max_age_seconds,
        )

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
        self.history.append_history(
            guild=guild,
            event_key=event_key,
            description=description,
            actor=actor,
            target=target,
            channel=channel,
        )

    def export_history(self, guild_id: int, *, limit: int = 100) -> discord.File:
        return self.history.export_history(guild_id, limit=limit)
