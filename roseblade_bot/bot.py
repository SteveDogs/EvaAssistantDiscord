"""
EVA Assistant core bot logic and Discord event handlers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from roseblade_bot.air_alerts import AirAlertService
from roseblade_bot.audit_logger import AuditLogger
from roseblade_bot.config import BotConfig, load_config
from roseblade_bot.cogs import EvaCommandsCog, EvaCoreCog, EvaEventsCog, EvaMusicCog, EvaSharedState
from roseblade_bot.music import MusicService
from roseblade_bot.pubg_lookup import PubgLookupService
from roseblade_bot.server_banner import ServerBannerService
from roseblade_bot.steam_digest import SteamDigestService
from roseblade_bot.storage import JsonStateStore
from roseblade_bot.war_monitor import WarMonitorService

def build_bot(config: BotConfig) -> commands.Bot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = config.discord.intents.members
    intents.presences = config.discord.intents.presences
    intents.guild_messages = True
    intents.message_content = config.discord.intents.message_content
    intents.voice_states = True

    bot = commands.Bot(command_prefix="!", intents=intents, max_messages=10000)
    store = JsonStateStore(config.discord.state_file)
    shared = EvaSharedState(
        bot=bot,
        config=config,
        store=store,
        pubg_lookup=PubgLookupService(config),
        steam_digest=SteamDigestService(config),
        server_banner=ServerBannerService(config),
        air_alert=AirAlertService(config),
        war_monitor=WarMonitorService(config),
        music=MusicService(config.music),
        audit=AuditLogger(
            store=store,
            default_category_name=config.audit.category_name,
            default_category_id=config.audit.category_id,
            static_ignored_channel_ids=config.audit.ignored_channel_ids,
        ),
    )

    async def setup() -> None:
        await bot.add_cog(EvaCoreCog(shared))
        await bot.add_cog(EvaCommandsCog(shared))
        await bot.add_cog(EvaEventsCog(shared))
        await bot.add_cog(EvaMusicCog(shared))
        if config.discord.guild_id:
            guild = discord.Object(id=config.discord.guild_id)
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        else:
            await bot.tree.sync()

    bot.setup_hook = setup
    return bot


def main() -> None:
    config = load_config()
    bot = build_bot(config)
    bot.run(config.discord.token)
