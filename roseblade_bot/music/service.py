"""
EVA Assistant music service powered by Wavelink/Lavalink.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any
import re

import discord
from discord.ext import commands
import wavelink

from roseblade_bot.config import MusicConfig
from roseblade_bot.music.phrases import (
    inactive_disconnect_line,
    next_track_line,
    soundcloud_rescue_line,
    track_exception_line,
)

_URL_RE = re.compile(r"^(https?://|spotify:)", re.IGNORECASE)
_SPOTIFY_RE = re.compile(r"(open\.spotify\.com|spotify:)", re.IGNORECASE)
_TOPIC_SUFFIX_RE = re.compile(r"\s*-\s*topic\s*$", re.IGNORECASE)
_AUTOCOMPLETE_CACHE_TTL_SECONDS = 20.0
_AUTOCOMPLETE_CACHE_MAX = 128
_SOURCE_LABELS = {
    "youtube": "YouTube",
    "youtubemusic": "YouTube Music",
    "soundcloud": "SoundCloud",
    "spotify": "Spotify",
}
_SEARCH_SOURCE_ALIASES = {
    "ytm": "ytmsearch",
    "ytmusic": "ytmsearch",
    "ytmsearch": "ytmsearch",
    "youtube_music": "ytmsearch",
    "youtube-music": "ytmsearch",
    "yt": "ytsearch",
    "youtube": "ytsearch",
    "ytsearch": "ytsearch",
    "sp": "spsearch",
    "spotify": "spsearch",
    "spsearch": "spsearch",
    "sc": wavelink.TrackSource.SoundCloud,
    "soundcloud": wavelink.TrackSource.SoundCloud,
}


class MusicCommandError(RuntimeError):
    """Human-friendly error for slash music commands."""


@dataclass(slots=True)
class MusicEnqueueResult:
    player: wavelink.Player
    started_track: wavelink.Playable | None
    queued_count: int
    playlist_name: str | None
    playlist_size: int
    used_fallback: bool


@dataclass(slots=True, frozen=True)
class MusicAutocompleteSuggestion:
    label: str
    value: str


def _duration_label(milliseconds: int) -> str:
    if milliseconds <= 0:
        return "LIVE"
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _source_label(source: str | None) -> str:
    if not source:
        return "Источник не указан"
    normalized = source.replace(" ", "").lower()
    return _SOURCE_LABELS.get(normalized, source)


def _normalize_search_source(source: str) -> wavelink.TrackSource | str:
    normalized = source.strip().lower()
    if not normalized:
        return "ytmsearch"
    mapped = _SEARCH_SOURCE_ALIASES.get(normalized)
    if mapped is not None:
        return mapped
    return normalized.removesuffix(":")


def _track_title(track: wavelink.Playable | None) -> str:
    if track is None:
        return "Ничего не играет"
    return track.title or "Без названия"


def _truncate_text(value: str, limit: int) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 1:
        return cleaned[:limit]
    return cleaned[: limit - 1].rstrip() + "…"


def _collapse_spaces(value: str) -> str:
    return " ".join(value.split())


def _truncate_choice_text(value: str, limit: int = 100) -> str:
    cleaned = _collapse_spaces(value).strip()
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 1:
        return cleaned[:limit]
    return cleaned[: limit - 1].rstrip() + "…"


def _build_autocomplete_suggestion(track: Any) -> MusicAutocompleteSuggestion:
    title = (getattr(track, "title", None) or "Без названия").strip()
    author = (getattr(track, "author", None) or "Неизвестный артист").strip()
    length = int(getattr(track, "length", 0) or 0)
    label = _truncate_choice_text(f"{author} — {title} • {_duration_label(length)}")

    uri = (getattr(track, "uri", None) or "").strip()
    if uri and len(uri) <= 100:
        value = uri
    else:
        value = _truncate_choice_text(f"{author} - {title}")

    return MusicAutocompleteSuggestion(label=label, value=value)


def _summarize_track_exception(exception: Any) -> str:
    raw = str(exception or "").strip()
    if not raw:
        return "Источник не отдал аудио-поток."

    lowered = raw.lower()
    if "requires login" in lowered or "confirm you're not a bot" in lowered:
        return "YouTube не отдал аудио и попросил авторизацию. Похоже, источник упёрся в антибот-защиту."
    if "all clients failed to load the item" in lowered:
        return "Ни один YouTube-клиент Lavalink не смог вытащить поток для этого видео."

    first_line = raw.splitlines()[0]
    return _truncate_text(first_line, 900)


def _track_source_name(track: wavelink.Playable | None) -> str:
    return ((track.source if track is not None else None) or "").replace(" ", "").lower()


def _normalize_match_text(value: str) -> str:
    lowered = value.casefold()
    cleaned = re.sub(r"[^a-zа-яё0-9]+", " ", lowered, flags=re.IGNORECASE)
    return _collapse_spaces(cleaned)


def _build_soundcloud_search_queries(track: wavelink.Playable, original_query: str) -> list[str]:
    title = _collapse_spaces((track.title or "").strip())
    author = _collapse_spaces(_TOPIC_SUFFIX_RE.sub("", (track.author or "").strip()))

    candidates: list[str] = []
    if original_query and not _URL_RE.match(original_query):
        candidates.append(original_query)
    if author and title:
        candidates.append(f"{author} {title}")
        candidates.append(f"{author} - {title}")
    if title:
        candidates.append(title)

    deduped: list[str] = []
    seen: set[str] = set()
    for query in candidates:
        normalized = _collapse_spaces(query).strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _select_best_soundcloud_candidate(
    tracks: list[wavelink.Playable],
    *,
    target_title: str,
    target_author: str,
) -> wavelink.Playable:
    normalized_title = _normalize_match_text(target_title)
    normalized_author = _normalize_match_text(_TOPIC_SUFFIX_RE.sub("", target_author))
    title_terms = [term for term in normalized_title.split() if term]

    def score(track: wavelink.Playable) -> tuple[int, int, int]:
        track_title = _normalize_match_text(track.title or "")
        track_author = _normalize_match_text(track.author or "")

        title_exact = int(track_title == normalized_title and bool(normalized_title))
        title_contains = int(normalized_title in track_title and bool(normalized_title))
        author_contains = int(normalized_author in track_author and bool(normalized_author))
        term_hits = sum(1 for term in title_terms if term in track_title)
        return (title_exact * 100 + title_contains * 20 + author_contains * 10 + term_hits, title_contains, author_contains)

    return max(tracks, key=score)


def _score_soundcloud_candidate(
    track: wavelink.Playable,
    *,
    target_title: str,
    target_author: str,
) -> tuple[int, int, int]:
    normalized_title = _normalize_match_text(target_title)
    normalized_author = _normalize_match_text(_TOPIC_SUFFIX_RE.sub("", target_author))
    title_terms = [term for term in normalized_title.split() if term]

    track_title = _normalize_match_text(track.title or "")
    track_author = _normalize_match_text(track.author or "")

    title_exact = int(track_title == normalized_title and bool(normalized_title))
    title_contains = int(normalized_title in track_title and bool(normalized_title))
    author_contains = int(normalized_author in track_author and bool(normalized_author))
    term_hits = sum(1 for term in title_terms if term in track_title)
    return (title_exact * 100 + title_contains * 20 + author_contains * 10 + term_hits, title_contains, author_contains)


class MusicService:
    def __init__(self, config: MusicConfig) -> None:
        self.config = config
        self._startup_error: str | None = None
        self._home_text_channels: dict[int, int] = {}
        self._autocomplete_cache: dict[str, tuple[float, list[MusicAutocompleteSuggestion]]] = {}

    @property
    def is_enabled(self) -> bool:
        return self.config.enabled

    @property
    def startup_error(self) -> str | None:
        return self._startup_error

    @property
    def spotify_links_expected(self) -> bool:
        return bool(self.config.spotify_client_id and self.config.spotify_client_secret)

    @property
    def lavalink_ready(self) -> bool:
        if not self.config.enabled:
            return False
        node = self.get_node()
        return node is not None and node.status is wavelink.NodeStatus.CONNECTED

    def get_node(self) -> wavelink.Node | None:
        try:
            return wavelink.Pool.get_node(self.config.node_identifier)
        except Exception:
            nodes = list(wavelink.Pool.nodes.values())
            return nodes[0] if nodes else None

    async def startup(self, bot: commands.Bot) -> None:
        if not self.config.enabled:
            self._startup_error = None
            return

        node = self.get_node()
        if node is not None and node.status is wavelink.NodeStatus.CONNECTED:
            self._startup_error = None
            return

        if wavelink.Pool.nodes:
            try:
                await wavelink.Pool.reconnect()
            except Exception as error:
                self._startup_error = str(error)
            else:
                node = self.get_node()
                if node is not None and node.status is wavelink.NodeStatus.CONNECTED:
                    self._startup_error = None
                    return

        try:
            await wavelink.Pool.connect(
                nodes=[
                    wavelink.Node(
                        identifier=self.config.node_identifier,
                        uri=self.config.lavalink_uri,
                        password=self.config.lavalink_password,
                        inactive_player_timeout=self.config.inactive_timeout_seconds,
                    )
                ],
                client=bot,
                cache_capacity=100,
            )
            self._startup_error = None
        except Exception as error:
            self._startup_error = str(error)

    async def ensure_started(self, bot: commands.Bot) -> None:
        if not self.config.enabled:
            raise MusicCommandError("Музыкальный режим сейчас выключен в конфиге Евы.")
        if self.lavalink_ready:
            return
        await self.startup(bot)
        if not self.lavalink_ready:
            detail = self._startup_error or "Lavalink пока не поднялся."
            raise MusicCommandError(f"Музыкальная нода сейчас недоступна: {detail}")

    def bind_home_channel(self, guild_id: int, channel_id: int) -> None:
        self._home_text_channels[guild_id] = channel_id

    def clear_home_channel(self, guild_id: int) -> None:
        self._home_text_channels.pop(guild_id, None)

    def get_home_channel(self, bot: commands.Bot, guild_id: int) -> discord.abc.Messageable | None:
        channel_id = self._home_text_channels.get(guild_id)
        if channel_id is None:
            return None
        channel = bot.get_channel(channel_id)
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel
        return None

    def member_is_allowed(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return True
        if not self.config.allowed_role_ids:
            return True
        return any(role.id in self.config.allowed_role_ids for role in member.roles)

    def looks_like_spotify(self, query: str) -> bool:
        return bool(_SPOTIFY_RE.search(query))

    def looks_like_url(self, query: str) -> bool:
        return bool(_URL_RE.match(query.strip()))

    async def ensure_player(
        self,
        interaction: discord.Interaction,
        *,
        connect_if_missing: bool,
    ) -> wavelink.Player:
        if interaction.guild is None:
            raise MusicCommandError("Эта команда работает только внутри сервера.")
        if not isinstance(interaction.user, discord.Member):
            raise MusicCommandError("Не смогла определить твои серверные права.")
        if not self.member_is_allowed(interaction.user):
            raise MusicCommandError("Эта музыкальная панель сейчас доступна не для всех ролей.")

        if interaction.user.voice is None or interaction.user.voice.channel is None:
            raise MusicCommandError("Сначала зайди в голосовой канал, а потом уже командуй музыку.")

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            if not connect_if_missing:
                raise MusicCommandError("Я сейчас не сижу ни в одном голосовом канале.")
            player = await voice_channel.connect(cls=wavelink.Player, self_deaf=True)
            await self.configure_player(player)
            return player

        if not isinstance(voice_client, wavelink.Player):
            raise MusicCommandError("В сервере уже висит другой voice-client, а не музыкальная нода Евы.")

        player = voice_client
        if player.channel is None:
            if connect_if_missing:
                await voice_channel.connect(cls=wavelink.Player, self_deaf=True)
                await self.configure_player(player)
                return player
            raise MusicCommandError("Музыкальный плеер сейчас не привязан к каналу.")

        if player.channel.id != voice_channel.id:
            raise MusicCommandError(
                f"Я уже играю в **{player.channel.name}**. Зайди туда же или сначала используй `/music_leave`."
            )

        await self.configure_player(player)
        return player

    async def configure_player(self, player: wavelink.Player) -> None:
        player.autoplay = wavelink.AutoPlayMode.disabled
        player.inactive_timeout = self.config.inactive_timeout_seconds
        if player.volume != self.config.default_volume:
            await player.set_volume(self.config.default_volume)

    async def search(self, query: str) -> tuple[wavelink.Search, bool]:
        cleaned = query.strip()
        if not cleaned:
            raise MusicCommandError("Пустой запрос я играть не умею. Дай ссылку или название трека.")

        if self.looks_like_spotify(cleaned) and not self.spotify_links_expected:
            raise MusicCommandError(
                "Spotify-ссылки я уже понимаю по архитектуре, но mirror для них ещё не включён на ноде. "
                "Нужны `MUSIC_SPOTIFY_CLIENT_ID` и `MUSIC_SPOTIFY_CLIENT_SECRET`."
            )

        source = None if self.looks_like_url(cleaned) else _normalize_search_source(self.config.default_search_source)
        result = await wavelink.Playable.search(cleaned, source=source)
        if result or self.looks_like_url(cleaned):
            return result, False

        fallback = _normalize_search_source(self.config.fallback_search_source)
        if fallback == source:
            return result, False
        fallback_result = await wavelink.Playable.search(cleaned, source=fallback)
        return fallback_result, True

    async def autocomplete_query(self, query: str, *, limit: int = 10) -> list[MusicAutocompleteSuggestion]:
        cleaned = _collapse_spaces(query).strip()
        if len(cleaned) < 2 or self.looks_like_url(cleaned):
            return []

        cache_key = cleaned.casefold()
        cached = self._autocomplete_cache.get(cache_key)
        now = monotonic()
        if cached is not None:
            cached_at, suggestions = cached
            if now - cached_at <= _AUTOCOMPLETE_CACHE_TTL_SECONDS:
                return suggestions[:limit]
            self._autocomplete_cache.pop(cache_key, None)

        result, _used_fallback = await self.search(cleaned)
        if not result:
            return []

        if isinstance(result, wavelink.Playlist):
            iterable = result.tracks
        else:
            iterable = result

        suggestions: list[MusicAutocompleteSuggestion] = []
        seen_values: set[str] = set()
        for track in iterable:
            suggestion = _build_autocomplete_suggestion(track)
            if not suggestion.value or suggestion.value in seen_values:
                continue
            seen_values.add(suggestion.value)
            suggestions.append(suggestion)
            if len(suggestions) >= limit:
                break

        if len(self._autocomplete_cache) >= _AUTOCOMPLETE_CACHE_MAX:
            oldest_key = min(self._autocomplete_cache.items(), key=lambda item: item[1][0])[0]
            self._autocomplete_cache.pop(oldest_key, None)
        self._autocomplete_cache[cache_key] = (now, suggestions)
        return suggestions

    async def enqueue_query(
        self,
        interaction: discord.Interaction,
        query: str,
    ) -> MusicEnqueueResult:
        assert interaction.guild is not None
        assert isinstance(interaction.user, discord.Member)

        player = await self.ensure_player(interaction, connect_if_missing=True)
        self.bind_home_channel(interaction.guild.id, interaction.channel_id)
        cleaned_query = query.strip()
        result, used_fallback = await self.search(cleaned_query)
        requested_via_url = self.looks_like_url(cleaned_query)

        if not result:
            raise MusicCommandError("Ничего не нашла. Попробуй ссылку, нормальное название или запрос покороче.")

        if isinstance(result, wavelink.Playlist):
            tracks = list(result.tracks)
            playlist_name = result.name
        else:
            tracks = list(result)
            playlist_name = None

        if not requested_via_url and tracks:
            tracks = [tracks[0]]
            playlist_name = None

        if not tracks:
            raise MusicCommandError("По этому запросу мне реально нечего ставить в очередь.")

        requester_payload = {
            "requester_id": interaction.user.id,
            "requester_name": interaction.user.display_name,
            "requester_mention": interaction.user.mention,
            "original_query": cleaned_query,
            "soundcloud_retry_attempted": False,
            "fallback_attempts": 0,
            "fallback_target_title": "",
            "fallback_target_author": "",
            "fallback_tried_uris": [],
        }
        for track in tracks:
            payload = dict(requester_payload)
            payload["skip_announce_once"] = False
            payload["fallback_target_title"] = track.title or ""
            payload["fallback_target_author"] = track.author or ""
            track.extras = payload

        started_track: wavelink.Playable | None = None
        queued_count = len(tracks)
        idle = not player.playing and player.current is None

        if idle:
            started_track = tracks[0]
            started_track.extras = {**dict(started_track.extras), "skip_announce_once": True}
            if len(tracks) > 1:
                await player.queue.put_wait(tracks[1:])
            await player.play(started_track, volume=player.volume or self.config.default_volume)
        else:
            await player.queue.put_wait(tracks)

        return MusicEnqueueResult(
            player=player,
            started_track=started_track,
            queued_count=queued_count,
            playlist_name=playlist_name,
            playlist_size=len(tracks),
            used_fallback=used_fallback,
        )

    def build_track_embed(
        self,
        *,
        title: str,
        description: str,
        track: wavelink.Playable,
        color: discord.Colour | None = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            colour=color or discord.Colour.from_rgb(233, 115, 150),
        )
        embed.add_field(name="Трек", value=track.title or "Без названия", inline=False)
        embed.add_field(name="Автор", value=track.author or "Неизвестно", inline=True)
        embed.add_field(name="Длительность", value=_duration_label(track.length), inline=True)
        embed.add_field(name="Источник", value=_source_label(track.source), inline=True)

        requester = dict(track.extras).get("requester_mention") if track.extras else None
        if requester:
            embed.add_field(name="Поставил", value=str(requester), inline=True)
        if track.uri:
            embed.add_field(name="Ссылка", value=f"[Открыть трек]({track.uri})", inline=True)
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        embed.set_footer(text="EVA Assistant • music mode")
        return embed

    def build_queue_embed(self, player: wavelink.Player) -> discord.Embed:
        embed = discord.Embed(
            title="Очередь EVA",
            colour=discord.Colour.from_rgb(214, 160, 122),
        )
        current = player.current
        if current is not None:
            embed.add_field(
                name="Сейчас играет",
                value=f"**{current.title}** • {_duration_label(current.length)} • {_source_label(current.source)}",
                inline=False,
            )

        upcoming = list(player.queue[:10])
        if upcoming:
            lines = [
                f"`{index}.` **{track.title}** • {_duration_label(track.length)}"
                for index, track in enumerate(upcoming, start=1)
            ]
            embed.add_field(name="Дальше по списку", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Дальше по списку", value="Очередь пустая.", inline=False)

        embed.add_field(name="Громкость", value=f"{player.volume}%", inline=True)
        embed.add_field(name="Loop", value=player.queue.mode.name, inline=True)
        embed.add_field(name="Автоподхват", value=player.autoplay.name, inline=True)
        embed.set_footer(text="EVA Assistant • не ссорьтесь из-за очереди")
        return embed

    def build_status_embed(self) -> discord.Embed:
        node = self.get_node()
        ready = node is not None and node.status is wavelink.NodeStatus.CONNECTED
        embed = discord.Embed(
            title="Музыкальный статус EVA",
            colour=discord.Colour.from_rgb(128, 208, 201) if ready else discord.Colour.from_rgb(240, 138, 138),
        )
        embed.add_field(name="Music mode", value="включён" if self.config.enabled else "выключен", inline=True)
        embed.add_field(name="Lavalink", value="подключена" if ready else "не готова", inline=True)
        embed.add_field(name="URI", value=self.config.lavalink_uri, inline=False)
        embed.add_field(name="Поиск по умолчанию", value=self.config.default_search_source, inline=True)
        embed.add_field(name="Fallback", value=self.config.fallback_search_source, inline=True)
        embed.add_field(
            name="Spotify mirror",
            value="готов к настройке" if self.spotify_links_expected else "нужны client id / secret",
            inline=True,
        )
        if self._startup_error:
            embed.add_field(name="Последняя ошибка", value=self._startup_error[:1000], inline=False)
        embed.set_footer(text="EVA Assistant • Steve Dogs Studio")
        return embed

    async def announce_track_start(self, bot: commands.Bot, payload: wavelink.TrackStartEventPayload) -> None:
        if payload.player is None or payload.player.guild is None:
            return

        track = payload.track
        extras = dict(track.extras) if track.extras else {}
        if extras.get("skip_announce_once"):
            track.extras = {**extras, "skip_announce_once": False}
            return

        channel = self.get_home_channel(bot, payload.player.guild.id)
        if channel is None:
            return

        embed = self.build_track_embed(
            title="🎵 Поехали дальше",
            description=next_track_line(track.title or "безымянный трек"),
            track=track,
            color=discord.Colour.from_rgb(126, 198, 255),
        )
        await channel.send(embed=embed)

    async def _play_next_queued_track(self, player: wavelink.Player) -> wavelink.Playable | None:
        try:
            next_track = player.queue.get()
        except wavelink.QueueEmpty:
            return None

        await player.play(next_track, volume=player.volume or self.config.default_volume)
        return next_track

    async def handle_track_end(self, bot: commands.Bot, payload: wavelink.TrackEndEventPayload) -> None:
        if payload.player is None or payload.player.guild is None:
            return
        if payload.reason in {"replaced", "cleanup"}:
            return
        if payload.player.current is not None:
            return

        await self._play_next_queued_track(payload.player)

    async def _try_soundcloud_rescue(
        self,
        bot: commands.Bot,
        payload: wavelink.TrackExceptionEventPayload,
    ) -> bool:
        if payload.player is None or payload.player.guild is None or payload.track is None:
            return False

        source_name = _track_source_name(payload.track)
        if source_name not in {"youtube", "youtubemusic", "soundcloud"}:
            return False

        extras = dict(payload.track.extras) if payload.track.extras else {}
        attempts = int(extras.get("fallback_attempts", 0) or 0)
        if attempts >= 4:
            return False

        original_query = str(extras.get("original_query") or "").strip()
        target_title = str(extras.get("fallback_target_title") or payload.track.title or "").strip()
        target_author = str(extras.get("fallback_target_author") or payload.track.author or "").strip()
        tried_uris_raw = extras.get("fallback_tried_uris") or []
        tried_uris = {str(item) for item in tried_uris_raw if item}
        if payload.track.uri:
            tried_uris.add(str(payload.track.uri))

        rescue_track: wavelink.Playable | None = None
        selected_query = original_query
        for query in _build_soundcloud_search_queries(payload.track, original_query):
            try:
                result = await wavelink.Playable.search(query, source=wavelink.TrackSource.SoundCloud)
            except Exception:
                continue
            if not result:
                continue

            if isinstance(result, wavelink.Playlist):
                candidates = list(result.tracks)
            else:
                candidates = list(result)
            if not candidates:
                continue

            filtered = [candidate for candidate in candidates[:10] if str(candidate.uri or "") not in tried_uris]
            if not filtered:
                continue

            ordered = sorted(
                filtered,
                key=lambda candidate: _score_soundcloud_candidate(
                    candidate,
                    target_title=target_title,
                    target_author=target_author,
                ),
                reverse=True,
            )
            rescue_track = ordered[0]
            selected_query = query
            break

        if rescue_track is None:
            return False

        tried_uris_updated = list(tried_uris)
        if rescue_track.uri and str(rescue_track.uri) not in tried_uris_updated:
            tried_uris_updated.append(str(rescue_track.uri))

        rescue_track.extras = {
            "requester_id": extras.get("requester_id"),
            "requester_name": extras.get("requester_name"),
            "requester_mention": extras.get("requester_mention"),
            "original_query": selected_query,
            "soundcloud_retry_attempted": True,
            "skip_announce_once": True,
            "fallback_attempts": attempts + 1,
            "fallback_target_title": target_title,
            "fallback_target_author": target_author,
            "fallback_tried_uris": tried_uris_updated,
        }

        await payload.player.play(
            rescue_track,
            replace=True,
            volume=payload.player.volume or self.config.default_volume,
        )

        channel = self.get_home_channel(bot, payload.player.guild.id)
        if channel is not None:
            embed = self.build_track_embed(
                title="🛟 Подхватила трек с SoundCloud",
                description=soundcloud_rescue_line(),
                track=rescue_track,
                color=discord.Colour.from_rgb(255, 156, 112),
            )
            await channel.send(embed=embed)
        return True

    async def announce_track_exception(self, bot: commands.Bot, payload: wavelink.TrackExceptionEventPayload) -> None:
        if payload.player is None or payload.player.guild is None:
            return
        if await self._try_soundcloud_rescue(bot, payload):
            return
        channel = self.get_home_channel(bot, payload.player.guild.id)
        if channel is None:
            await self._play_next_queued_track(payload.player)
            return

        next_track = await self._play_next_queued_track(payload.player)
        if next_track is None:
            embed = discord.Embed(
                title="⚠️ Трек развалился по дороге",
                description=track_exception_line(),
                colour=discord.Colour.from_rgb(240, 138, 138),
            )
            embed.add_field(name="Трек", value=_track_title(payload.track), inline=False)
            embed.add_field(name="Причина", value=_summarize_track_exception(payload.exception), inline=False)
            await channel.send(embed=embed)

    async def handle_inactive_player(self, bot: commands.Bot, player: wavelink.Player) -> None:
        guild = player.guild
        if guild is None:
            return
        channel = self.get_home_channel(bot, guild.id)
        self.clear_home_channel(guild.id)
        try:
            await player.disconnect()
        finally:
            if channel is not None:
                await channel.send(inactive_disconnect_line())
