"""
EVA Assistant PUBG lookup integration.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import random
import re
from typing import TYPE_CHECKING, Any
from urllib import parse

import aiohttp
import discord

from roseblade_bot import EMBED_FOOTER
from roseblade_bot.config import BotConfig
from roseblade_bot.phrases import PHRASES
from roseblade_bot.services.http import HttpRequestError, fetch_json

if TYPE_CHECKING:
    from roseblade_bot.cogs.shared import EvaSharedCog


_ADDRESS_RE = re.compile(r"^\s*(ева|eva)\b", re.IGNORECASE)
_ACTION_RE = re.compile(
    r"\b(посмотр(?:и|еть)?|глян(?:ь|уть)?|проверь|проверить|чекни|check|please|пожалуйста|можешь)\b",
    re.IGNORECASE,
)
_PUBG_HINT_RE = re.compile(r"\b(pubg|пабг|бан|ник|аккаунт|игрок|player)\b", re.IGNORECASE)
_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9._-]{2,32}")
_TARGET_PATTERNS = (
    re.compile(r"\bник\s*[:\-]?\s*(?P<nick>[A-Za-z0-9._-]{2,32})", re.IGNORECASE),
    re.compile(r"\bаккаунт\s*[:\-]?\s*(?P<nick>[A-Za-z0-9._-]{2,32})", re.IGNORECASE),
    re.compile(r"\bигрок\s*[:\-]?\s*(?P<nick>[A-Za-z0-9._-]{2,32})", re.IGNORECASE),
    re.compile(r"\bplayer\s*[:\-]?\s*(?P<nick>[A-Za-z0-9._-]{2,32})", re.IGNORECASE),
    re.compile(r"\bban\s*[:\-]?\s*(?P<nick>[A-Za-z0-9._-]{2,32})", re.IGNORECASE),
    re.compile(r"\bбан\s*[:\-]?\s*(?P<nick>[A-Za-z0-9._-]{2,32})", re.IGNORECASE),
)
_STOP_TOKENS = {
    "eva",
    "check",
    "please",
    "pubg",
    "ban",
    "player",
    "steam",
}

_CLEAN_TITLES = PHRASES.pubg_titles.get("clean", ())
_PERMABAN_TITLES = PHRASES.pubg_titles.get("permaban", ())
_TEMPBAN_TITLES = PHRASES.pubg_titles.get("tempban", ())
_NOT_FOUND_TITLES = PHRASES.pubg_titles.get("not_found", ())
_RATE_LIMIT_TITLES = PHRASES.pubg_titles.get("rate_limit", ())
_ERROR_TITLES = PHRASES.pubg_titles.get("error", ())


@dataclass(slots=True)
class PubgLifetimeSummary:
    game_mode: str
    rounds_played: int
    wins: int
    top10s: int
    kills: int
    damage_dealt: float
    time_survived: float


@dataclass(slots=True)
class PubgRankedSummary:
    game_mode: str
    current_tier: str
    current_sub_tier: str | None
    current_rank_point: int
    best_tier: str
    best_sub_tier: str | None
    best_rank_point: int
    rounds_played: int
    avg_rank: float
    win_ratio: float
    top10_ratio: float
    wins: int
    kills: int


@dataclass(slots=True)
class PubgPlayerLookup:
    name: str
    account_id: str
    shard_id: str
    clan_id: str | None
    ban_type: str | None
    recent_match_count: int
    ranked_summary: PubgRankedSummary | None
    lifetime_summary: PubgLifetimeSummary | None


@dataclass(slots=True)
class PubgLookupResult:
    ok: bool
    found: bool
    rate_limited: bool
    needs_nickname: bool
    nickname: str | None
    title: str
    description: str
    color: discord.Colour
    player: PubgPlayerLookup | None = None
    retry_after_seconds: int | None = None


@dataclass(slots=True)
class _CacheEntry:
    result: PubgLookupResult
    cached_at: datetime


class PubgLookupService:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self._cache: dict[tuple[str, str, bool, bool], _CacheEntry] = {}
        self._user_cooldowns: dict[tuple[int, int], datetime] = {}
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset_at: datetime | None = None
        self._current_season_id: str | None = None
        self._current_season_loaded_at: datetime | None = None

    @property
    def is_enabled(self) -> bool:
        return self.config.pubg.enabled

    @property
    def is_configured(self) -> bool:
        return self.is_enabled and bool(self.config.pubg.api_key) and bool(self.config.pubg.channel_ids)

    def channel_count(self) -> int:
        return len(self.config.pubg.channel_ids)

    def allowed_role_count(self) -> int:
        return len(self.config.pubg.allowed_role_ids)

    def has_steam_key(self) -> bool:
        return bool(self.config.pubg.steam_api_key)

    def is_enabled_for_channel(self, channel_id: int) -> bool:
        return self.is_enabled and channel_id in self.config.pubg.channel_ids

    def member_has_access(self, member: discord.Member) -> bool:
        if member.id == member.guild.owner_id:
            return True
        allowed_role_ids = self.config.pubg.allowed_role_ids
        if not allowed_role_ids:
            return True
        return any(role.id in allowed_role_ids for role in member.roles if not role.is_default())

    def _normalize_nickname(self, nickname: str) -> str:
        return nickname.strip().lower()

    def _pick(self, pool: tuple[str, ...]) -> str:
        return random.choice(pool)

    def _is_rate_limited_locally(self) -> tuple[bool, int | None]:
        if self._rate_limit_reset_at is None:
            return False, None
        delta = self._rate_limit_reset_at - discord.utils.utcnow()
        if delta.total_seconds() <= 0:
            self._rate_limit_reset_at = None
            self._rate_limit_remaining = None
            return False, None
        if self._rate_limit_remaining is not None and self._rate_limit_remaining > 0:
            return False, None
        return True, max(int(delta.total_seconds()), 1)

    def _remember_headers(self, headers: Any) -> None:
        remaining_raw = headers.get("X-RateLimit-Remaining")
        reset_raw = headers.get("X-RateLimit-Reset")
        try:
            self._rate_limit_remaining = int(remaining_raw) if remaining_raw is not None else None
        except (TypeError, ValueError):
            self._rate_limit_remaining = None
        try:
            reset_ts = int(reset_raw) if reset_raw is not None else None
        except (TypeError, ValueError):
            reset_ts = None
        self._rate_limit_reset_at = (
            datetime.fromtimestamp(reset_ts, tz=discord.utils.utcnow().tzinfo)
            if reset_ts is not None
            else None
        )

    def _extract_nickname(self, text: str) -> str | None:
        for pattern in _TARGET_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group("nick")

        candidates = _ASCII_TOKEN_RE.findall(text)
        for token in reversed(candidates):
            lowered = token.lower()
            if lowered in _STOP_TOKENS:
                continue
            return token
        return None

    def _is_pubg_request(self, text: str) -> bool:
        if not _ADDRESS_RE.search(text):
            return False
        if not _ACTION_RE.search(text):
            return False
        if _PUBG_HINT_RE.search(text):
            return True
        candidates = _ASCII_TOKEN_RE.findall(text)
        return any(token.lower() not in _STOP_TOKENS for token in candidates)

    def is_user_on_cooldown(self, guild_id: int, user_id: int) -> int | None:
        cooldown_seconds = self.config.pubg.user_cooldown_seconds
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

    def parse_message(self, message: discord.Message) -> str | None:
        if message.guild is None or message.author.bot:
            return None
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return None
        if not self.is_enabled_for_channel(message.channel.id):
            return None
        if not message.content or not self._is_pubg_request(message.content):
            return None
        return self._extract_nickname(message.content)

    def build_missing_nickname_result(self) -> PubgLookupResult:
        return PubgLookupResult(
            ok=False,
            found=False,
            rate_limited=False,
            needs_nickname=True,
            nickname=None,
            title="Назови ник PUBG нормально, солнце.",
            description=(
                "После обращения вроде `Ева посмотри` мне нужен сам ник, "
                "например `SteveDogs`, `S_T_E_V_E-` или `G_O_S_P_O_Z_H_A`."
            ),
            color=discord.Colour.gold(),
        )

    def build_cooldown_result(self, seconds: int) -> PubgLookupResult:
        return PubgLookupResult(
            ok=False,
            found=False,
            rate_limited=True,
            needs_nickname=False,
            nickname=None,
            title=self._pick(_RATE_LIMIT_TITLES),
            description=(
                f"Я уже бегала за этой справкой совсем недавно. "
                f"Подожди ещё **{seconds} сек**, а потом снова дёргай Еву."
            ),
            color=discord.Colour.orange(),
            retry_after_seconds=seconds,
        )

    def build_access_denied_result(self) -> PubgLookupResult:
        return PubgLookupResult(
            ok=False,
            found=False,
            rate_limited=False,
            needs_nickname=False,
            nickname=None,
            title="Сюда по пропуску, солнышко.",
            description=(
                "Эта PUBG-проверка доступна не всем подряд. "
                "Нужна одна из ролей, которые сервер выдал для этой функции."
            ),
            color=discord.Colour.dark_gold(),
        )

    async def _request_json(self, url: str) -> tuple[Any, Any]:
        return await fetch_json(
            url,
            headers={
                "Authorization": f"Bearer {self.config.pubg.api_key}",
                "Accept": "application/vnd.api+json",
                "User-Agent": "EVA-Assistant/1.0",
            },
            timeout_total=20,
        )

    def _extract_best_mode(self, payload: Any) -> PubgLifetimeSummary | None:
        game_mode_stats = payload.get("data", {}).get("attributes", {}).get("gameModeStats", {})
        best_mode_name: str | None = None
        best_mode_payload: dict[str, Any] | None = None
        best_rounds = -1
        for mode_name, mode_payload in game_mode_stats.items():
            rounds_played = int(mode_payload.get("roundsPlayed", 0) or 0)
            if rounds_played > best_rounds:
                best_rounds = rounds_played
                best_mode_name = mode_name
                best_mode_payload = mode_payload
        if best_mode_name is None or best_mode_payload is None or best_rounds <= 0:
            return None
        return PubgLifetimeSummary(
            game_mode=best_mode_name,
            rounds_played=best_rounds,
            wins=int(best_mode_payload.get("wins", 0) or 0),
            top10s=int(best_mode_payload.get("top10s", 0) or 0),
            kills=int(best_mode_payload.get("kills", 0) or 0),
            damage_dealt=float(best_mode_payload.get("damageDealt", 0) or 0),
            time_survived=float(best_mode_payload.get("timeSurvived", 0) or 0),
        )

    async def _resolve_current_season_id(self) -> str | None:
        now = discord.utils.utcnow()
        if (
            self._current_season_id is not None
            and self._current_season_loaded_at is not None
            and now - self._current_season_loaded_at <= timedelta(hours=6)
        ):
            return self._current_season_id

        payload, headers = await self._request_json(f"https://api.pubg.com/shards/{self.config.pubg.platform}/seasons")
        self._remember_headers(headers)
        seasons = payload.get("data") or []
        current = next((season for season in seasons if season.get("attributes", {}).get("isCurrentSeason")), None)
        if current is None:
            current = next((season for season in seasons if season.get("attributes", {}).get("isOffseason")), None)
        season_id = str(current.get("id")) if current is not None else None
        self._current_season_id = season_id
        self._current_season_loaded_at = now
        return season_id

    def _extract_ranked_summary(self, payload: Any) -> PubgRankedSummary | None:
        mode_stats = payload.get("data", {}).get("attributes", {}).get("rankedGameModeStats", {})
        best_mode_name: str | None = None
        best_mode_payload: dict[str, Any] | None = None
        best_rounds = -1
        best_rank_points = -1
        for mode_name, mode_payload in mode_stats.items():
            rounds_played = int(mode_payload.get("roundsPlayed", 0) or 0)
            rank_points = int(mode_payload.get("currentRankPoint", 0) or 0)
            if rounds_played > best_rounds or (rounds_played == best_rounds and rank_points > best_rank_points):
                best_rounds = rounds_played
                best_rank_points = rank_points
                best_mode_name = mode_name
                best_mode_payload = mode_payload
        if best_mode_name is None or best_mode_payload is None or best_rounds <= 0:
            return None

        current_tier = best_mode_payload.get("currentTier", {}) or {}
        best_tier = best_mode_payload.get("bestTier", {}) or {}
        current_sub_tier_raw = str(current_tier.get("subTier") or "").strip()
        best_sub_tier_raw = str(best_tier.get("subTier") or "").strip()
        return PubgRankedSummary(
            game_mode=best_mode_name,
            current_tier=str(current_tier.get("tier") or "Unknown"),
            current_sub_tier=current_sub_tier_raw or None,
            current_rank_point=int(best_mode_payload.get("currentRankPoint", 0) or 0),
            best_tier=str(best_tier.get("tier") or "Unknown"),
            best_sub_tier=best_sub_tier_raw or None,
            best_rank_point=int(best_mode_payload.get("bestRankPoint", 0) or 0),
            rounds_played=int(best_mode_payload.get("roundsPlayed", 0) or 0),
            avg_rank=float(best_mode_payload.get("avgRank", 0) or 0),
            win_ratio=float(best_mode_payload.get("winRatio", 0) or 0),
            top10_ratio=float(best_mode_payload.get("top10Ratio", 0) or 0),
            wins=int(best_mode_payload.get("wins", 0) or 0),
            kills=int(best_mode_payload.get("kills", 0) or 0),
        )

    def _ban_text(self, ban_type: str | None) -> tuple[str, str, discord.Colour]:
        normalized = (ban_type or "").strip()
        lowered = normalized.lower()
        if not normalized or lowered in {"innocent", "noban", "none", "unknown"}:
            return "Без бана", self._pick(_CLEAN_TITLES), discord.Colour.green()
        if "permanent" in lowered:
            return "Перманентный бан", self._pick(_PERMABAN_TITLES), discord.Colour.red()
        if "temporary" in lowered or "temp" in lowered:
            return "Временный бан", self._pick(_TEMPBAN_TITLES), discord.Colour.orange()
        return normalized, self._pick(_TEMPBAN_TITLES), discord.Colour.orange()

    def _format_seconds(self, total_seconds: float) -> str:
        seconds = max(int(total_seconds), 0)
        hours, remainder = divmod(seconds, 3600)
        minutes, sec = divmod(remainder, 60)
        parts: list[str] = []
        if hours:
            parts.append(f"{hours} ч")
        if minutes:
            parts.append(f"{minutes} мин")
        if sec or not parts:
            parts.append(f"{sec} сек")
        return " ".join(parts)

    def _format_percent(self, ratio: float) -> str:
        return f"{ratio * 100:.1f}%"

    def _format_tier(self, tier: str, sub_tier: str | None) -> str:
        tier_label = discord.utils.escape_markdown(tier)
        if sub_tier:
            return f"{tier_label} {discord.utils.escape_markdown(sub_tier)}"
        return tier_label

    async def _lookup_async(self, nickname: str) -> PubgLookupResult:
        locally_limited, retry_after = self._is_rate_limited_locally()
        if locally_limited:
            return PubgLookupResult(
                ok=False,
                found=False,
                rate_limited=True,
                needs_nickname=False,
                nickname=nickname,
                title=self._pick(_RATE_LIMIT_TITLES),
                description=(
                    f"PUBG API держит меня на паузе. Дай мне ещё **{retry_after} сек**, "
                    "и я снова схожу за сводкой."
                ),
                color=discord.Colour.orange(),
                retry_after_seconds=retry_after,
            )

        cache_key = (
            self.config.pubg.platform,
            self._normalize_nickname(nickname),
            self.config.pubg.include_ranked,
            self.config.pubg.include_lifetime_stats,
        )
        cached = self._cache.get(cache_key)
        now = discord.utils.utcnow()
        if cached is not None and now - cached.cached_at <= timedelta(seconds=self.config.pubg.cache_ttl_seconds):
            return cached.result

        player_url = (
            f"https://api.pubg.com/shards/{self.config.pubg.platform}/players"
            f"?filter[playerNames]={parse.quote(nickname)}"
        )
        try:
            payload, headers = await self._request_json(player_url)
            self._remember_headers(headers)
        except HttpRequestError as exc:
            self._remember_headers(exc.headers)
            if exc.status == 404:
                result = PubgLookupResult(
                    ok=False,
                    found=False,
                    rate_limited=False,
                    needs_nickname=False,
                    nickname=nickname,
                    title=self._pick(_NOT_FOUND_TITLES),
                    description=(
                        f"По нику **{discord.utils.escape_markdown(nickname)}** ничего не нашла "
                        f"на shard **{self.config.pubg.platform}**. Проверь раскладку и символы."
                    ),
                    color=discord.Colour.light_grey(),
                )
                self._cache[cache_key] = _CacheEntry(result=result, cached_at=now)
                return result
            if exc.status == 429:
                locally_limited, retry_after = self._is_rate_limited_locally()
                return PubgLookupResult(
                    ok=False,
                    found=False,
                    rate_limited=True,
                    needs_nickname=False,
                    nickname=nickname,
                    title=self._pick(_RATE_LIMIT_TITLES),
                    description=(
                        f"PUBG API попросил не давить на кнопку. "
                        f"Подожди примерно **{retry_after or 60} сек** и повтори."
                    ),
                    color=discord.Colour.orange(),
                    retry_after_seconds=retry_after or 60,
                )
            return PubgLookupResult(
                ok=False,
                found=False,
                rate_limited=False,
                needs_nickname=False,
                nickname=nickname,
                title=self._pick(_ERROR_TITLES),
                description=f"PUBG API вернул ошибку **{exc.status}**. Чуть позже попробуем ещё раз.",
                color=discord.Colour.red(),
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError):
            return PubgLookupResult(
                ok=False,
                found=False,
                rate_limited=False,
                needs_nickname=False,
                nickname=nickname,
                title=self._pick(_ERROR_TITLES),
                description="Не смогла нормально достучаться до PUBG API. Похоже, там временно капризничает сеть.",
                color=discord.Colour.red(),
            )

        players = payload.get("data") or []
        if not players:
            result = PubgLookupResult(
                ok=False,
                found=False,
                rate_limited=False,
                needs_nickname=False,
                nickname=nickname,
                title=self._pick(_NOT_FOUND_TITLES),
                description=(
                    f"По нику **{discord.utils.escape_markdown(nickname)}** пусто. "
                    "Либо опечатка, либо аккаунт на другом shard."
                ),
                color=discord.Colour.light_grey(),
            )
            self._cache[cache_key] = _CacheEntry(result=result, cached_at=now)
            return result

        player = players[0]
        attributes = player.get("attributes", {})
        matches = player.get("relationships", {}).get("matches", {}).get("data", [])
        ranked_summary: PubgRankedSummary | None = None
        lifetime_summary: PubgLifetimeSummary | None = None
        if self.config.pubg.include_ranked:
            try:
                season_id = await self._resolve_current_season_id()
                if season_id:
                    ranked_url = (
                        f"https://api.pubg.com/shards/{self.config.pubg.platform}/players/{player['id']}/seasons/{season_id}/ranked"
                    )
                    ranked_payload, ranked_headers = await self._request_json(ranked_url)
                    self._remember_headers(ranked_headers)
                    ranked_summary = self._extract_ranked_summary(ranked_payload)
            except Exception:
                ranked_summary = None
        if self.config.pubg.include_lifetime_stats:
            lifetime_url = f"https://api.pubg.com/shards/{self.config.pubg.platform}/players/{player['id']}/seasons/lifetime"
            try:
                lifetime_payload, lifetime_headers = await self._request_json(lifetime_url)
                self._remember_headers(lifetime_headers)
                lifetime_summary = self._extract_best_mode(lifetime_payload)
            except Exception:
                lifetime_summary = None

        player_data = PubgPlayerLookup(
            name=str(attributes.get("name") or nickname),
            account_id=str(player.get("id") or ""),
            shard_id=str(attributes.get("shardId") or self.config.pubg.platform),
            clan_id=str(attributes.get("clanId") or "").strip() or None,
            ban_type=str(attributes.get("banType") or "").strip() or None,
            recent_match_count=len(matches),
            ranked_summary=ranked_summary,
            lifetime_summary=lifetime_summary,
        )
        ban_label, title, color = self._ban_text(player_data.ban_type)
        description = (
            f"Ник **{discord.utils.escape_markdown(player_data.name)}** нашла на shard "
            f"**{discord.utils.escape_markdown(player_data.shard_id)}**. "
            f"По бан-статусу там сейчас: **{ban_label}**."
        )
        result = PubgLookupResult(
            ok=True,
            found=True,
            rate_limited=False,
            needs_nickname=False,
            nickname=player_data.name,
            title=title,
            description=description,
            color=color,
            player=player_data,
        )
        self._cache[cache_key] = _CacheEntry(result=result, cached_at=now)
        return result

    async def lookup(self, nickname: str) -> PubgLookupResult:
        return await self._lookup_async(nickname)

    def render_embed(self, result: PubgLookupResult) -> discord.Embed:
        embed = discord.Embed(title=result.title, description=result.description, color=result.color)
        if result.player is not None:
            player = result.player
            ban_label, _, _ = self._ban_text(player.ban_type)
            embed.add_field(name="Игрок", value=f"**{discord.utils.escape_markdown(player.name)}**", inline=True)
            embed.add_field(name="Статус", value=ban_label, inline=True)
            embed.add_field(name="Платформа", value=discord.utils.escape_markdown(player.shard_id), inline=True)
            embed.add_field(
                name="Матчи",
                value=f"{player.recent_match_count} за последние 14 дней",
                inline=True,
            )
            embed.add_field(
                name="Клан",
                value=discord.utils.escape_markdown(player.clan_id or "не указан"),
                inline=True,
            )
            embed.add_field(
                name="PUBG ID",
                value=f"`{player.account_id}`",
                inline=False,
            )
            if player.ranked_summary is not None:
                ranked = player.ranked_summary
                embed.add_field(
                    name="Ранг сейчас",
                    value=self._format_tier(ranked.current_tier, ranked.current_sub_tier),
                    inline=True,
                )
                embed.add_field(name="RP", value=str(ranked.current_rank_point), inline=True)
                embed.add_field(name="Режим ранга", value=discord.utils.escape_markdown(ranked.game_mode), inline=True)
                embed.add_field(
                    name="Лучший ранг",
                    value=self._format_tier(ranked.best_tier, ranked.best_sub_tier),
                    inline=True,
                )
                embed.add_field(name="Ранговых каток", value=str(ranked.rounds_played), inline=True)
                embed.add_field(name="Побед в ранге", value=str(ranked.wins), inline=True)
                embed.add_field(name="Топ-10 в ранге", value=self._format_percent(ranked.top10_ratio), inline=True)
                embed.add_field(name="Среднее место", value=f"{ranked.avg_rank:.2f}", inline=True)
                embed.add_field(name="Фрагов в ранге", value=str(ranked.kills), inline=True)
            if player.lifetime_summary is not None:
                summary = player.lifetime_summary
                embed.add_field(
                    name="Любимый режим",
                    value=discord.utils.escape_markdown(summary.game_mode),
                    inline=True,
                )
                embed.add_field(name="Каток", value=str(summary.rounds_played), inline=True)
                embed.add_field(name="Побед", value=str(summary.wins), inline=True)
                embed.add_field(name="Топ-10", value=str(summary.top10s), inline=True)
                embed.add_field(name="Фрагов", value=str(summary.kills), inline=True)
                embed.add_field(name="Нажёг урона", value=f"{round(summary.damage_dealt):,}".replace(",", " "), inline=True)
                embed.add_field(
                    name="Время в жизни",
                    value=self._format_seconds(summary.time_survived),
                    inline=True,
                )
        if result.retry_after_seconds:
            embed.add_field(name="Когда повторить", value=f"Через {result.retry_after_seconds} сек", inline=False)
        embed.set_footer(text=f"{EMBED_FOOTER} • PUBG lookup")
        return embed

    async def maybe_handle_message(self, cog: EvaSharedCog, message: discord.Message) -> bool:
        nickname = self.parse_message(message)
        if nickname is None:
            if message.guild is None or message.author.bot or not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
                return False
            if not self.is_enabled_for_channel(message.channel.id):
                return False
            if not message.content or not self._is_pubg_request(message.content):
                return False
            result = self.build_missing_nickname_result()
            try:
                await message.reply(
                    embed=self.render_embed(result),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return True

        if message.guild is None or not isinstance(message.author, discord.Member):
            return False

        if not self.member_has_access(message.author):
            result = self.build_access_denied_result()
            try:
                await message.reply(
                    embed=self.render_embed(result),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return True

        if not self.is_configured:
            result = PubgLookupResult(
                ok=False,
                found=False,
                rate_limited=False,
                needs_nickname=False,
                nickname=nickname,
                title="Я бы посмотрела, но PUBG API у меня не настроен.",
                description=(
                    "Нужны `PUBG_LOOKUP_ENABLED=true`, хотя бы один канал в `PUBG_LOOKUP_CHANNEL_IDS` "
                    "и действующий `PUBG_API_KEY`."
                ),
                color=discord.Colour.orange(),
            )
            try:
                await message.reply(
                    embed=self.render_embed(result),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return True

        cooldown = self.is_user_on_cooldown(message.guild.id, message.author.id)
        if cooldown is not None:
            result = self.build_cooldown_result(cooldown)
            try:
                await message.reply(
                    embed=self.render_embed(result),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return True

        result = await self.lookup(nickname)
        self.remember_user_request(message.guild.id, message.author.id)
        try:
            await message.reply(
                embed=self.render_embed(result),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            return True
        return True
