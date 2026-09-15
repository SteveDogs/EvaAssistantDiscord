"""
EVA Assistant Steam availability monitor.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter

import aiohttp
import discord

from roseblade_bot import EMBED_FOOTER
from roseblade_bot.config import BotConfig
from roseblade_bot.services.http import http_session


STEAMSTAT_URL = "https://steamstat.us/"
_PROBES = (
    ("store", "Магазин Steam", "https://store.steampowered.com/"),
    ("community", "Steam Community", "https://steamcommunity.com/"),
    ("web_api", "Steam Web API", "https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/?format=json"),
    ("cm_directory", "Connection Managers", "https://api.steampowered.com/ISteamDirectory/GetCMList/v1/?cellid=0"),
)


@dataclass(frozen=True, slots=True)
class SteamServiceProbe:
    key: str
    label: str
    available: bool
    latency_ms: int | None
    detail: str | None


@dataclass(frozen=True, slots=True)
class SteamStatusSnapshot:
    services: tuple[SteamServiceProbe, ...]

    @property
    def failed_services(self) -> tuple[SteamServiceProbe, ...]:
        return tuple(service for service in self.services if not service.available)


class SteamStatusService:
    def __init__(self, config: BotConfig) -> None:
        self.config = config

    @property
    def is_enabled(self) -> bool:
        return self.config.steam_status.enabled

    @property
    def is_configured(self) -> bool:
        return self.is_enabled and bool(self.config.steam_status.channel_ids)

    def channel_count(self) -> int:
        return len(self.config.steam_status.channel_ids)

    def schedule_label(self) -> str:
        return f"every {self.config.steam_status.poll_minutes}m"

    async def fetch_snapshot(self) -> SteamStatusSnapshot:
        headers = {
            "User-Agent": "EVA Assistant Steam Monitor / RoseBladeBot",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        }
        async with http_session(timeout_total=18, headers=headers) as session:
            probes = await asyncio.gather(*(self._probe(session, *definition) for definition in _PROBES))
        return SteamStatusSnapshot(services=tuple(probes))

    @staticmethod
    async def _probe(
        session: aiohttp.ClientSession,
        key: str,
        label: str,
        url: str,
    ) -> SteamServiceProbe:
        started = perf_counter()
        try:
            async with session.get(url, allow_redirects=True) as response:
                await response.content.read(512)
                latency_ms = max(0, int((perf_counter() - started) * 1000))
                # 4xx is a reachable Steam edge; only network errors and 5xx indicate an outage.
                available = response.status < 500
                detail = None if available else f"HTTP {response.status}"
                return SteamServiceProbe(key, label, available, latency_ms, detail)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            return SteamServiceProbe(key, label, False, None, type(error).__name__)

    @staticmethod
    def build_incident_embed(services: tuple[SteamServiceProbe, ...]) -> discord.Embed:
        names = "\n".join(f"• {service.label} — {service.detail or 'недоступно'}" for service in services)
        embed = discord.Embed(
            title="🚨 У Steam неполадки",
            description=(
                "Ева подтвердила проблему повторной проверкой. Это похоже на сбой на стороне Steam, "
                "а не на ваш интернет."
            ),
            colour=discord.Colour.red(),
            url=STEAMSTAT_URL,
        )
        embed.add_field(name="Что отвечает с ошибкой", value=names[:1024], inline=False)
        embed.add_field(name="Проверка", value=f"[Открыть SteamStat.us]({STEAMSTAT_URL})", inline=False)
        embed.set_footer(text=f"{EMBED_FOOTER} • Steam status")
        return embed

    @staticmethod
    def build_recovery_embed(services: tuple[SteamServiceProbe, ...], duration_label: str) -> discord.Embed:
        names = ", ".join(service.label for service in services)
        embed = discord.Embed(
            title="✅ Steam снова отвечает",
            description="Похоже, сервисы вернулись в строй. Можно пробовать зайти ещё раз.",
            colour=discord.Colour.green(),
            url=STEAMSTAT_URL,
        )
        embed.add_field(name="Восстановлено", value=names[:1024], inline=False)
        embed.add_field(name="Длительность сбоя", value=duration_label, inline=True)
        embed.add_field(name="Проверка", value=f"[SteamStat.us]({STEAMSTAT_URL})", inline=True)
        embed.set_footer(text=f"{EMBED_FOOTER} • Steam status")
        return embed
