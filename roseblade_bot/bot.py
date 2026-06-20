"""
EVA Assistant core bot logic and Discord event handlers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from roseblade_bot.audit_logger import AuditLogger
from roseblade_bot.config import BotConfig, load_config
from roseblade_bot.cogs import EvaCommandsCog, EvaCoreCog, EvaEventsCog, EvaSharedState
from roseblade_bot.pubg_lookup import PubgLookupService
from roseblade_bot.server_banner import ServerBannerService
from roseblade_bot.steam_digest import SteamDigestService
from roseblade_bot.storage import JsonStateStore

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
    shared = EvaSharedState(
        bot=bot,
        config=config,
        store=store,
        pubg_lookup=PubgLookupService(config),
        steam_digest=SteamDigestService(config),
        server_banner=ServerBannerService(config),
        audit=AuditLogger(
            store=store,
            default_category_name=config.audit_category_name,
            default_category_id=config.audit_category_id,
            static_ignored_channel_ids=config.ignored_channel_ids,
        ),
    )

    async def setup() -> None:
        await bot.add_cog(EvaCoreCog(shared))
        await bot.add_cog(EvaCommandsCog(shared))
        await bot.add_cog(EvaEventsCog(shared))
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
