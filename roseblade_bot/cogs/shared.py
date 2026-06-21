"""
EVA Assistant shared cog state and base classes.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from roseblade_bot.audit_logger import AuditLogger
from roseblade_bot.config import BotConfig
from roseblade_bot.music import MusicService
from roseblade_bot.pubg_lookup import PubgLookupService
from roseblade_bot.server_banner import ServerBannerService
from roseblade_bot.steam_digest import SteamDigestService
from roseblade_bot.storage import JsonStateStore


@dataclass(slots=True)
class EvaSharedState:
    bot: commands.Bot
    config: BotConfig
    store: JsonStateStore
    pubg_lookup: PubgLookupService
    steam_digest: SteamDigestService
    server_banner: ServerBannerService
    music: MusicService
    audit: AuditLogger
    _bootstrapped_guild_ids: set[int] = field(default_factory=set)
    _voice_sessions: dict[tuple[int, int], datetime] = field(default_factory=dict)
    _stream_sessions: dict[tuple[int, int], datetime] = field(default_factory=dict)
    _camera_sessions: dict[tuple[int, int], datetime] = field(default_factory=dict)
    _managed_nickname_updates: dict[tuple[int, int], datetime] = field(default_factory=dict)
    _nickname_sync_queue: deque[tuple[int, int]] = field(default_factory=deque)
    _nickname_sync_pending: set[tuple[int, int]] = field(default_factory=set)
    _chat_banter_last_channel_reply: dict[tuple[int, int], datetime] = field(default_factory=dict)
    _chat_banter_last_user_reply: dict[tuple[int, int], datetime] = field(default_factory=dict)
    _chat_banter_last_channel_text: dict[tuple[int, int], str] = field(default_factory=dict)
    _special_dm_last_sent_at: dict[tuple[int, str], datetime] = field(default_factory=dict)
    _protected_voice_guard_recent: dict[tuple[int, int, int, int | None], datetime] = field(default_factory=dict)
    _protected_ban_startup_check_done: bool = False
    _server_banner_startup_refresh_done: bool = False


_SHARED_ATTR_NAMES = frozenset(EvaSharedState.__dataclass_fields__.keys())


class EvaSharedCog(commands.Cog):
    def __init__(self, shared: EvaSharedState) -> None:
        super().__setattr__("shared", shared)

    def __getattr__(self, name: str) -> Any:
        if name in _SHARED_ATTR_NAMES:
            return getattr(self.shared, name)
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "shared":
            super().__setattr__(name, value)
            return
        if name in _SHARED_ATTR_NAMES:
            setattr(self.shared, name, value)
            return
        super().__setattr__(name, value)


class EvaPassiveSharedCog(EvaSharedCog):
    async def cog_load(self) -> None:
        return None

    def cog_unload(self) -> None:
        return None

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        return None

    async def on_ready(self) -> None:
        return None

    async def on_guild_join(self, guild: discord.Guild) -> None:
        return None
