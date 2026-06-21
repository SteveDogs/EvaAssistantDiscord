"""
EVA Assistant music cog.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import wavelink

from roseblade_bot.cogs.shared import EvaPassiveSharedCog
from roseblade_bot.music import MusicCommandError
from roseblade_bot.music.phrases import (
    fallback_suffix,
    join_voice_line,
    leave_line,
    now_playing_line,
    pause_line,
    play_started_line,
    playlist_queued_line,
    playlist_started_line,
    queue_added_line,
    resume_line,
    shuffle_line,
    skip_line,
    stop_line,
    volume_line,
)


class EvaMusicCog(EvaPassiveSharedCog):
    async def cog_load(self) -> None:
        await self.music.startup(self.bot)

    async def _ensure_music_ready(self, interaction: discord.Interaction) -> None:
        await self.music.ensure_started(self.bot)
        if interaction.guild is None:
            raise MusicCommandError("Музыка работает только внутри сервера.")

    @app_commands.command(name="music_status", description="Показать состояние музыкальной ноды EVA")
    @app_commands.guild_only()
    async def music_status(self, interaction: discord.Interaction) -> None:
        await self._respond_safe(interaction, embed=self.music.build_status_embed(), ephemeral=True)

    @app_commands.command(name="music_join", description="Подключить Еву к твоему голосовому каналу")
    @app_commands.guild_only()
    async def music_join(self, interaction: discord.Interaction) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=True)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        self.music.bind_home_channel(interaction.guild_id or 0, interaction.channel_id)
        channel_name = player.channel.name if player.channel else "неизвестный канал"
        await self._respond_safe(interaction, join_voice_line(channel_name))

    @app_commands.command(name="music_play", description="Включить трек, ссылку или плейлист")
    @app_commands.describe(query="Название трека, YouTube Music ссылка, YouTube ссылка или Spotify ссылка")
    @app_commands.guild_only()
    async def music_play(self, interaction: discord.Interaction, query: str) -> None:
        await self._handle_play(interaction, query)

    @app_commands.command(name="play", description="Включить трек или плейлист с подсказками EVA")
    @app_commands.describe(query="Название трека, артист, YouTube Music ссылка, YouTube ссылка или Spotify ссылка")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await self._handle_play(interaction, query)

    async def _handle_play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(thinking=True)
        try:
            await self._ensure_music_ready(interaction)
            result = await self.music.enqueue_query(interaction, query)
        except MusicCommandError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return

        if result.started_track is not None:
            track_title = result.started_track.title or "безымянный трек"
            description = play_started_line(track_title)
            if result.playlist_name:
                description = playlist_started_line(result.playlist_name, result.playlist_size)
            if result.used_fallback:
                description += fallback_suffix()
            embed = self.music.build_track_embed(
                title="🎶 Стартанула музыку",
                description=description,
                track=result.started_track,
            )
            await interaction.followup.send(embed=embed)
            return

        player = result.player
        queued_total = len(player.queue)
        text = (
            queue_added_line(result.queued_count, queued_total)
            if not result.playlist_name
            else playlist_queued_line(result.playlist_name, queued_total)
        )
        if result.used_fallback:
            text += fallback_suffix()
        await interaction.followup.send(text)

    async def _autocomplete_query(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild is None or not self.music.is_enabled:
            return []
        if len(current.strip()) < 2:
            return []
        if not isinstance(interaction.user, discord.Member):
            return []
        if not self.music.member_is_allowed(interaction.user):
            return []

        try:
            await self.music.ensure_started(self.bot)
            suggestions = await self.music.autocomplete_query(current, limit=10)
        except Exception:
            return []

        return [app_commands.Choice(name=item.label, value=item.value) for item in suggestions]

    @music_play.autocomplete("query")
    async def music_play_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self._autocomplete_query(interaction, current)

    @play.autocomplete("query")
    async def play_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self._autocomplete_query(interaction, current)

    @app_commands.command(name="music_now", description="Показать текущий трек")
    @app_commands.guild_only()
    async def music_now(self, interaction: discord.Interaction) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=False)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        if player.current is None:
            await self._respond_safe(interaction, "Сейчас тишина. Поставь что-нибудь через `/play`.", ephemeral=True)
            return

        embed = self.music.build_track_embed(
            title="🎵 Сейчас играет",
            description=now_playing_line(),
            track=player.current,
        )
        await self._respond_safe(interaction, embed=embed)

    @app_commands.command(name="music_queue", description="Показать очередь треков")
    @app_commands.guild_only()
    async def music_queue(self, interaction: discord.Interaction) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=False)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        await self._respond_safe(interaction, embed=self.music.build_queue_embed(player))

    @app_commands.command(name="music_skip", description="Скипнуть текущий трек")
    @app_commands.guild_only()
    async def music_skip(self, interaction: discord.Interaction) -> None:
        await self._handle_skip(interaction)

    @app_commands.command(name="skip", description="Быстро переключить на следующий трек")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction) -> None:
        await self._handle_skip(interaction)

    async def _handle_skip(self, interaction: discord.Interaction) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=False)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        if player.current is None:
            await self._respond_safe(interaction, "Скипать нечего, там уже тишина.", ephemeral=True)
            return

        title = player.current.title or "безымянный трек"
        await player.skip(force=True)
        await self._respond_safe(interaction, skip_line(title))

    @app_commands.command(name="music_pause", description="Поставить музыку на паузу")
    @app_commands.guild_only()
    async def music_pause(self, interaction: discord.Interaction) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=False)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        if player.current is None:
            await self._respond_safe(interaction, "Пауза не нужна, трек и так не идёт.", ephemeral=True)
            return
        if player.paused:
            await self._respond_safe(interaction, "Музыка уже стоит на паузе.", ephemeral=True)
            return

        await player.pause(True)
        await self._respond_safe(interaction, pause_line())

    @app_commands.command(name="music_resume", description="Снять паузу и продолжить")
    @app_commands.guild_only()
    async def music_resume(self, interaction: discord.Interaction) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=False)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        if player.current is None:
            await self._respond_safe(interaction, "Возобновлять пока нечего.", ephemeral=True)
            return
        if not player.paused:
            await self._respond_safe(interaction, "Музыка и так уже играет.", ephemeral=True)
            return

        await player.pause(False)
        await self._respond_safe(interaction, resume_line())

    @app_commands.command(name="music_stop", description="Остановить текущий трек и очистить очередь")
    @app_commands.guild_only()
    async def music_stop(self, interaction: discord.Interaction) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=False)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        player.queue.clear()
        await player.stop()
        await self._respond_safe(interaction, stop_line())

    @app_commands.command(name="music_volume", description="Изменить громкость")
    @app_commands.describe(value="Громкость от 1 до 150")
    @app_commands.guild_only()
    async def music_volume(self, interaction: discord.Interaction, value: app_commands.Range[int, 1, 150]) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=False)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        await player.set_volume(value)
        await self._respond_safe(interaction, volume_line(value))

    @app_commands.command(name="music_leave", description="Вывести Еву из голосового канала")
    @app_commands.guild_only()
    async def music_leave(self, interaction: discord.Interaction) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=False)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        guild_id = interaction.guild_id or 0
        player.queue.clear()
        await player.disconnect()
        self.music.clear_home_channel(guild_id)
        await self._respond_safe(interaction, leave_line())

    @app_commands.command(name="music_shuffle", description="Перемешать очередь")
    @app_commands.guild_only()
    async def music_shuffle(self, interaction: discord.Interaction) -> None:
        try:
            await self._ensure_music_ready(interaction)
            player = await self.music.ensure_player(interaction, connect_if_missing=False)
        except MusicCommandError as error:
            await self._respond_safe(interaction, str(error), ephemeral=True)
            return

        if len(player.queue) == 0:
            await self._respond_safe(interaction, "Там нечего мешать, очередь пустая.", ephemeral=True)
            return
        player.queue.shuffle()
        await self._respond_safe(interaction, shuffle_line())

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        await self.music.announce_track_start(self.bot, payload)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        await self.music.handle_track_end(self.bot, payload)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload) -> None:
        await self.music.announce_track_exception(self.bot, payload)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player) -> None:
        await self.music.handle_inactive_player(self.bot, player)

    async def _respond_safe(
        self,
        interaction: discord.Interaction,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        ephemeral: bool = False,
    ) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
            return
        await interaction.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
