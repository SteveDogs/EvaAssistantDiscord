"""
EVA Assistant audit models.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import discord


EmbedField = tuple[str, str, bool]


@dataclass(frozen=True, slots=True)
class AuditEventPayload:
    guild: discord.Guild
    event_key: str
    description: str
    actor: discord.abc.User | None = None
    target: Any | None = None
    reason: str | None = None
    fields: Sequence[EmbedField] = field(default_factory=tuple)
    show_actor_field: bool = False
    show_target_field: bool = True
    actor_label: str = "Исполнитель"
    target_label: str | None = None
    thumbnail_target: Any | None = None
    related_channels: Sequence[discord.abc.GuildChannel | discord.Thread | None] = field(default_factory=tuple)
    related_channel_ids: Sequence[int | None] = field(default_factory=tuple)
    related_users: Sequence[discord.Member | discord.User | None] = field(default_factory=tuple)
    related_roles: Sequence[discord.Role | None] = field(default_factory=tuple)
    include_case_id: bool | None = None
    flavor_text: str | None = None
