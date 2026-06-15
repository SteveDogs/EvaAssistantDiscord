"""
EVA Assistant voice event handlers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from roseblade_bot.formatters import (
    _display_name,
    _format_voice_flags,
    _format_voice_moderation_flags,
    _voice_moderation_summary,
    _voice_state_summary,
)

if TYPE_CHECKING:
    from roseblade_bot.bot import AuditCog


async def handle_on_voice_state_update(
    cog: AuditCog,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if member.bot:
        return

    guild = member.guild
    active_channel = after.channel or before.channel

    if after.channel is not None:
        cog._start_session(cog._voice_sessions, member)
    if after.channel is not None and after.self_stream:
        cog._start_session(cog._stream_sessions, member)
    if after.channel is not None and after.self_video:
        cog._start_session(cog._camera_sessions, member)

    moderation_changes = _format_voice_moderation_flags(before, after)
    if moderation_changes and active_channel is not None:
        entry = await cog.audit.fetch_recent_audit_entry(
            guild,
            actions=[discord.AuditLogAction.member_update],
            target_id=member.id,
            max_age_seconds=8,
        )
        await cog.audit.send_event(
            guild,
            "member_voice_moderation_changed",
            (
                f"{_display_name(entry.user, 'Кто-то из стаффа')} "
                f"{_voice_moderation_summary(moderation_changes)} участнику **{_display_name(member)}**."
            ),
            actor=entry.user if entry else None,
            target=member,
            reason=entry.reason if entry else None,
            fields=[
                ("Кто навёл движ", cog.audit.format_entity(entry.user) if entry else "Неизвестно", False),
                ("Участник", cog.audit.format_entity(member), False),
                ("Канал", cog.audit.format_channel(active_channel), False),
                ("Изменения", "\n".join(moderation_changes), False),
            ],
            show_target_field=False,
            thumbnail_target=member,
            related_channels=[active_channel],
            related_users=[member, entry.user if entry else None],
        )

    if before.self_stream != after.self_stream and active_channel is not None:
        if after.self_stream:
            cog._start_session(cog._stream_sessions, member)
            await cog.audit.send_event(
                guild,
                "member_stream_started",
                f"**{_display_name(member)}** запустил стрим в {active_channel.mention}.",
                target=member,
                fields=[("Канал", cog.audit.format_channel(active_channel), False)],
                thumbnail_target=member,
                related_channels=[active_channel],
                related_users=[member],
            )
        else:
            duration = cog._stop_session(cog._stream_sessions, member)
            fields = [("Канал", cog.audit.format_channel(active_channel), False)]
            if duration:
                fields.append(("Длительность", duration, True))
            await cog.audit.send_event(
                guild,
                "member_stream_stopped",
                f"**{_display_name(member)}** остановил стрим в {active_channel.mention}.",
                target=member,
                fields=fields,
                thumbnail_target=member,
                related_channels=[active_channel],
                related_users=[member],
            )

    if before.self_video != after.self_video and active_channel is not None:
        if after.self_video:
            cog._start_session(cog._camera_sessions, member)
            await cog.audit.send_event(
                guild,
                "member_camera_started",
                f"**{_display_name(member)}** включил камеру в {active_channel.mention}.",
                target=member,
                fields=[("Канал", cog.audit.format_channel(active_channel), False)],
                thumbnail_target=member,
                related_channels=[active_channel],
                related_users=[member],
            )
        else:
            duration = cog._stop_session(cog._camera_sessions, member)
            fields = [("Канал", cog.audit.format_channel(active_channel), False)]
            if duration:
                fields.append(("Длительность", duration, True))
            await cog.audit.send_event(
                guild,
                "member_camera_stopped",
                f"**{_display_name(member)}** выключил камеру в {active_channel.mention}.",
                target=member,
                fields=fields,
                thumbnail_target=member,
                related_channels=[active_channel],
                related_users=[member],
            )

    state_changes = _format_voice_flags(before, after)
    if state_changes and active_channel is not None:
        await cog.audit.send_event(
            guild,
            "member_voice_state_changed",
            f"**{_display_name(member)}** в войсе {_voice_state_summary(state_changes)}.",
            target=member,
            fields=[
                ("Канал", cog.audit.format_channel(active_channel), False),
                ("Изменения", "\n".join(state_changes), False),
            ],
            related_channels=[active_channel],
            related_users=[member],
        )

    if before.channel != after.channel:
        if before.channel is not None and after.channel is None:
            voice_duration = cog._stop_session(cog._voice_sessions, member)
            cog._stop_session(cog._stream_sessions, member)
            cog._stop_session(cog._camera_sessions, member)
            entry = await cog.find_member_disconnect_entry(member, max_age_seconds=10)
            if entry is not None and not cog.audit.was_recent(guild.id, "member_disconnected", member.id, seconds=8):
                cog.audit.remember_recent(guild.id, "member_disconnected", member.id)
                await cog._log_voice_session_finished(
                    member,
                    before.channel,
                    duration=voice_duration,
                    actor=entry.user,
                    reason=entry.reason,
                )
                fields = [
                    ("Кто навёл движ", cog.audit.format_entity(entry.user), False),
                    ("Участник", cog.audit.format_entity(member), False),
                    ("Канал", cog.audit.format_channel(before.channel), False),
                ]
                if voice_duration:
                    fields.append(("Просидел в войсе", voice_duration, True))
                await cog.audit.send_event(
                    guild,
                    "member_disconnected",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} выдернул **{_display_name(member)}** из войса.",
                    actor=entry.user,
                    target=member,
                    reason=entry.reason,
                    fields=fields,
                    show_target_field=False,
                    thumbnail_target=member,
                    related_channels=[before.channel],
                    related_users=[member, entry.user],
                )
                await cog.maybe_trigger_protected_voice_guard(
                    target=member,
                    actor=entry.user,
                    source_channel=before.channel,
                )
                return
            await cog._log_voice_session_finished(
                member,
                before.channel,
                duration=voice_duration,
            )
            fields = [("Канал", cog.audit.format_channel(before.channel), False)]
            if voice_duration:
                fields.append(("Просидел в войсе", voice_duration, True))
            await cog.audit.send_event(
                guild,
                "member_voice_left",
                f"**{_display_name(member)}** вышел из войса.",
                target=member,
                fields=fields,
                related_channels=[before.channel],
                related_users=[member],
            )
            return

        if before.channel is None and after.channel is not None:
            await cog.audit.send_event(
                guild,
                "member_voice_joined",
                f"**{_display_name(member)}** залетел в войс.",
                target=member,
                fields=[("Канал", cog.audit.format_channel(after.channel), False)],
                thumbnail_target=member,
                related_channels=[after.channel],
                related_users=[member],
            )
            return

        if before.channel is not None and after.channel is not None:
            voice_duration = cog._stop_session(cog._voice_sessions, member)
            entry = await cog.find_member_move_entry(member, after.channel, max_age_seconds=8)
            if entry is not None and not cog.audit.was_recent(guild.id, "member_moved", member.id, seconds=8):
                cog.audit.remember_recent(guild.id, "member_moved", member.id)
                await cog._log_voice_session_finished(
                    member,
                    before.channel,
                    duration=voice_duration,
                    destination=after.channel,
                    actor=entry.user,
                    reason=entry.reason,
                )
                cog._start_session(cog._voice_sessions, member, replace=True)
                await cog.audit.send_event(
                    guild,
                    "member_moved",
                    (
                        f"{_display_name(entry.user, 'Кто-то из стаффа')} перетащил **{_display_name(member)}** "
                        f"из {before.channel.mention} в {after.channel.mention}."
                    ),
                    actor=entry.user,
                    target=member,
                    reason=entry.reason,
                    fields=[
                        ("Модератор", cog.audit.format_entity(entry.user), False),
                        ("Участник", cog.audit.format_entity(member), False),
                        ("Из канала", cog.audit.format_channel(before.channel), True),
                        ("В канал", cog.audit.format_channel(after.channel), True),
                    ],
                    show_target_field=False,
                    thumbnail_target=member,
                    related_channels=[before.channel, after.channel],
                    related_users=[member, entry.user],
                )
                return
            await cog._log_voice_session_finished(
                member,
                before.channel,
                duration=voice_duration,
                destination=after.channel,
            )
            cog._start_session(cog._voice_sessions, member, replace=True)
            await cog.audit.send_event(
                guild,
                "member_voice_switched",
                f"**{_display_name(member)}** сам переехал между войсами.",
                target=member,
                fields=[
                    ("Из", cog.audit.format_channel(before.channel), True),
                    ("В", cog.audit.format_channel(after.channel), True),
                ],
                thumbnail_target=member,
                related_channels=[before.channel, after.channel],
                related_users=[member],
            )
