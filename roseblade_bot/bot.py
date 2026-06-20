"""
EVA Assistant core bot logic and Discord event handlers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

import discord
from discord.ext import commands

from roseblade_bot.audit_logger import AuditLogger
from roseblade_bot.audit_cog_commands import AuditCogCommandsMixin
from roseblade_bot.audit_cog_events import AuditCogEventsMixin
from roseblade_bot.audit_cog_runtime import AuditCogRuntimeMixin
from roseblade_bot.config import BotConfig, load_config
from roseblade_bot.pubg_lookup import PubgLookupService
from roseblade_bot.server_banner import ServerBannerService
from roseblade_bot.steam_digest import SteamDigestService
from roseblade_bot.storage import JsonStateStore


class AuditCog(AuditCogCommandsMixin, AuditCogEventsMixin, AuditCogRuntimeMixin, commands.Cog):
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
        self._server_banner_startup_refresh_done = False
        self.pubg_lookup = PubgLookupService(config)
        self.steam_digest = SteamDigestService(config)
        self.server_banner = ServerBannerService(config)
        self.audit = AuditLogger(
            store=store,
            default_category_name=config.audit_category_name,
            default_category_id=config.audit_category_id,
            static_ignored_channel_ids=config.ignored_channel_ids,
        )


def build_bot(config: BotConfig) -> commands.Bot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = config.enable_members_intent
    intents.presences = config.enable_presences_intent
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
