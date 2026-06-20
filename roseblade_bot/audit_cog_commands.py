"""
EVA Assistant AuditCog slash-command mixin.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import discord
from discord import app_commands

from roseblade_bot.audit_definitions import CHANNEL_DEFINITIONS, EVENT_CHOICES, EVENT_DEFINITIONS
from roseblade_bot.chat_banter import CHAT_BANTER
from roseblade_bot.formatters import _bool_label, _parse_hex_color
from roseblade_bot.server_banner import ServerBannerRenderResult
from roseblade_bot.voice_guard import VOICE_GUARD


class AuditCogCommandsMixin:
    @app_commands.command(name="audit_setup", description="Создать категорию и каналы для аудита")
    @app_commands.describe(category_name="Название категории аудита")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_setup(
        self,
        interaction: discord.Interaction,
        category_name: str | None = None,
    ) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        category, channels = await self.audit.ensure_guild_setup(interaction.guild, category_name=category_name)
        lines = [f"Категория: {category.name}"]
        for key, channel in channels.items():
            lines.append(f"{CHANNEL_DEFINITIONS[key].name}: {channel.mention}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="audit_status", description="Показать текущую конфигурацию аудит-логов")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        saved = self.store.get_guild(interaction.guild.id)
        nickname_state = self._nickname_prefix_state(interaction.guild.id)
        protected_bans_state = self._protected_bans_state(interaction.guild.id)
        server_banner_state = self._server_banner_state(interaction.guild.id)

        lines = [f"Категория ID: `{saved.get('category_id')}`"]
        for key, definition in CHANNEL_DEFINITIONS.items():
            channel_id = saved["channels"].get(key)
            channel = interaction.guild.get_channel(channel_id or 0)
            channel_value = channel.mention if isinstance(channel, discord.TextChannel) else "не настроен"
            lines.append(f"{definition.name}: {channel_value}")
        lines.append("")
        lines.append(f"Переопределённых цветов: `{len(saved['colors'])}`")
        disabled_events = [key for key, enabled in saved["enabled_events"].items() if not enabled]
        lines.append(f"Отключённых событий: `{len(disabled_events)}`")
        lines.append(
            "Intents:"
            f" members={_bool_label(self.config.enable_members_intent)},"
            f" presences={_bool_label(self.config.enable_presences_intent)},"
            f" message_content={_bool_label(self.config.enable_message_content_intent)}"
        )
        lines.append(f"Префиксы ников: `{len(self.config.nickname_prefix_rules)}`")
        lines.append(
            "Nick sync:"
            f" legacy={len(self.config.nickname_prefix_legacy_prefixes)},"
            f" excluded={len(self.config.nickname_prefix_excluded_user_ids)},"
            f" interval={self.config.nickname_prefix_resync_minutes}m,"
            f" pending={len(self._nickname_sync_queue)},"
            f" last_reason={nickname_state.get('last_queue_reason', 'n/a')}"
        )
        lines.append(
            "Protected bans:"
            f" enabled={_bool_label(self.config.protected_bans_enabled)},"
            f" auto_capture={_bool_label(self.config.protected_bans_auto_capture)},"
            f" count={self.protected_ban_count(interaction.guild.id)},"
            f" enforce={self.config.protected_bans_enforce_minutes}m,"
            f" last_restore={protected_bans_state.get('last_enforce_restored', 0)}"
        )
        protected_voice_guard_count = len(self.get_protected_voice_guard_user_ids(interaction.guild))
        lines.append(
            "Voice guard:"
            f" enabled={_bool_label(self.config.protected_voice_guard_enabled)},"
            f" protected={protected_voice_guard_count},"
            f" phrases={VOICE_GUARD.variants_count}"
        )
        lines.append(
            "Chat EVA:"
            f" enabled={_bool_label(self.config.chat_banter_enabled)},"
            f" chance={self.config.chat_banter_reply_chance:.2f},"
            f" variants={CHAT_BANTER.reply_variants_count}"
        )
        lines.append(
            "PUBG lookup:"
            f" enabled={_bool_label(self.config.pubg_lookup_enabled)},"
            f" configured={_bool_label(self.pubg_lookup.is_configured)},"
            f" channels={self.pubg_lookup.channel_count()},"
            f" roles={self.pubg_lookup.allowed_role_count()},"
            f" platform={self.config.pubg_platform},"
            f" ranked={_bool_label(self.config.pubg_lookup_include_ranked)},"
            f" lifetime={_bool_label(self.config.pubg_lookup_include_lifetime_stats)},"
            f" steam_key={_bool_label(self.pubg_lookup.has_steam_key())}"
        )
        lines.append(
            "Steam digest:"
            f" enabled={_bool_label(self.config.steam_digest_enabled)},"
            f" configured={_bool_label(self.steam_digest.is_configured)},"
            f" channels={self.steam_digest.channel_count()},"
            f" schedule={self.steam_digest.schedule_label()},"
            f" top={self.config.steam_digest_top_count},"
            f" support={_bool_label(self.config.steam_digest_include_support_stats)}"
        )
        lines.append(
            "Server banner:"
            f" enabled={_bool_label(self.config.server_banner_enabled)},"
            f" interval={self.server_banner.schedule_label()},"
            f" online={_bool_label(self.server_banner.online_count_supported)},"
            f" bg={self.server_banner.custom_background_label()},"
            f" last_status={server_banner_state.get('last_status', 'n/a')}"
        )
        ignored = saved["ignored"]
        ignored_channel_count = len(self.get_ignored_channel_ids(interaction.guild.id))
        lines.append(
            "Ignore:"
            f" channels={ignored_channel_count},"
            f" categories={len(ignored['category_ids'])},"
            f" users={len(ignored['user_ids'])},"
            f" roles={len(ignored['role_ids'])}"
        )

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="nick_resync", description="Поставить пересборку ник-префиксов в очередь")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def nick_resync(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        queued = await self.queue_guild_nickname_resync(
            interaction.guild,
            reason="manual_resync",
            full=False,
        )
        await interaction.followup.send(
            (
                f"Поставила в очередь **{queued}** участников для пересинхронизации ников. "
                f"Worker идёт по одному участнику примерно раз в **1.5 сек**."
            ),
            ephemeral=True,
        )

    @app_commands.command(name="protected_bans_sync", description="Синхронизировать текущий бан-лист в owner-only защиту")
    @app_commands.guild_only()
    async def protected_bans_sync(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not await self._ensure_owner_only(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not self.config.protected_bans_enabled:
            await interaction.followup.send(
                "Защищённые пермабаны сейчас выключены в конфиге.",
                ephemeral=True,
            )
            return

        added = await self.sync_current_bans_to_protected(interaction.guild, actor=interaction.user)
        await interaction.followup.send(
            f"Синхронизировала текущий бан-лист. В owner-only защиту добавлено **{added}** банов.",
            ephemeral=True,
        )

    @app_commands.command(name="protected_bans_list", description="Показать owner-only список защищённых пермабанов")
    @app_commands.guild_only()
    async def protected_bans_list(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not await self._ensure_owner_only(interaction):
            return
        entries = list(self._protected_ban_entries(interaction.guild.id).values())
        if not entries:
            await interaction.response.send_message("Список защищённых пермабанов сейчас пуст.", ephemeral=True)
            return

        lines = []
        for entry in entries[:40]:
            user_id = int(entry.get("user_id", 0) or 0)
            label = str(entry.get("display_name") or entry.get("username") or user_id)
            reason = str(entry.get("reason") or "без причины")
            lines.append(f"`{user_id}` • {label} • {reason}")
        message = "\n".join(lines)
        if len(entries) > 40:
            message += f"\n... и ещё {len(entries) - 40}"
        await interaction.response.send_message(message[:1900], ephemeral=True)

    @app_commands.command(name="protected_unban", description="Снять owner-only защиту и разбанить пользователя")
    @app_commands.describe(user_id="ID пользователя или упоминание", reason="Причина разбана")
    @app_commands.guild_only()
    async def protected_unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str | None = None,
    ) -> None:
        assert interaction.guild is not None
        if not await self._ensure_owner_only(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            target_id = self._parse_user_id(user_id)
        except ValueError:
            await interaction.followup.send("Не смогла распознать `user_id`.", ephemeral=True)
            return

        removed = self.remove_protected_ban(interaction.guild.id, target_id)
        try:
            await interaction.guild.unban(
                discord.Object(id=target_id),
                reason=reason or f"EVA protected unban by owner {interaction.user}",
            )
        except discord.NotFound:
            await interaction.followup.send(
                "Этого пользователя уже нет в бан-листе. Защиту я всё равно сняла." if removed else "Этого пользователя уже нет в бан-листе.",
                ephemeral=True,
            )
            return
        except (discord.Forbidden, discord.HTTPException) as error:
            if removed is not None:
                state = self._protected_bans_state(interaction.guild.id)
                entries = self._protected_ban_entries(interaction.guild.id)
                entries[str(target_id)] = removed
                state["entries"] = entries
                self.store.set_service_state(interaction.guild.id, "protected_bans", state)
            await interaction.followup.send(f"Не смогла разбанить пользователя: {error}", ephemeral=True)
            return

        await interaction.followup.send(
            f"Пользователь `{target_id}` снят с owner-only защиты и разбанен.",
            ephemeral=True,
        )

    @app_commands.command(name="steam_digest_now", description="Отправить тестовый Steam-дайджест в текущий канал")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def steam_digest_now(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not self.steam_digest.is_configured:
            await interaction.followup.send(
                "Steam-дайджест сейчас выключен или для него не заданы каналы в конфиге.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if channel is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.followup.send(
                "В этот тип канала я тестовый дайджест не отправлю. Нужен обычный текстовый канал или ветка.",
                ephemeral=True,
            )
            return

        try:
            report = await self.steam_digest.build_report()
            embed = self.steam_digest.build_embed(report)
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as error:
            await interaction.followup.send(f"Не смогла отправить дайджест: {error}", ephemeral=True)
            return
        except Exception as error:
            await interaction.followup.send(f"Не смогла собрать Steam-дайджест: {error}", ephemeral=True)
            return

        await interaction.followup.send("Тестовый Steam-дайджест отправлен в этот канал.", ephemeral=True)

    @app_commands.command(name="server_banner_now", description="Отправить в Discord свежий live-баннер сервера")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def server_banner_now(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self.server_banner.is_enabled:
            await interaction.followup.send(
                "Живой баннер сейчас выключен в конфиге.",
                ephemeral=True,
            )
            return

        prepared: ServerBannerRenderResult | None = None
        try:
            prepared = await self.server_banner.render_banner(interaction.guild)
        except Exception as error:
            await interaction.followup.send(f"Не смогла собрать баннер: {error}", ephemeral=True)
            return

        status, prepared = await self.refresh_guild_server_banner(
            interaction.guild,
            force=True,
            source="slash_command",
            prepared=prepared,
        )
        if status != "updated" or prepared is None:
            await interaction.followup.send(
                f"Баннер не обновился. Статус: `{status}`.",
                ephemeral=True,
            )
            return

        preview = discord.File(
            BytesIO(prepared.image_bytes),
            filename="roseblade-live-banner.png",
        )
        online_value = prepared.stats.online_count if prepared.stats.online_count is not None else "н/д"
        await interaction.followup.send(
            (
                f"Баннер обновлён. "
                f"Участников: **{prepared.stats.member_count}**, "
                f"онлайн: **{online_value}**, "
                f"в войсе: **{prepared.stats.voice_count}**."
            ),
            ephemeral=True,
            file=preview,
        )

    @app_commands.command(name="audit_events", description="Список ключей событий для настройки цветов")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_events(self, interaction: discord.Interaction) -> None:
        lines = []
        for event_key in EVENT_CHOICES:
            event = EVENT_DEFINITIONS[event_key]
            lines.append(f"`{event_key}` -> {event.title} / {CHANNEL_DEFINITIONS[event.channel_key].name}")
        message = "\n".join(lines)
        await interaction.response.send_message(message[:1990], ephemeral=True)

    @app_commands.command(name="audit_set_color", description="Задать цвет для конкретного события")
    @app_commands.describe(
        event_key="Ключ события, см. /audit_events",
        color="HEX цвет вроде #FFAA00 или слово default",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_set_color(
        self,
        interaction: discord.Interaction,
        event_key: str,
        color: str,
    ) -> None:
        assert interaction.guild is not None

        if event_key not in EVENT_DEFINITIONS:
            await interaction.response.send_message(
                "Неизвестный ключ события. Сначала посмотри /audit_events.",
                ephemeral=True,
            )
            return

        try:
            parsed = _parse_hex_color(color)
        except ValueError:
            await interaction.response.send_message(
                "Неверный цвет. Используй формат `#RRGGBB` или `default`.",
                ephemeral=True,
            )
            return

        if parsed == -1:
            self.store.remove_color_override(interaction.guild.id, event_key)
            await interaction.response.send_message(
                f"Цвет события `{event_key}` сброшен к значению по умолчанию.",
                ephemeral=True,
            )
            return

        self.store.update_guild(interaction.guild.id, colors={event_key: parsed})
        await interaction.response.send_message(
            f"Для события `{event_key}` установлен цвет `#{parsed:06X}`.",
            ephemeral=True,
        )

    async def event_key_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        del interaction
        current_lower = current.lower()
        matches = [
            app_commands.Choice(name=f"{key} - {EVENT_DEFINITIONS[key].title}", value=key)
            for key in EVENT_CHOICES
            if current_lower in key.lower() or current_lower in EVENT_DEFINITIONS[key].title.lower()
        ]
        return matches[:25]

    async def channel_key_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        del interaction
        current_lower = current.lower()
        matches = [
            app_commands.Choice(name=f"{key} - {CHANNEL_DEFINITIONS[key].name}", value=key)
            for key in sorted(CHANNEL_DEFINITIONS)
            if current_lower in key.lower() or current_lower in CHANNEL_DEFINITIONS[key].name.lower()
        ]
        return matches[:25]

    @audit_set_color.autocomplete("event_key")
    async def audit_set_color_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self.event_key_autocomplete(interaction, current)

    @app_commands.command(name="audit_toggle", description="Включить или выключить конкретный лог")
    @app_commands.describe(event_key="Ключ события, см. /audit_events", enabled="Вкл или выкл")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_toggle(
        self,
        interaction: discord.Interaction,
        event_key: str,
        enabled: bool,
    ) -> None:
        assert interaction.guild is not None
        if event_key not in EVENT_DEFINITIONS:
            await interaction.response.send_message("Неизвестный ключ события.", ephemeral=True)
            return
        self.store.set_event_enabled(interaction.guild.id, event_key, enabled)
        await interaction.response.send_message(
            f"Событие `{event_key}` теперь {_bool_label(enabled)}.",
            ephemeral=True,
        )

    @audit_toggle.autocomplete("event_key")
    async def audit_toggle_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self.event_key_autocomplete(interaction, current)

    @app_commands.command(name="audit_bind", description="Привязать лог-категорию к конкретному текстовому каналу")
    @app_commands.describe(channel_key="Ключ лог-категории", channel="Канал, куда отправлять эти логи")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_bind(
        self,
        interaction: discord.Interaction,
        channel_key: str,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild is not None
        if channel_key not in CHANNEL_DEFINITIONS:
            await interaction.response.send_message("Неизвестный ключ лог-категории.", ephemeral=True)
            return
        self.store.update_guild(interaction.guild.id, channels={channel_key: channel.id})
        await interaction.response.send_message(
            f"Логи `{CHANNEL_DEFINITIONS[channel_key].name}` теперь идут в {channel.mention}.",
            ephemeral=True,
        )

    @audit_bind.autocomplete("channel_key")
    async def audit_bind_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self.channel_key_autocomplete(interaction, current)

    @app_commands.command(name="audit_export", description="Выгрузить историю логов этого сервера в JSON")
    @app_commands.describe(limit="Сколько последних записей выгрузить")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_export(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 1000] = 100) -> None:
        assert interaction.guild is not None
        audit_file = self.audit.export_history(interaction.guild.id, limit=limit)
        await interaction.response.send_message(
            content=f"Экспорт последних `{limit}` записей.",
            file=audit_file,
            ephemeral=True,
        )

    @app_commands.command(name="audit_ignore_channel", description="Игнорировать события из канала")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_ignore_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel) -> None:
        assert interaction.guild is not None
        self.store.add_ignored_id(interaction.guild.id, "channel_ids", channel.id)
        await interaction.response.send_message(f"Канал {channel.mention} добавлен в ignore.", ephemeral=True)

    @app_commands.command(name="audit_unignore_channel", description="Снять ignore с канала")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_unignore_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel) -> None:
        assert interaction.guild is not None
        self.store.remove_ignored_id(interaction.guild.id, "channel_ids", channel.id)
        await interaction.response.send_message(f"Канал {channel.mention} убран из ignore.", ephemeral=True)

    @app_commands.command(name="audit_ignore_category", description="Игнорировать события из категории")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_ignore_category(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        assert interaction.guild is not None
        self.store.add_ignored_id(interaction.guild.id, "category_ids", category.id)
        await interaction.response.send_message(f"Категория **{category.name}** добавлена в ignore.", ephemeral=True)

    @app_commands.command(name="audit_unignore_category", description="Снять ignore с категории")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_unignore_category(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        assert interaction.guild is not None
        self.store.remove_ignored_id(interaction.guild.id, "category_ids", category.id)
        await interaction.response.send_message(f"Категория **{category.name}** убрана из ignore.", ephemeral=True)

    @app_commands.command(name="audit_ignore_user", description="Игнорировать события пользователя")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_ignore_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        self.store.add_ignored_id(interaction.guild.id, "user_ids", member.id)
        await interaction.response.send_message(f"Пользователь {member.mention} добавлен в ignore.", ephemeral=True)

    @app_commands.command(name="audit_unignore_user", description="Снять ignore с пользователя")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_unignore_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        self.store.remove_ignored_id(interaction.guild.id, "user_ids", member.id)
        await interaction.response.send_message(f"Пользователь {member.mention} убран из ignore.", ephemeral=True)

    @app_commands.command(name="audit_ignore_role", description="Игнорировать события роли")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_ignore_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        assert interaction.guild is not None
        self.store.add_ignored_id(interaction.guild.id, "role_ids", role.id)
        await interaction.response.send_message(f"Роль {role.mention} добавлена в ignore.", ephemeral=True)

    @app_commands.command(name="audit_unignore_role", description="Снять ignore с роли")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def audit_unignore_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        assert interaction.guild is not None
        self.store.remove_ignored_id(interaction.guild.id, "role_ids", role.id)
        await interaction.response.send_message(f"Роль {role.mention} убрана из ignore.", ephemeral=True)
