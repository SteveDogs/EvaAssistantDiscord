"""
EVA Assistant Steam profile watch service.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import random
import re
from typing import TYPE_CHECKING, Any

import discord

from roseblade_bot import EMBED_FOOTER
from roseblade_bot.config import BotConfig, SteamProfileWatchTarget
from roseblade_bot.services.http import HttpRequestError, fetch_json

if TYPE_CHECKING:
    from roseblade_bot.cogs.shared import EvaSharedCog


STEAM_WEB_API_BASE = "https://api.steampowered.com"
_ADDRESS_RE = re.compile(r"^\s*(ева|eva)\b", re.IGNORECASE)
_STEAMID_RE = re.compile(r"\b7656119\d{10}\b")
_QUESTION_HINTS = (
    "что там",
    "как там",
    "глянь",
    "посмотри",
    "проверь",
    "check",
    "steam",
    "стим",
    "профил",
)
_SUMMARY_TITLES = (
    "🫖 Что там у профиля в Steam",
    "🎮 Steam-срез по профилю",
    "📡 Ева сходила в Steam и вернулась",
)
_SUMMARY_LINES = (
    "Собрала короткую сводку без воды. Почти без воды.",
    "Заглянула в профиль и принесла всё интересное, что Steam сейчас отдаёт.",
    "Посмотрела профиль спокойно и внимательно. Вот что там живёт прямо сейчас.",
)
_CHANGE_LINES = (
    "Я это заметила раньше, чем Steam успел сделать вид, что ничего не было.",
    "Профиль снова шевельнулся, и я это аккуратно записала.",
    "Там случился маленький движ, так что вот свежая сводка.",
)


@dataclass(frozen=True, slots=True)
class SteamRecentGame:
    appid: int
    name: str
    playtime_2weeks_minutes: int
    playtime_forever_minutes: int


@dataclass(frozen=True, slots=True)
class SteamProfileSnapshot:
    steamid: int
    persona_name: str
    profile_url: str
    avatar_url: str
    avatar_hash: str
    visibility_state: int
    persona_state: int
    current_game_name: str | None
    current_game_appid: int | None
    last_logoff: int | None
    steam_level: int | None
    owned_game_count: int | None
    recent_games: tuple[SteamRecentGame, ...]
    community_banned: bool
    vac_banned: bool
    vac_ban_count: int
    game_ban_count: int
    economy_ban: str


class SteamProfileWatchService:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self._user_cooldowns: dict[tuple[int, int], datetime] = {}

    @property
    def is_enabled(self) -> bool:
        return self.config.steam_profile_watch.enabled

    @property
    def is_configured(self) -> bool:
        return (
            self.is_enabled
            and bool(self.config.steam_profile_watch.api_key)
            and bool(self.config.steam_profile_watch.channel_ids)
            and bool(self.config.steam_profile_watch.targets)
        )

    def channel_count(self) -> int:
        return len(self.config.steam_profile_watch.channel_ids)

    def target_count(self) -> int:
        return len(self.config.steam_profile_watch.targets)

    def allowed_role_count(self) -> int:
        return len(self.config.steam_profile_watch.allowed_role_ids)

    def target_labels(self) -> list[str]:
        labels: list[str] = []
        for target in self.config.steam_profile_watch.targets:
            labels.append(target.aliases[0] if target.aliases else str(target.steamid))
        return labels

    def is_enabled_for_channel(self, channel_id: int) -> bool:
        return self.is_enabled and channel_id in self.config.steam_profile_watch.channel_ids

    def member_has_access(self, member: discord.Member) -> bool:
        if member.id == member.guild.owner_id:
            return True
        allowed_role_ids = self.config.steam_profile_watch.allowed_role_ids
        if not allowed_role_ids:
            return True
        return any(role.id in allowed_role_ids for role in member.roles if not role.is_default())

    @staticmethod
    def _normalize_text(value: str) -> str:
        lowered = value.casefold().replace("ё", "е")
        return " ".join(lowered.split())

    def _looks_like_request(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not _ADDRESS_RE.search(normalized):
            return False
        return any(hint in normalized for hint in _QUESTION_HINTS)

    def resolve_target(self, text: str) -> SteamProfileWatchTarget | None:
        normalized = self._normalize_text(text)
        steamid_match = _STEAMID_RE.search(normalized)
        if steamid_match is not None:
            steamid = int(steamid_match.group(0))
            for target in self.config.steam_profile_watch.targets:
                if target.steamid == steamid:
                    return target

        best: tuple[int, SteamProfileWatchTarget] | None = None
        for target in self.config.steam_profile_watch.targets:
            for alias in target.aliases:
                normalized_alias = self._normalize_text(alias)
                if not normalized_alias or normalized_alias not in normalized:
                    continue
                weight = len(normalized_alias)
                if best is None or weight > best[0]:
                    best = (weight, target)
        if best is not None:
            return best[1]

        if len(self.config.steam_profile_watch.targets) == 1 and self._looks_like_request(text):
            return self.config.steam_profile_watch.targets[0]
        return None

    def is_user_on_cooldown(self, guild_id: int, user_id: int) -> int | None:
        cooldown_seconds = self.config.steam_profile_watch.user_cooldown_seconds
        if cooldown_seconds <= 0:
            return None
        stamp = self._user_cooldowns.get((guild_id, user_id))
        if stamp is None:
            return None
        delta = discord.utils.utcnow() - stamp
        if delta >= timedelta(seconds=cooldown_seconds):
            return None
        return max(cooldown_seconds - int(delta.total_seconds()), 1)

    def remember_user_request(self, guild_id: int, user_id: int) -> None:
        self._user_cooldowns[(guild_id, user_id)] = discord.utils.utcnow()

    async def _fetch_summary(self, steamid: int) -> dict[str, Any]:
        payload, _ = await fetch_json(
            f"{STEAM_WEB_API_BASE}/ISteamUser/GetPlayerSummaries/v2/",
            params={
                "key": self.config.steam_profile_watch.api_key,
                "steamids": str(steamid),
            },
            headers={"User-Agent": "EVA Assistant / Steam profile watch"},
            timeout_total=20,
        )
        players = payload.get("response", {}).get("players", []) if isinstance(payload, dict) else []
        if not players:
            raise RuntimeError(f"Steam не вернул профиль для {steamid}.")
        return players[0]

    async def _fetch_bans(self, steamid: int) -> dict[str, Any]:
        payload, _ = await fetch_json(
            f"{STEAM_WEB_API_BASE}/ISteamUser/GetPlayerBans/v1/",
            params={
                "key": self.config.steam_profile_watch.api_key,
                "steamids": str(steamid),
            },
            headers={"User-Agent": "EVA Assistant / Steam profile watch"},
            timeout_total=20,
        )
        players = payload.get("players", []) if isinstance(payload, dict) else []
        return players[0] if players else {}

    async def _fetch_optional_recent_games(self, steamid: int) -> tuple[SteamRecentGame, ...]:
        try:
            payload, _ = await fetch_json(
                f"{STEAM_WEB_API_BASE}/IPlayerService/GetRecentlyPlayedGames/v1/",
                params={
                    "key": self.config.steam_profile_watch.api_key,
                    "steamid": str(steamid),
                    "count": 3,
                },
                headers={"User-Agent": "EVA Assistant / Steam profile watch"},
                timeout_total=20,
            )
        except HttpRequestError as error:
            if error.status in {401, 403}:
                return ()
            raise

        raw_games = payload.get("response", {}).get("games", []) if isinstance(payload, dict) else []
        games: list[SteamRecentGame] = []
        for raw in raw_games[:3]:
            games.append(
                SteamRecentGame(
                    appid=int(raw.get("appid") or 0),
                    name=str(raw.get("name") or f"App {int(raw.get('appid') or 0)}").strip(),
                    playtime_2weeks_minutes=int(raw.get("playtime_2weeks") or 0),
                    playtime_forever_minutes=int(raw.get("playtime_forever") or 0),
                )
            )
        return tuple(games)

    async def _fetch_optional_owned_game_count(self, steamid: int) -> int | None:
        try:
            payload, _ = await fetch_json(
                f"{STEAM_WEB_API_BASE}/IPlayerService/GetOwnedGames/v1/",
                params={
                    "key": self.config.steam_profile_watch.api_key,
                    "steamid": str(steamid),
                    "include_appinfo": 0,
                    "include_played_free_games": 1,
                },
                headers={"User-Agent": "EVA Assistant / Steam profile watch"},
                timeout_total=20,
            )
        except HttpRequestError as error:
            if error.status in {401, 403}:
                return None
            raise
        response = payload.get("response", {}) if isinstance(payload, dict) else {}
        if not isinstance(response, dict):
            return None
        game_count = response.get("game_count")
        if game_count is None:
            return None
        return int(game_count)

    async def _fetch_optional_steam_level(self, steamid: int) -> int | None:
        try:
            payload, _ = await fetch_json(
                f"{STEAM_WEB_API_BASE}/IPlayerService/GetSteamLevel/v1/",
                params={
                    "key": self.config.steam_profile_watch.api_key,
                    "steamid": str(steamid),
                },
                headers={"User-Agent": "EVA Assistant / Steam profile watch"},
                timeout_total=20,
            )
        except HttpRequestError as error:
            if error.status in {401, 403}:
                return None
            raise
        response = payload.get("response", {}) if isinstance(payload, dict) else {}
        if not isinstance(response, dict):
            return None
        player_level = response.get("player_level")
        return int(player_level) if player_level is not None else None

    async def fetch_profile_snapshot(self, steamid: int) -> SteamProfileSnapshot:
        summary = await self._fetch_summary(steamid)
        bans, recent_games, owned_game_count, steam_level = await asyncio.gather(
            self._fetch_bans(steamid),
            self._fetch_optional_recent_games(steamid),
            self._fetch_optional_owned_game_count(steamid),
            self._fetch_optional_steam_level(steamid),
        )

        avatar_url = str(summary.get("avatarfull") or summary.get("avatarmedium") or summary.get("avatar") or "").strip()
        avatar_hash = avatar_url.rsplit("/", 1)[-1] if avatar_url else ""
        current_game_name_raw = str(summary.get("gameextrainfo") or "").strip()
        current_game_name = current_game_name_raw or None
        current_game_appid_raw = summary.get("gameid")
        current_game_appid = int(current_game_appid_raw) if current_game_appid_raw not in (None, "") else None

        return SteamProfileSnapshot(
            steamid=steamid,
            persona_name=str(summary.get("personaname") or str(steamid)).strip(),
            profile_url=str(summary.get("profileurl") or f"https://steamcommunity.com/profiles/{steamid}/").strip(),
            avatar_url=avatar_url,
            avatar_hash=avatar_hash,
            visibility_state=int(summary.get("communityvisibilitystate") or 0),
            persona_state=int(summary.get("personastate") or 0),
            current_game_name=current_game_name,
            current_game_appid=current_game_appid,
            last_logoff=int(summary.get("lastlogoff")) if summary.get("lastlogoff") is not None else None,
            steam_level=steam_level,
            owned_game_count=owned_game_count,
            recent_games=recent_games,
            community_banned=bool(bans.get("CommunityBanned", False)),
            vac_banned=bool(bans.get("VACBanned", False)),
            vac_ban_count=int(bans.get("NumberOfVACBans") or 0),
            game_ban_count=int(bans.get("NumberOfGameBans") or 0),
            economy_ban=str(bans.get("EconomyBan") or "none").strip().lower() or "none",
        )

    async def fetch_all_snapshots(self) -> tuple[SteamProfileSnapshot, ...]:
        snapshots = await asyncio.gather(
            *(self.fetch_profile_snapshot(target.steamid) for target in self.config.steam_profile_watch.targets)
        )
        return tuple(snapshots)

    @staticmethod
    def snapshot_to_state(snapshot: SteamProfileSnapshot) -> dict[str, Any]:
        return {
            "steamid": snapshot.steamid,
            "persona_name": snapshot.persona_name,
            "profile_url": snapshot.profile_url,
            "avatar_url": snapshot.avatar_url,
            "avatar_hash": snapshot.avatar_hash,
            "visibility_state": snapshot.visibility_state,
            "persona_state": snapshot.persona_state,
            "current_game_name": snapshot.current_game_name,
            "current_game_appid": snapshot.current_game_appid,
            "last_logoff": snapshot.last_logoff,
            "steam_level": snapshot.steam_level,
            "owned_game_count": snapshot.owned_game_count,
            "recent_games": [
                {
                    "appid": game.appid,
                    "name": game.name,
                    "playtime_2weeks_minutes": game.playtime_2weeks_minutes,
                    "playtime_forever_minutes": game.playtime_forever_minutes,
                }
                for game in snapshot.recent_games
            ],
            "community_banned": snapshot.community_banned,
            "vac_banned": snapshot.vac_banned,
            "vac_ban_count": snapshot.vac_ban_count,
            "game_ban_count": snapshot.game_ban_count,
            "economy_ban": snapshot.economy_ban,
        }

    @staticmethod
    def snapshot_from_state(payload: Any) -> SteamProfileSnapshot | None:
        if not isinstance(payload, dict):
            return None
        raw_recent_games = payload.get("recent_games", [])
        recent_games: list[SteamRecentGame] = []
        if isinstance(raw_recent_games, list):
            for raw in raw_recent_games:
                if not isinstance(raw, dict):
                    continue
                recent_games.append(
                    SteamRecentGame(
                        appid=int(raw.get("appid") or 0),
                        name=str(raw.get("name") or "Unknown App").strip(),
                        playtime_2weeks_minutes=int(raw.get("playtime_2weeks_minutes") or 0),
                        playtime_forever_minutes=int(raw.get("playtime_forever_minutes") or 0),
                    )
                )
        return SteamProfileSnapshot(
            steamid=int(payload.get("steamid") or 0),
            persona_name=str(payload.get("persona_name") or "").strip(),
            profile_url=str(payload.get("profile_url") or "").strip(),
            avatar_url=str(payload.get("avatar_url") or "").strip(),
            avatar_hash=str(payload.get("avatar_hash") or "").strip(),
            visibility_state=int(payload.get("visibility_state") or 0),
            persona_state=int(payload.get("persona_state") or 0),
            current_game_name=str(payload.get("current_game_name")).strip() if payload.get("current_game_name") else None,
            current_game_appid=int(payload.get("current_game_appid")) if payload.get("current_game_appid") is not None else None,
            last_logoff=int(payload.get("last_logoff")) if payload.get("last_logoff") is not None else None,
            steam_level=int(payload.get("steam_level")) if payload.get("steam_level") is not None else None,
            owned_game_count=int(payload.get("owned_game_count")) if payload.get("owned_game_count") is not None else None,
            recent_games=tuple(recent_games),
            community_banned=bool(payload.get("community_banned", False)),
            vac_banned=bool(payload.get("vac_banned", False)),
            vac_ban_count=int(payload.get("vac_ban_count") or 0),
            game_ban_count=int(payload.get("game_ban_count") or 0),
            economy_ban=str(payload.get("economy_ban") or "none").strip().lower() or "none",
        )

    @staticmethod
    def _persona_state_label(snapshot: SteamProfileSnapshot) -> str:
        if snapshot.current_game_name:
            return f"в игре: {snapshot.current_game_name}"
        labels = {
            0: "offline",
            1: "online",
            2: "busy",
            3: "away",
            4: "snooze",
            5: "looking to trade",
            6: "looking to play",
        }
        return labels.get(snapshot.persona_state, f"state {snapshot.persona_state}")

    @staticmethod
    def _visibility_label(visibility_state: int) -> str:
        if visibility_state >= 3:
            return "публичный"
        if visibility_state == 2:
            return "ограниченный"
        if visibility_state == 1:
            return "закрытый"
        return "неизвестно"

    @staticmethod
    def _format_minutes(minutes: int) -> str:
        hours = minutes / 60
        if hours >= 10:
            return f"{hours:.0f} ч"
        if hours >= 1:
            return f"{hours:.1f} ч"
        return f"{minutes} мин"

    @classmethod
    def _recent_games_value(cls, snapshot: SteamProfileSnapshot) -> str:
        if not snapshot.recent_games:
            return "Тишина или Steam не отдал список недавних игр."
        lines = []
        for game in snapshot.recent_games[:3]:
            lines.append(
                f"**{discord.utils.escape_markdown(game.name)}**"
                f" — {cls._format_minutes(game.playtime_2weeks_minutes)} за 2 недели"
            )
        return "\n".join(lines)

    @staticmethod
    def _ban_value(snapshot: SteamProfileSnapshot) -> str:
        lines = [
            f"VAC: **{'да' if snapshot.vac_banned else 'нет'}** ({snapshot.vac_ban_count})",
            f"Game bans: **{snapshot.game_ban_count}**",
            f"Community ban: **{'да' if snapshot.community_banned else 'нет'}**",
            f"Economy: **{snapshot.economy_ban or 'none'}**",
        ]
        return "\n".join(lines)

    @classmethod
    def _summary_color(cls, snapshot: SteamProfileSnapshot) -> discord.Colour:
        if snapshot.vac_banned or snapshot.community_banned or snapshot.game_ban_count > 0:
            return discord.Colour.red()
        if snapshot.current_game_name:
            return discord.Colour.green()
        if snapshot.persona_state == 0:
            return discord.Colour.light_grey()
        return discord.Colour.blurple()

    def render_summary_embed(
        self,
        snapshot: SteamProfileSnapshot,
        *,
        target: SteamProfileWatchTarget | None = None,
    ) -> discord.Embed:
        title = random.choice(_SUMMARY_TITLES)
        embed = discord.Embed(
            title=title,
            description=random.choice(_SUMMARY_LINES),
            colour=self._summary_color(snapshot),
            url=snapshot.profile_url,
        )
        embed.add_field(name="Игрок", value=f"**{discord.utils.escape_markdown(snapshot.persona_name)}**", inline=True)
        embed.add_field(name="Статус", value=self._persona_state_label(snapshot), inline=True)
        embed.add_field(name="Видимость", value=self._visibility_label(snapshot.visibility_state), inline=True)
        embed.add_field(
            name="Steam level",
            value=str(snapshot.steam_level) if snapshot.steam_level is not None else "скрыт или не отдался",
            inline=True,
        )
        embed.add_field(
            name="Библиотека",
            value=(f"{snapshot.owned_game_count} игр" if snapshot.owned_game_count is not None else "скрыта"),
            inline=True,
        )
        embed.add_field(name="Баны", value=self._ban_value(snapshot), inline=False)
        embed.add_field(name="Недавние игры", value=self._recent_games_value(snapshot), inline=False)
        if snapshot.last_logoff is not None:
            embed.add_field(
                name="Последний выход",
                value=discord.utils.format_dt(datetime.fromtimestamp(snapshot.last_logoff, tz=discord.utils.utcnow().tzinfo), style="R"),
                inline=False,
            )
        if target is not None and target.aliases:
            embed.add_field(name="Как ты просил звать", value=", ".join(f"`{alias}`" for alias in target.aliases[:5]), inline=False)
        if snapshot.avatar_url:
            embed.set_thumbnail(url=snapshot.avatar_url)
        embed.set_footer(text=f"{EMBED_FOOTER} • Steam profile watch")
        return embed

    def describe_changes(self, previous: SteamProfileSnapshot, current: SteamProfileSnapshot) -> list[str]:
        changes: list[str] = []
        config = self.config.steam_profile_watch

        if config.announce_name_changes and previous.persona_name != current.persona_name:
            changes.append(
                f"Ник сменился: **{discord.utils.escape_markdown(previous.persona_name)}** → "
                f"**{discord.utils.escape_markdown(current.persona_name)}**"
            )

        if config.announce_avatar_changes and previous.avatar_hash != current.avatar_hash:
            changes.append("Аватарка обновилась. Профиль снова решил нарядиться.")

        if previous.visibility_state != current.visibility_state:
            changes.append(
                f"Видимость профиля: **{self._visibility_label(previous.visibility_state)}** → "
                f"**{self._visibility_label(current.visibility_state)}**"
            )

        if config.announce_game_changes and previous.current_game_name != current.current_game_name:
            if previous.current_game_name and current.current_game_name:
                changes.append(
                    f"Сменил игру: **{discord.utils.escape_markdown(previous.current_game_name)}** → "
                    f"**{discord.utils.escape_markdown(current.current_game_name)}**"
                )
            elif current.current_game_name:
                changes.append(f"Залетел в **{discord.utils.escape_markdown(current.current_game_name)}**.")
            elif previous.current_game_name:
                changes.append(f"Вышел из **{discord.utils.escape_markdown(previous.current_game_name)}**.")

        if config.announce_level_changes:
            if previous.steam_level is not None and current.steam_level is not None and previous.steam_level != current.steam_level:
                changes.append(f"Steam level: **{previous.steam_level}** → **{current.steam_level}**")

        if config.announce_ban_changes:
            before_ban_signature = (
                previous.community_banned,
                previous.vac_banned,
                previous.vac_ban_count,
                previous.game_ban_count,
                previous.economy_ban,
            )
            after_ban_signature = (
                current.community_banned,
                current.vac_banned,
                current.vac_ban_count,
                current.game_ban_count,
                current.economy_ban,
            )
            if before_ban_signature != after_ban_signature:
                changes.append("Бан-статус изменился. Тут уже без шуток, Steam что-то пересчитал.")

        if config.announce_library_changes:
            if (
                previous.owned_game_count is not None
                and current.owned_game_count is not None
                and previous.owned_game_count != current.owned_game_count
            ):
                changes.append(
                    f"Библиотека изменилась: **{previous.owned_game_count}** → **{current.owned_game_count}** игр"
                )

        return changes

    def render_change_embed(
        self,
        previous: SteamProfileSnapshot,
        current: SteamProfileSnapshot,
        *,
        changes: list[str],
    ) -> discord.Embed:
        persona_name = discord.utils.escape_markdown(current.persona_name)
        embed = discord.Embed(
            title=f"🎮 У {persona_name} в Steam что-то поменялось",
            description=random.choice(_CHANGE_LINES),
            colour=self._summary_color(current),
            url=current.profile_url,
        )
        embed.add_field(name="Что заметила", value="\n".join(f"• {line}" for line in changes), inline=False)
        embed.add_field(name="Сейчас", value=self._persona_state_label(current), inline=True)
        embed.add_field(name="Steam level", value=str(current.steam_level) if current.steam_level is not None else "скрыт", inline=True)
        embed.add_field(
            name="Библиотека",
            value=(f"{current.owned_game_count} игр" if current.owned_game_count is not None else "скрыта"),
            inline=True,
        )
        if current.avatar_url:
            embed.set_thumbnail(url=current.avatar_url)
        embed.set_footer(text=f"{EMBED_FOOTER} • Steam profile watch")
        return embed

    def build_access_denied_embed(self) -> discord.Embed:
        return discord.Embed(
            title="Стим-сплетни не для всех.",
            description="Если для этого режима заданы роли, я отвечаю только владельцу сервера и людям с нужной ролью.",
            colour=discord.Colour.orange(),
        )

    def build_missing_target_embed(self) -> discord.Embed:
        aliases = ", ".join(f"`{label}`" for label in self.target_labels()[:8]) or "`steamid`"
        return discord.Embed(
            title="Скажи, за кем следить в Steam.",
            description=f"Я жду либо один из алиасов {aliases}, либо сам `SteamID64`.",
            colour=discord.Colour.gold(),
        )

    def build_not_configured_embed(self) -> discord.Embed:
        return discord.Embed(
            title="Steam-профиль я бы посмотрела, но блок ещё не настроен.",
            description=(
                "Нужны `STEAM_PROFILE_WATCH_ENABLED=true`, хотя бы один канал в "
                "`STEAM_PROFILE_WATCH_CHANNEL_IDS`, список целей в `STEAM_PROFILE_WATCH_TARGETS` "
                "и рабочий `STEAM_API_KEY`."
            ),
            colour=discord.Colour.orange(),
        )

    def build_cooldown_embed(self, seconds: int) -> discord.Embed:
        return discord.Embed(
            title="Я ещё не остыла после прошлого захода в Steam.",
            description=f"Дай мне {seconds} сек и я снова посмотрю профиль без лишней суеты.",
            colour=discord.Colour.gold(),
        )

    def build_error_embed(self, target: SteamProfileWatchTarget, error: Exception) -> discord.Embed:
        label = target.aliases[0] if target.aliases else str(target.steamid)
        return discord.Embed(
            title=f"Steam сегодня мнётся насчёт {label}.",
            description=f"Не смогла собрать профиль: `{error}`",
            colour=discord.Colour.red(),
        )

    async def maybe_handle_message(self, cog: EvaSharedCog, message: discord.Message) -> bool:
        if message.guild is None or message.author.bot or not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return False
        if not self.is_enabled_for_channel(message.channel.id):
            return False
        if not message.content or not self._looks_like_request(message.content):
            return False

        target = self.resolve_target(message.content)
        if target is None:
            try:
                await message.reply(
                    embed=self.build_missing_target_embed(),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return True

        if not isinstance(message.author, discord.Member):
            return False
        if not self.member_has_access(message.author):
            try:
                await message.reply(
                    embed=self.build_access_denied_embed(),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return True

        if not self.is_configured:
            try:
                await message.reply(
                    embed=self.build_not_configured_embed(),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return True

        cooldown = self.is_user_on_cooldown(message.guild.id, message.author.id)
        if cooldown is not None:
            try:
                await message.reply(
                    embed=self.build_cooldown_embed(cooldown),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return True

        try:
            snapshot = await self.fetch_profile_snapshot(target.steamid)
        except Exception as error:
            try:
                await message.reply(
                    embed=self.build_error_embed(target, error),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return True

        self.remember_user_request(message.guild.id, message.author.id)
        try:
            await message.reply(
                embed=self.render_summary_embed(snapshot, target=target),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            return True
        return True
