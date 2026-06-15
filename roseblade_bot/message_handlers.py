"""
EVA Assistant message event handlers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import discord

from roseblade_bot.chat_banter import CHAT_BANTER
from roseblade_bot.formatters import (
    _display_name,
    _format_attachments,
    _format_deleted_message_body,
    _format_message_content,
    _format_reference,
)

if TYPE_CHECKING:
    from roseblade_bot.bot import AuditCog


def _channel_value(channel: object, fallback_id: int) -> str:
    if isinstance(channel, (discord.TextChannel, discord.Thread)):
        return channel.mention
    return f"`{fallback_id}`"


def _related_channels(
    channel: object,
) -> list[discord.abc.GuildChannel | discord.Thread] | None:
    if isinstance(channel, (discord.abc.GuildChannel, discord.Thread)):
        return [channel]
    return None


async def handle_on_message(cog: AuditCog, message: discord.Message) -> None:
    if await cog.pubg_lookup.maybe_handle_message(cog, message):
        return

    if not cog.should_reply_with_banter(message):
        return

    guild = message.guild
    if guild is None:
        return

    previous_reply = cog._chat_banter_last_channel_text.get((guild.id, message.channel.id))
    reply_text = CHAT_BANTER.render_reply(
        _display_name(message.author),
        message.content,
        previous_reply=previous_reply,
    )
    try:
        await message.reply(
            reply_text,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException):
        cog.log_banter_decision(message, decision="fail", reason="reply_send_error")
        return
    cog.remember_banter_reply(message, reply_text)
    cog.log_banter_decision(message, decision="sent", reason="reply_posted")


async def handle_on_message_delete(cog: AuditCog, message: discord.Message) -> None:
    if message.guild is None or message.author.bot:
        return
    if isinstance(message.channel, (discord.TextChannel, discord.Thread)) and cog.is_ignored_channel(
        message.guild,
        message.channel,
    ):
        return
    entry = await cog.find_message_delete_entry(message)
    fields = [
        ("Канал", message.channel.mention, False),
        ("Message ID", f"`{message.id}`", False),
        (
            "Сообщение",
            _format_deleted_message_body(
                message,
                message_content_intent_enabled=cog.config.enable_message_content_intent,
            ),
            False,
        ),
        ("Отправлено", discord.utils.format_dt(message.created_at, style="F"), False),
    ]
    attachments = _format_attachments(message)
    if attachments:
        fields.append(("Вложения", attachments, False))
    reference = _format_reference(message)
    if reference:
        fields.append(("Ответ на", reference, False))
    if entry is None:
        fields.append(
            (
                "Кто удалил",
                "Audit Log не дал точного исполнителя. Обычно это значит, что сообщение удалил сам автор или запись ещё не успела появиться у Discord.",
                False,
            )
        )
    await cog.audit.send_event(
        message.guild,
        "message_deleted",
        (
            f"{_display_name(entry.user, 'Кто-то из стаффа')} подчистил сообщение "
            f"**{_display_name(message.author)}** в {message.channel.mention}."
            if entry is not None
            else f"Сообщение **{_display_name(message.author)}** исчезло из {message.channel.mention}."
        ),
        actor=entry.user if entry else None,
        target=message.author,
        reason=entry.reason if entry else None,
        fields=fields,
        show_actor_field=entry is not None,
        show_target_field=True,
        actor_label="Кто подчистил",
        target_label="Автор сообщения",
        thumbnail_target=message.author,
        related_channels=[message.channel],
        related_users=[message.author, entry.user if entry else None],
    )


async def handle_on_raw_message_delete(cog: AuditCog, payload: discord.RawMessageDeleteEvent) -> None:
    if payload.cached_message is not None or payload.guild_id is None:
        return
    guild = cog.bot.get_guild(payload.guild_id)
    if guild is None:
        return
    channel = guild.get_channel(payload.channel_id) or guild.get_thread(payload.channel_id)
    if isinstance(channel, (discord.abc.GuildChannel, discord.Thread)):
        if cog.is_ignored_channel(guild, channel):
            return
    elif cog.is_ignored_channel_id(guild.id, payload.channel_id):
        return
    entry = await cog.find_raw_message_delete_entry(guild, payload.channel_id)
    fields: list[tuple[str, str, bool]] = [
        ("Канал", _channel_value(channel, payload.channel_id), False),
        ("Message ID", f"`{payload.message_id}`", False),
    ]
    if entry is not None and entry.target is not None:
        fields.append(("Автор сообщения", cog.audit.format_entity(entry.target), False))
    fields.append(
        (
            "Почему нет текста",
            "Сообщение не попало в кэш бота. Для показа удалённого текста бот должен заранее видеть сообщение и хранить его в памяти.",
            False,
        )
    )
    await cog.audit.send_event(
        guild,
        "message_deleted",
        (
            f"{_display_name(entry.user, 'Кто-то из стаффа')} снёс сообщение, но текст ускользнул из кэша."
            if entry is not None
            else "Сообщение удалили, но его текст не успел осесть в памяти бота."
        ),
        actor=entry.user if entry else None,
        target=entry.target if entry and entry.target is not None else None,
        reason=entry.reason if entry else None,
        fields=fields,
        show_actor_field=entry is not None,
        show_target_field=entry is not None and entry.target is not None,
        actor_label="Кто подчистил",
        target_label="Автор сообщения",
        thumbnail_target=entry.target if entry and entry.target is not None else None,
        related_channels=_related_channels(channel),
        related_users=[entry.user if entry else None, entry.target if entry else None],
    )


async def handle_on_raw_bulk_message_delete(
    cog: AuditCog,
    payload: discord.RawBulkMessageDeleteEvent,
) -> None:
    if payload.guild_id is None:
        return
    guild = cog.bot.get_guild(payload.guild_id)
    if guild is None:
        return
    channel = guild.get_channel(payload.channel_id) or guild.get_thread(payload.channel_id)
    if isinstance(channel, (discord.abc.GuildChannel, discord.Thread)):
        if cog.is_ignored_channel(guild, channel):
            return
    elif cog.is_ignored_channel_id(guild.id, payload.channel_id):
        return
    cached_messages = [message for message in payload.cached_messages if not message.author.bot]
    fields: list[tuple[str, str, bool]] = [
        ("Канал", _channel_value(channel, payload.channel_id), False),
        ("Количество", str(len(payload.message_ids)), True),
        ("Из кэша", str(len(cached_messages)), True),
    ]
    await cog.audit.send_event(
        guild,
        "message_deleted",
        "В канале устроили массовую зачистку сообщений.",
        fields=fields,
        related_channels=_related_channels(channel),
        include_case_id=False,
    )

    if cached_messages:
        transcript_lines = []
        for message in cached_messages[:50]:
            transcript_lines.append(
                f"[{message.created_at.isoformat()}] {message.author} ({message.author.id}): {message.content}"
            )
        transcript = io.BytesIO("\n".join(transcript_lines).encode("utf-8"))
        transcript.seek(0)
        log_channel = await cog.audit.get_channel_for_event(guild, "message_deleted")
        if log_channel is not None:
            await log_channel.send(
                content="Транскрипт удалённых сообщений:",
                file=discord.File(transcript, filename=f"bulk-delete-{payload.channel_id}.txt"),
            )


async def handle_on_message_edit(
    cog: AuditCog,
    before: discord.Message,
    after: discord.Message,
) -> None:
    if before.guild is None or before.author.bot:
        return
    if isinstance(before.channel, (discord.TextChannel, discord.Thread)) and cog.is_ignored_channel(
        before.guild,
        before.channel,
    ):
        return
    if before.content == after.content and before.attachments == after.attachments:
        return
    fields = [
        ("Автор", cog.audit.format_entity(before.author), False),
        ("Канал", before.channel.mention, False),
        ("До", _format_message_content(before.content), False),
        ("После", _format_message_content(after.content), False),
        ("Ссылка", after.jump_url, False),
    ]
    before_attachments = _format_attachments(before)
    after_attachments = _format_attachments(after)
    if before_attachments or after_attachments:
        fields.append(("Вложения до", before_attachments or "Нет", False))
        fields.append(("Вложения после", after_attachments or "Нет", False))
    reference = _format_reference(after)
    if reference:
        fields.append(("Ответ на", reference, False))
    await cog.audit.send_event(
        before.guild,
        "message_edited",
        f"**{_display_name(before.author)}** переписал сообщение в {before.channel.mention}. Версия 2.0 готова.",
        target=before.author,
        fields=fields,
        show_target_field=False,
        thumbnail_target=before.author,
        related_channels=[before.channel],
        related_users=[before.author],
    )


async def handle_on_raw_message_edit(cog: AuditCog, payload: discord.RawMessageUpdateEvent) -> None:
    if payload.cached_message is not None or payload.guild_id is None:
        return
    if "content" not in payload.data:
        return
    guild = cog.bot.get_guild(payload.guild_id)
    if guild is None:
        return
    channel = guild.get_channel(payload.channel_id) or guild.get_thread(payload.channel_id)
    if isinstance(channel, (discord.abc.GuildChannel, discord.Thread)):
        if cog.is_ignored_channel(guild, channel):
            return
    elif cog.is_ignored_channel_id(guild.id, payload.channel_id):
        return
    await cog.audit.send_event(
        guild,
        "message_edited",
        "Сообщение переписали, но старая версия успела улизнуть из кэша.",
        fields=[
            ("Канал", _channel_value(channel, payload.channel_id), False),
            ("Message ID", f"`{payload.message_id}`", False),
            ("После", _format_message_content(payload.data.get("content")), False),
            (
                "Почему нет старого текста",
                "Бот не сохранил старую версию в кэше. Для лучшего покрытия держим увеличенный кэш, но старые сообщения и рестарты всё равно могут выпадать.",
                False,
            ),
        ],
        related_channels=_related_channels(channel),
    )
