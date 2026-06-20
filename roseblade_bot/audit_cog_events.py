"""
EVA Assistant AuditCog event-listener mixin.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from roseblade_bot.audit_snapshots import (
    _automod_rule_snapshot,
    _channel_snapshot,
    _emoji_snapshot,
    _invite_entry_snapshot,
    _role_snapshot,
    _scheduled_event_snapshot,
    _soundboard_snapshot,
    _stage_snapshot,
    _sticker_snapshot,
    _thread_snapshot,
    _webhook_snapshot,
)
from roseblade_bot.formatters import _display_name
from roseblade_bot.message_handlers import (
    handle_on_message,
    handle_on_message_delete,
    handle_on_message_edit,
    handle_on_raw_bulk_message_delete,
    handle_on_raw_message_delete,
    handle_on_raw_message_edit,
)
from roseblade_bot.voice_handlers import handle_on_voice_state_update


class AuditCogEventsMixin:
    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        guild = entry.guild
        if not self.store.get_guild(guild.id)["channels"]:
            return

        action = entry.action
        action_value = getattr(action, "value", None)
        target = entry.target

        # Compare by raw audit action value to avoid enum alias inconsistencies across discord.py builds.
        if action_value == 20:
            target_id = getattr(target, "id", 0)
            if target_id:
                self.audit.remember_recent(guild.id, "member_kicked", target_id)
            await self.audit.send_event(
                guild,
                "member_kicked",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} показал **{_display_name(target)}** дверь сервера.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                related_users=[entry.user, target],
            )
        elif action_value == 21:
            removed = getattr(entry.extra, "members_removed", None)
            prune_days = getattr(entry.extra, "delete_member_days", None)
            fields = []
            if removed is not None:
                fields.append(("Сколько убрало", str(removed), True))
            if prune_days is not None:
                fields.append(("Неактивность от", f"{prune_days} дн.", True))
            await self.audit.send_event(
                guild,
                "members_pruned",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} устроил массовую чистку неактивных участников.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
                include_case_id=False,
            )
        elif action_value == 22:
            target_id = getattr(target, "id", 0)
            if target_id:
                self.audit.remember_recent(guild.id, "member_banned", target_id)
            if (
                self.config.protected_bans_enabled
                and self.config.protected_bans_auto_capture
                and isinstance(target, (discord.User, discord.Member))
            ):
                self.upsert_protected_ban(
                    guild,
                    target,
                    actor=entry.user,
                    reason=entry.reason,
                    source="audit_ban",
                )
            await self.audit.send_event(
                guild,
                "member_banned",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} отправил **{_display_name(target)}** отдыхать в бан-лист.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                related_users=[entry.user, target],
            )
        elif action_value == 23:
            target_id = getattr(target, "id", 0)
            if target_id:
                self.audit.remember_recent(guild.id, "member_unbanned", target_id)
            if self.config.protected_bans_enabled and target_id and self.is_protected_ban(guild.id, target_id):
                if entry.user is not None and entry.user.id == guild.owner_id:
                    self.remove_protected_ban(guild.id, target_id)
                    fields = [("Статус защиты", "Снята владельцем сервера", False)]
                    await self.audit.send_event(
                        guild,
                        "member_unbanned",
                        f"{_display_name(entry.user, 'Владелец сервера')} лично вытащил **{_display_name(target)}** из owner-only бан-листа.",
                        actor=entry.user,
                        target=target,
                        reason=entry.reason,
                        fields=fields,
                        related_users=[entry.user, target],
                    )
                    return

                try:
                    await guild.ban(
                        target,
                        reason=(
                            "EVA protected perma-ban: "
                            f"неавторизованный разбан пользователем {_display_name(entry.user, 'Неизвестно')}"
                        ),
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

                fields = [
                    ("Кто может разбанить", "Только владелец сервера", False),
                ]
                protected_entry = self.protected_ban_entry(guild.id, target_id)
                protected_reason = None if protected_entry is None else protected_entry.get("reason")
                if protected_reason:
                    fields.append(("Изначальная причина бана", str(protected_reason), False))
                await self.audit.send_event(
                    guild,
                    "protected_ban_restored",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} попытался разбанить **{_display_name(target)}**, но Ева вернула бан обратно.",
                    actor=entry.user,
                    target=target,
                    reason=entry.reason,
                    fields=fields,
                    related_users=[entry.user, target],
                    show_actor_field=True,
                    show_target_field=True,
                )
                return
            await self.audit.send_event(
                guild,
                "member_unbanned",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} вернул **{_display_name(target)}** из бан-листа.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                related_users=[entry.user, target],
            )
        elif action_value == 10:
            channel_name, fields = _channel_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "channel_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} открыл канал **{discord.utils.escape_markdown(channel_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.abc.GuildChannel) else None],
                related_channel_ids=[getattr(target, "id", None)],
                related_users=[entry.user],
            )
        elif action_value == 12:
            channel_name, fields = _channel_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "channel_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} снёс канал **{discord.utils.escape_markdown(channel_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.abc.GuildChannel) else None],
                related_users=[entry.user],
            )
        elif action_value == 11:
            channel_name, fields = _channel_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "channel_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} подкрутил канал **{discord.utils.escape_markdown(channel_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.abc.GuildChannel) else None],
                related_users=[entry.user],
            )
        elif action_value in {13, 14, 15}:
            changes = self.audit.describe_changes(entry)
            fields = [("Канал", self.audit.format_entity(target), False)] if target is not None else []
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "channel_permissions_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} перекроил доступы к каналу.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.abc.GuildChannel) else None],
                related_users=[entry.user],
            )
        elif action_value == 110:
            thread_name, fields = _thread_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "thread_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} завёл ветку **{discord.utils.escape_markdown(thread_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.Thread) else None],
                related_channel_ids=[getattr(target, "id", None)],
                related_users=[entry.user],
            )
        elif action_value == 112:
            thread_name, fields = _thread_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "thread_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} прикрыл ветку **{discord.utils.escape_markdown(thread_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.Thread) else None],
                related_channel_ids=[getattr(target, "id", None)],
                related_users=[entry.user],
            )
        elif action_value == 111:
            thread_name, fields = _thread_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "thread_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил ветку **{discord.utils.escape_markdown(thread_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[target if isinstance(target, discord.Thread) else None],
                related_channel_ids=[getattr(target, "id", None)],
                related_users=[entry.user],
            )
        elif action_value == 30:
            role_name, fields = _role_snapshot(entry)
            await self.audit.send_event(
                guild,
                "role_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} создал роль **{discord.utils.escape_markdown(role_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_roles=[target if isinstance(target, discord.Role) else None],
                related_users=[entry.user],
            )
        elif action_value == 32:
            role_name, fields = _role_snapshot(entry)
            await self.audit.send_event(
                guild,
                "role_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} отправил роль **{discord.utils.escape_markdown(role_name)}** в архив забвения.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_roles=[target if isinstance(target, discord.Role) else None],
                related_users=[entry.user],
            )
        elif action_value == 31:
            role_name, fields = _role_snapshot(entry)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "role_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил роль **{discord.utils.escape_markdown(role_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_roles=[target if isinstance(target, discord.Role) else None],
                related_users=[entry.user],
            )
        elif action_value == 25:
            added_roles = list(getattr(entry.after, "roles", []) or [])
            removed_roles = list(getattr(entry.before, "roles", []) or [])
            target_id = getattr(target, "id", 0)
            target_member = await self.resolve_member(guild, target)

            if added_roles:
                if target_id:
                    self.audit.remember_recent(guild.id, "member_role_added", target_id)
                await self.audit.send_event(
                    guild,
                    "member_role_added",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} накинул роли участнику **{_display_name(target)}**.",
                    actor=entry.user,
                    target=target,
                    reason=entry.reason,
                    fields=[("Какие роли прилетели", self.audit.format_entity(added_roles), False)],
                    show_actor_field=True,
                    show_target_field=True,
                    actor_label="Кто навёл движ",
                    target_label="Кому прилетело",
                    thumbnail_target=target,
                    related_users=[entry.user, target],
                    related_roles=added_roles,
                )
                if target_member is not None:
                    self.queue_member_nickname_sync(target_member)

            if removed_roles:
                if target_id:
                    self.audit.remember_recent(guild.id, "member_role_removed", target_id)
                await self.audit.send_event(
                    guild,
                    "member_role_removed",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} снял роли с участника **{_display_name(target)}**.",
                    actor=entry.user,
                    target=target,
                    reason=entry.reason,
                    fields=[("Что именно улетело", self.audit.format_entity(removed_roles), False)],
                    show_actor_field=True,
                    show_target_field=True,
                    actor_label="Кто навёл движ",
                    target_label="Кого разжаловали",
                    thumbnail_target=target,
                    related_users=[entry.user, target],
                    related_roles=removed_roles,
                )
                if target_member is not None:
                    self.queue_member_nickname_sync(target_member)
        elif action_value == 28:
            await self.audit.send_event(
                guild,
                "bot_added",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} добавил на сервер бота **{_display_name(target)}**.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                fields=[
                    (
                        "Аккаунт бота создан",
                        discord.utils.format_dt(target.created_at, style="F")
                        if isinstance(target, (discord.Member, discord.User))
                        else "Неизвестно",
                        False,
                    )
                ],
                related_users=[entry.user, target],
                thumbnail_target=target,
            )
        elif action_value == 40:
            code, fields = _invite_entry_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "invite_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} выкатил приглашение **{code}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.target, "channel", None), getattr(entry.after, "channel", None)],
                related_users=[entry.user, getattr(entry.target, "inviter", None), getattr(entry.after, "inviter", None)],
            )
        elif action_value == 41:
            code, fields = _invite_entry_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "invite_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} освежил настройки приглашения **{code}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.target, "channel", None), getattr(entry.after, "channel", None)],
                related_users=[entry.user, getattr(entry.target, "inviter", None), getattr(entry.after, "inviter", None)],
            )
        elif action_value == 42:
            code, fields = _invite_entry_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "invite_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} прикрыл приглашение **{code}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.before, "channel", None), getattr(entry.target, "channel", None)],
                related_users=[entry.user, getattr(entry.before, "inviter", None), getattr(entry.target, "inviter", None)],
            )
        elif action_value == 60:
            emoji_name, fields = _emoji_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "emoji_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} добавил эмодзи **{discord.utils.escape_markdown(emoji_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 61:
            emoji_name, fields = _emoji_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "emoji_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил эмодзи **{discord.utils.escape_markdown(emoji_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 62:
            emoji_name, fields = _emoji_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "emoji_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} убрал эмодзи **{discord.utils.escape_markdown(emoji_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value in {74, 75}:
            channel = getattr(entry.extra, "channel", None)
            message_id = getattr(entry.extra, "message_id", None)
            action_key = "message_pinned" if action_value == 74 else "message_unpinned"
            action_text = "приколол" if action_value == 74 else "открепил"
            actor_label = "Кто закрепил" if action_value == 74 else "Кто открепил"
            fields: list[tuple[str, str, bool]] = []
            if channel is not None:
                fields.append(("Канал", self.audit.format_channel(channel), False))
            if message_id is not None:
                fields.append(("Message ID", f"`{message_id}`", True))
                if channel is not None and getattr(channel, "id", None) is not None:
                    fields.append(("Ссылка", _message_jump_url(guild.id, channel.id, message_id), False))
                    if isinstance(channel, (discord.TextChannel, discord.Thread)):
                        fields.extend(await self.fetch_message_excerpt(channel, message_id))
            await self.audit.send_event(
                guild,
                action_key,
                f"{_display_name(entry.user, 'Кто-то из стаффа')} {action_text} сообщение **{_display_name(target, 'без автора')}**.",
                actor=entry.user,
                target=target,
                reason=entry.reason,
                fields=fields,
                show_actor_field=True,
                show_target_field=target is not None,
                actor_label=actor_label,
                target_label="Чьё сообщение",
                thumbnail_target=target,
                related_channels=[channel],
                related_users=[entry.user, target],
                include_case_id=False,
            )
        elif action_value == 1:
            changes = self.audit.describe_changes(entry)
            fields: list[tuple[str, str, bool]] = []
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "server_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} снова крутил гайки сервера.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 83:
            stage_topic, fields = _stage_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "stage_instance_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} открыл сцену **{discord.utils.escape_markdown(stage_topic)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.extra, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 84:
            stage_topic, fields = _stage_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "stage_instance_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил сцену **{discord.utils.escape_markdown(stage_topic)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.extra, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 85:
            stage_topic, fields = _stage_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "stage_instance_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} закрыл сцену **{discord.utils.escape_markdown(stage_topic)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.extra, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 90:
            sticker_name, fields = _sticker_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "sticker_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} добавил стикер **{discord.utils.escape_markdown(sticker_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 91:
            sticker_name, fields = _sticker_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "sticker_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил стикер **{discord.utils.escape_markdown(sticker_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 92:
            sticker_name, fields = _sticker_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "sticker_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} убрал стикер **{discord.utils.escape_markdown(sticker_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 100:
            event_name, fields = _scheduled_event_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "scheduled_event_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} создал событие **{discord.utils.escape_markdown(event_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.target, "channel", None), getattr(entry.after, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 101:
            event_name, fields = _scheduled_event_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "scheduled_event_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил событие **{discord.utils.escape_markdown(event_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.target, "channel", None), getattr(entry.after, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 102:
            event_name, fields = _scheduled_event_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "scheduled_event_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} отменил событие **{discord.utils.escape_markdown(event_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(entry.before, "channel", None), getattr(entry.target, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 50:
            webhook_name, fields = _webhook_snapshot(target, self.audit)
            await self.audit.send_event(
                guild,
                "webhook_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} создал вебхук **{discord.utils.escape_markdown(webhook_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(target, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 130:
            sound_name, fields = _soundboard_snapshot(entry)
            await self.audit.send_event(
                guild,
                "soundboard_sound_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} добавил звук **{discord.utils.escape_markdown(sound_name)}** на саунд-панель.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 131:
            sound_name, fields = _soundboard_snapshot(entry)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "soundboard_sound_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил звук **{discord.utils.escape_markdown(sound_name)}** на саунд-панели.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 132:
            sound_name, fields = _soundboard_snapshot(entry)
            await self.audit.send_event(
                guild,
                "soundboard_sound_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} убрал звук **{discord.utils.escape_markdown(sound_name)}** с саунд-панели.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 140:
            rule_name, fields = _automod_rule_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "automod_rule_created",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} создал правило автомода **{discord.utils.escape_markdown(rule_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 141:
            rule_name, fields = _automod_rule_snapshot(entry, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "automod_rule_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} подкрутил правило автомода **{discord.utils.escape_markdown(rule_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value == 142:
            rule_name, fields = _automod_rule_snapshot(entry, self.audit)
            await self.audit.send_event(
                guild,
                "automod_rule_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} снял с дежурства правило автомода **{discord.utils.escape_markdown(rule_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_users=[entry.user],
            )
        elif action_value in {143, 144, 145, 146}:
            extra = entry.extra
            channel = getattr(extra, "channel", None)
            rule_name = getattr(extra, "automod_rule_name", "Неизвестное правило")
            trigger_type = getattr(extra, "automod_rule_trigger_type", None)
            key_map = {
                143: "automod_action_blocked",
                144: "automod_action_flagged",
                145: "automod_action_timeout",
                146: "automod_action_quarantined",
            }
            description_map = {
                143: f"Автомод остановил сообщение участника **{_display_name(target)}** ещё на подлёте.",
                144: f"Автомод поднял флаг на участника **{_display_name(target)}** и позвал модерацию посмотреть.",
                145: f"Автомод выдал тайм-аут участнику **{_display_name(target)}**.",
                146: f"Автомод ограничил взаимодействия участнику **{_display_name(target)}**.",
            }
            fields = [
                ("Правило", f"**{discord.utils.escape_markdown(str(rule_name))}**", False),
                ("Триггер", self.audit.format_change_value(trigger_type) if trigger_type is not None else "Неизвестно", True),
            ]
            if channel is not None:
                fields.append(("Канал", self.audit.format_channel(channel), False))
            await self.audit.send_event(
                guild,
                key_map[action_value],
                description_map[action_value],
                actor=entry.user if entry.user is not None else None,
                target=target,
                reason=entry.reason,
                fields=fields,
                show_actor_field=False,
                show_target_field=target is not None,
                target_label="Участник",
                thumbnail_target=target,
                related_channels=[channel],
                related_users=[entry.user, target],
                include_case_id=action_value in {145, 146},
            )
        elif action_value == 52:
            webhook_name, fields = _webhook_snapshot(target, self.audit)
            await self.audit.send_event(
                guild,
                "webhook_deleted",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} удалил вебхук **{discord.utils.escape_markdown(webhook_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(target, "channel", None)],
                related_users=[entry.user],
            )
        elif action_value == 51:
            webhook_name, fields = _webhook_snapshot(target, self.audit)
            changes = self.audit.describe_changes(entry)
            if changes:
                fields.append(("Что изменилось", changes, False))
            await self.audit.send_event(
                guild,
                "webhook_updated",
                f"{_display_name(entry.user, 'Кто-то из стаффа')} обновил вебхук **{discord.utils.escape_markdown(webhook_name)}**.",
                actor=entry.user,
                reason=entry.reason,
                fields=fields,
                show_target_field=False,
                related_channels=[getattr(target, "channel", None)],
                related_users=[entry.user],
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        self.queue_member_nickname_sync(member)
        await self.audit.send_event(
            member.guild,
            "member_joined",
            f"На сервер залетел **{_display_name(member)}**. Добро пожаловать в движ.",
            target=member,
            fields=[
                ("Аккаунт создан", discord.utils.format_dt(member.created_at, style="F"), False),
                ("Возраст аккаунта", discord.utils.format_dt(member.created_at, style="R"), False),
            ],
            related_users=[member],
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        if not self.config.protected_bans_enabled or not self.config.protected_bans_auto_capture:
            return
        self.upsert_protected_ban(
            guild,
            user,
            source="member_ban_event",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return

        if self.audit.was_recent(member.guild.id, "member_kicked", member.id, seconds=10):
            return
        if self.audit.was_recent(member.guild.id, "member_banned", member.id, seconds=10):
            return

        await self.audit.send_event(
            member.guild,
            "member_left",
            f"**{_display_name(member)}** покинул сервер. Вышел красиво или просто растворился в тумане.",
            target=member,
            fields=[
                (
                    "Присоединился к серверу",
                    discord.utils.format_dt(member.joined_at, style="F") if member.joined_at else "Неизвестно",
                    False,
                ),
                (
                    "Роли",
                    ", ".join(role.mention for role in member.roles if not role.is_default()) or "Нет ролей",
                    False,
                ),
            ],
            related_users=[member],
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot:
            return

        guild = after.guild
        skip_nickname_log = self._was_recent_managed_nickname_update(after)

        if before.nick != after.nick and not skip_nickname_log:
            entry = await self.audit.fetch_recent_audit_entry(
                guild,
                actions=[discord.AuditLogAction.member_update],
                target_id=after.id,
                max_age_seconds=15,
            )
            await self.audit.send_event(
                guild,
                "nickname_changed",
                f"Участник **{_display_name(before)}** теперь проходит как **{_display_name(after)}**.",
                actor=entry.user if entry else None,
                target=after,
                reason=entry.reason if entry else None,
                related_users=[after, entry.user if entry else None],
            )

        before_roles = {role.id: role for role in before.roles if not role.is_default()}
        after_roles = {role.id: role for role in after.roles if not role.is_default()}
        added_roles = [role for role_id, role in after_roles.items() if role_id not in before_roles]
        removed_roles = [role for role_id, role in before_roles.items() if role_id not in after_roles]
        if self.audit.was_recent(guild.id, "member_role_added", after.id, seconds=10):
            added_roles = []
        if self.audit.was_recent(guild.id, "member_role_removed", after.id, seconds=10):
            removed_roles = []
        if added_roles or removed_roles:
            entry = await self.audit.fetch_recent_audit_entry(
                guild,
                actions=[discord.AuditLogAction.member_role_update],
                target_id=after.id,
                max_age_seconds=15,
            )
            if added_roles:
                await self.audit.send_event(
                    guild,
                    "member_role_added",
                    f"Участнику **{_display_name(after)}** накинули новые роли.",
                    actor=entry.user if entry else None,
                    target=after,
                    reason=entry.reason if entry else None,
                    fields=[("Какие роли прилетели", self.audit.format_entity(added_roles), False)],
                    show_actor_field=entry is not None,
                    show_target_field=True,
                    actor_label="Кто навёл движ",
                    target_label="Кому прилетело",
                    thumbnail_target=after,
                    related_users=[after, entry.user if entry else None],
                    related_roles=added_roles,
                )
            if removed_roles:
                await self.audit.send_event(
                    guild,
                    "member_role_removed",
                    f"С участника **{_display_name(after)}** сняли роли.",
                    actor=entry.user if entry else None,
                    target=after,
                    reason=entry.reason if entry else None,
                    fields=[("Что именно улетело", self.audit.format_entity(removed_roles), False)],
                    show_actor_field=entry is not None,
                    show_target_field=True,
                    actor_label="Кто навёл движ",
                    target_label="Кого разжаловали",
                    thumbnail_target=after,
                    related_users=[after, entry.user if entry else None],
                    related_roles=removed_roles,
                )

        if before.timed_out_until != after.timed_out_until:
            entry = await self.audit.fetch_recent_audit_entry(
                guild,
                actions=[
                    discord.AuditLogAction.member_update,
                    discord.AuditLogAction.automod_timeout_member,
                ],
                target_id=after.id,
                max_age_seconds=15,
            )
            if after.timed_out_until is not None:
                self.audit.remember_recent(guild.id, "member_timeout_applied", after.id)
                await self.audit.send_event(
                    guild,
                    "member_timeout_applied",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} отправил **{_display_name(after)}** посидеть в тайм-ауте.",
                    actor=entry.user if entry else None,
                    target=after,
                    reason=entry.reason if entry else None,
                    fields=[
                        (
                            "До",
                            discord.utils.format_dt(after.timed_out_until, style="F"),
                            False,
                        )
                    ],
                    related_users=[after, entry.user if entry else None],
                )
            else:
                self.audit.remember_recent(guild.id, "member_timeout_removed", after.id)
                await self.audit.send_event(
                    guild,
                    "member_timeout_removed",
                    f"{_display_name(entry.user, 'Кто-то из стаффа')} вернул **{_display_name(after)}** из тайм-аута.",
                    actor=entry.user if entry else None,
                    target=after,
                    reason=entry.reason if entry else None,
                    related_users=[after, entry.user if entry else None],
                )

        if before.premium_since != after.premium_since and after.premium_since is not None:
            await self.audit.send_event(
                guild,
                "server_boosted",
                f"**{_display_name(after)}** бустанул сервер. Красиво зашёл.",
                target=after,
                fields=[("С", discord.utils.format_dt(after.premium_since, style="F"), False)],
                related_users=[after],
            )

        if before.nick != after.nick or before.roles != after.roles:
            self.queue_member_nickname_sync(after)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await handle_on_message(self, message)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        await handle_on_message_delete(self, message)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        await handle_on_raw_message_delete(self, payload)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        await handle_on_raw_bulk_message_delete(self, payload)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        await handle_on_message_edit(self, before, after)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        await handle_on_raw_message_edit(self, payload)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        await handle_on_voice_state_update(self, member, before, after)
