"""Configurable message quarantine for EVA Assistant.

Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta
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
logger = logging.getLogger(__name__)


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

    logger.info(
        "Message quarantine matched user=%s message=%s channel=%s",
        message.author.id,
        message.id,
        message.channel.id,
    )
    assert message.guild is not None
    key = (message.guild.id, message.author.id)
    lock = cog._message_quarantine_locks.setdefault(key, asyncio.Lock())

    # Mark before the REST call: Discord can dispatch the delete event immediately.
    cog._quarantined_message_ids.add(message.id)
    async with lock:
        deleted = False
        for attempt in range(4):
            try:
                await message.delete()
                deleted = True
                break
            except discord.Forbidden as error:
                logger.warning("Message quarantine has no delete permission for message=%s: %s", message.id, error)
                break
            except discord.HTTPException as error:
                if error.status != 429 or attempt == 3:
                    logger.warning("Message quarantine could not delete message=%s: %s", message.id, error)
                    break
                retry_after = max(1.0, float(getattr(error, "retry_after", 1.0)))
                await asyncio.sleep(retry_after)

        if not deleted:
            cog._quarantined_message_ids.discard(message.id)
            return True

        logger.info("Message quarantine deleted message=%s", message.id)
        now = discord.utils.utcnow()
        last_warning = cog._message_quarantine_last_warning.get(key)
        should_warn = last_warning is None or now - last_warning >= timedelta(
            seconds=cog.config.message_quarantine.warning_cooldown_seconds,
        )
        if should_warn and isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            try:
                warning = await message.channel.send(
                    random.choice(_WARNINGS).format(member=message.author.mention),
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
                cog._message_quarantine_last_warning[key] = now
                seconds = cog.config.message_quarantine.warning_delete_seconds
                if seconds:
                    await warning.delete(delay=seconds)
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Discord dispatches cached and raw delete events separately. Keep the marker briefly
        # so neither event produces an audit entry for a deliberate quarantine deletion.
        asyncio.create_task(_release_quarantine_marker(cog, message.id))
        await asyncio.sleep(cog.config.message_quarantine.delete_interval_seconds)
    return True


async def _release_quarantine_marker(cog: AuditCog, message_id: int) -> None:
    await asyncio.sleep(60)
    cog._quarantined_message_ids.discard(message_id)
