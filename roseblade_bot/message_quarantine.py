"""Configurable message quarantine for EVA Assistant.

Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from roseblade_bot.bot import AuditCog


_WARNINGS = (
    "🌷 {member}, я пока тихонько убираю твои новые сообщения, чтобы чат не разгонялся. "
    "Когда тебя снимут с тихого режима, сможешь писать снова.",
    "🫶 {member}, это не наказание, а маленькая пауза для чата. Новое сообщение я спрятала, не обижайся.",
    "🌸 {member}, я поймала это сообщение и убрала в карман. Тихий режим пока включён, зато старые сообщения не трогаю.",
    "🐾 {member}, Ева сегодня бережёт чат от разгона. Новое сообщение спрятано, а доступ вернётся после снятия тихого режима.",
)


def is_quarantined_message(cog: AuditCog, message: discord.Message) -> bool:
    return (
        message.guild is not None
        and not message.author.bot
        and cog.config.message_quarantine.enabled
        and message.author.id in cog.config.message_quarantine.user_ids
    )


async def maybe_quarantine_message(cog: AuditCog, message: discord.Message) -> bool:
    """Delete a new configured member message and leave a short, kind notice."""
    if not is_quarantined_message(cog, message):
        return False

    # Mark before the REST call: Discord can dispatch the delete event immediately.
    cog._quarantined_message_ids.add(message.id)
    try:
        await message.delete(reason="EVA message quarantine")
    except (discord.Forbidden, discord.HTTPException):
        cog._quarantined_message_ids.discard(message.id)
        return True

    if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        return True

    try:
        warning = await message.channel.send(
            random.choice(_WARNINGS).format(member=message.author.mention),
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )
        seconds = cog.config.message_quarantine.warning_delete_seconds
        if seconds:
            await warning.delete(delay=seconds)
    except (discord.Forbidden, discord.HTTPException):
        pass
    return True
