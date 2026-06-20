"""
EVA Assistant Steam digest service.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import unescape
import random
import re
from time import perf_counter
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import discord

from roseblade_bot import EMBED_FOOTER
from roseblade_bot.config import BotConfig
from roseblade_bot.services.http import http_session


STEAM_WEB_API_BASE = "https://api.steampowered.com"
STEAM_STORE_BASE = "https://store.steampowered.com"
STEAM_CHARTS_URL = f"{STEAM_STORE_BASE}/charts/mostplayed"
STEAM_SUPPORT_URL = f"{STEAM_STORE_BASE}/stats/support/"
STEAM_FEATURED_CATEGORIES_URL = f"{STEAM_STORE_BASE}/api/featuredcategories"
PUBG_APP_ID = 578080
CURRENT_PLAYER_REQUEST_CONCURRENCY = 12
NAME_REQUEST_CONCURRENCY = 6
PRICE_REQUEST_CONCURRENCY = 4
TIMEZONE_FALLBACK_HOURS = {
    "Europe/Simferopol": 3,
    "Europe/Moscow": 3,
    "UTC": 0,
}
APP_URL_RE = re.compile(r"/app/(\d+)")
SALE_URL_RE = re.compile(r"/sale/([^/?#]+)")
WEEKEND_PROMO_HINTS = ("free weekend", "weekend deal", "weekend", "free")

SUPPORT_BACKLOG_RE = re.compile(
    r"Waiting for response</td>\s*"
    r"<td class=\"users_count\"[^>]*>\s*<span class=\"backlogTopHi\">([^<]+)</span>\s*</td>\s*"
    r"<td class=\"users_count\"[^>]*>\s*<span class=\"backlogTopHi\">([^<]+)</span>",
    re.IGNORECASE | re.DOTALL,
)
SUPPORT_ROW_RE = re.compile(
    r"<tr class=\"player_count_row\">.*?"
    r"<span class=\"supportDetail strong\">(.*?)</span>.*?"
    r"<span class=\"supportDetail\">(.*?)</span>.*?"
    r"<span class=\"supportDetail\">(.*?)</span>",
    re.IGNORECASE | re.DOTALL,
)

STEAM_DIGEST_INTROS = (
    "Ева на связи. Принесла вечерний Steam-срез, пока у кого-то уже кипит катка.",
    "Вечерний обход Steam готов. Смотрим, кто держит трон, а кто просто шумит красиво.",
    "Я заглянула в Steam и принесла сухую выжимку без лишней воды. Почти без воды.",
    "Короткий Steam-дайджест на вечер: кто в топе, где жара и сколько народу толпится у Valve.",
    "Ева снова роется в цифрах, чтобы у сервера был нормальный вечерний расклад по Steam.",
)

STEAM_DIGEST_TITLES = (
    "🌙 Вечерний Steam-дайджест",
    "📡 Steam-сводка на вечер",
    "🎮 Что творится в Steam",
    "🔥 Steam вечером выглядит так",
)

STEAM_PUBG_LINES = (
    "PUBG всё ещё держится уверенно и не собирается тихо уходить в тень.",
    "PUBG снова в строю и шумит так, будто весь лут уже разобрали без вас.",
    "PUBG в онлайне бодрится. Паника в лобби официально продолжается.",
    "PUBG на радарах. Кто-то уже ищет дым, а кто-то алиби.",
)

STEAM_API_DOWN_LINES = (
    "Steam Web API сегодня строит из себя молчуна. Бывает и у титанов плохое настроение.",
    "Steam API сейчас отвечает холодно или вовсе молчит. Не драматизируем, но я записала.",
    "С API у Steam сегодня лёгкая хандра. Остальную сводку всё равно дотащила.",
)

STEAM_DAILY_DEAL_LINES = (
    "На витрине дня у Steam сегодня вот такой соблазн.",
    "Steam сегодня сам подкинул скидку дня, я только красиво донесла.",
    "Если кошелёк рядом, лучше держать его покрепче: скидка дня уже машет рукой.",
)

STEAM_WEEKEND_LINES = (
    "На выходные Steam тоже не молчит, там уже подкинули пару приманок.",
    "По уикенд-витрине у Steam тоже движ есть, так что вот короткая наводка.",
    "На выходных Steam снова расставил ловушки для вашего баланса. Смотрим.",
)


@dataclass(frozen=True, slots=True)
class SteamChartGame:
    appid: int
    name: str
    current_players: int
    weekly_rank: int
    last_week_rank: int | None
    weekly_peak: int


@dataclass(frozen=True, slots=True)
class SteamSupportSnapshot:
    waiting_for_response: str
    peak_waiting_90d: str
    refund_requests_24h: str | None
    refund_response_time: str | None


@dataclass(frozen=True, slots=True)
class SteamPromotion:
    title: str
    url: str
    label: str
    appid: int | None
    discount_percent: int | None
    initial_formatted: str | None
    final_formatted: str | None
    discount_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class SteamDigestReport:
    generated_at: datetime
    steam_server_time: datetime | None
    steam_api_latency_ms: int | None
    top_games: tuple[SteamChartGame, ...]
    pubg_game: SteamChartGame | None
    support: SteamSupportSnapshot | None
    chart_rollup_date: datetime | None
    daily_deal: SteamPromotion | None
    weekend_promotions: tuple[SteamPromotion, ...]


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _format_rank_shift(current_rank: int, previous_rank: int | None) -> str:
    if previous_rank is None or previous_rank <= 0:
        return "новичок"
    delta = previous_rank - current_rank
    if delta > 0:
        return f"поднялся на {delta}"
    if delta < 0:
        return f"просел на {abs(delta)}"
    return "держит позицию"


def _format_price_fallback(cents: int | None, currency: str | None) -> str | None:
    if cents is None or not currency:
        return None
    if cents == 0:
        return "Free"
    return f"{cents / 100:.2f} {currency}"


def _extract_appid_from_url(url: str | None) -> int | None:
    if not url:
        return None
    match = APP_URL_RE.search(url)
    if match is None:
        return None
    return int(match.group(1))


def _looks_generic_promo_title(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip()).lower()
    return normalized in {"weekend deal", "free weekend", "publisher sale"} or normalized.startswith("weekend deal")


def _prettify_sale_slug(url: str | None) -> str | None:
    if not url:
        return None
    match = SALE_URL_RE.search(url)
    if match is None:
        return None
    slug = match.group(1)
    pretty = re.sub(r"[-_]+", " ", slug).strip()
    pretty = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", pretty)
    pretty = re.sub(r"(?<=\D)(\d{4})$", r" \1", pretty)
    return pretty.title() if pretty else None


def _steam_color() -> discord.Colour:
    return discord.Colour.from_rgb(27, 40, 56)


class SteamDigestService:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self._app_name_cache: dict[int, str] = {
            730: "Counter-Strike 2",
            570: "Dota 2",
            578080: "PUBG: BATTLEGROUNDS",
        }
        try:
            self.timezone = ZoneInfo(config.steam_digest_timezone)
        except ZoneInfoNotFoundError:
            offset_hours = TIMEZONE_FALLBACK_HOURS.get(config.steam_digest_timezone, 0)
            self.timezone = timezone(timedelta(hours=offset_hours), name=config.steam_digest_timezone)

    @property
    def is_enabled(self) -> bool:
        return self.config.steam_digest_enabled

    @property
    def is_configured(self) -> bool:
        return self.is_enabled and bool(self.config.steam_digest_channel_ids)

    def channel_count(self) -> int:
        return len(self.config.steam_digest_channel_ids)

    def schedule_label(self) -> str:
        return f"{self.config.steam_digest_hour:02d}:{self.config.steam_digest_minute:02d} ({self.config.steam_digest_timezone})"

    def is_due(self, now: datetime) -> bool:
        local_now = now.astimezone(self.timezone)
        scheduled_minutes = self.config.steam_digest_hour * 60 + self.config.steam_digest_minute
        current_minutes = local_now.hour * 60 + local_now.minute
        return current_minutes >= scheduled_minutes

    async def build_report(self) -> SteamDigestReport:
        headers = {
            "User-Agent": "EVA Assistant / RoseBladeBot",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with http_session(timeout_total=25, headers=headers) as session:
            steam_server_time, steam_api_latency_ms = await self._fetch_server_info(session)
            chart_rollup_date, ranked_candidates = await self._fetch_most_played_candidates(session)
            support = await self._fetch_support_snapshot(session) if self.config.steam_digest_include_support_stats else None
            daily_promotion_raw, weekend_promotions_raw = await self._fetch_store_promotions(session)

            candidate_appids = [appid for _, appid, _, _ in ranked_candidates]
            current_players = await self._fetch_current_player_counts(session, candidate_appids)
            sorted_appids = sorted(candidate_appids, key=lambda appid: current_players.get(appid, 0), reverse=True)
            selected_appids = sorted_appids[: self.config.steam_digest_top_count]

            needed_names = set(selected_appids)
            needed_names.add(PUBG_APP_ID)
            promotion_appids = {
                raw["appid"]
                for raw in [daily_promotion_raw, *weekend_promotions_raw]
                if isinstance(raw, dict) and isinstance(raw.get("appid"), int)
            }
            needed_names.update(promotion_appids)
            await self._populate_app_names(session, needed_names)
            price_overviews = await self._fetch_price_overviews(session, promotion_appids)

            candidate_index = {
                appid: (weekly_rank, last_week_rank, weekly_peak)
                for weekly_rank, appid, last_week_rank, weekly_peak in ranked_candidates
            }
            top_games = tuple(
                SteamChartGame(
                    appid=appid,
                    name=self._app_name_cache.get(appid, f"App {appid}"),
                    current_players=current_players.get(appid, 0),
                    weekly_rank=candidate_index[appid][0],
                    last_week_rank=candidate_index[appid][1],
                    weekly_peak=candidate_index[appid][2],
                )
                for appid in selected_appids
            )

            pubg_game: SteamChartGame | None = None
            if PUBG_APP_ID in candidate_index:
                weekly_rank, last_week_rank, weekly_peak = candidate_index[PUBG_APP_ID]
                pubg_game = SteamChartGame(
                    appid=PUBG_APP_ID,
                    name=self._app_name_cache.get(PUBG_APP_ID, "PUBG: BATTLEGROUNDS"),
                    current_players=current_players.get(PUBG_APP_ID, 0),
                    weekly_rank=weekly_rank,
                    last_week_rank=last_week_rank,
                    weekly_peak=weekly_peak,
                )

            daily_deal = self._materialize_promotion(daily_promotion_raw, price_overviews)
            weekend_promotions = tuple(
                promotion
                for promotion in (
                    self._materialize_promotion(raw, price_overviews) for raw in weekend_promotions_raw
                )
                if promotion is not None
            )

            return SteamDigestReport(
                generated_at=datetime.now(timezone.utc),
                steam_server_time=steam_server_time,
                steam_api_latency_ms=steam_api_latency_ms,
                top_games=top_games,
                pubg_game=pubg_game,
                support=support,
                chart_rollup_date=chart_rollup_date,
                daily_deal=daily_deal,
                weekend_promotions=weekend_promotions,
            )

    def build_embed(self, report: SteamDigestReport) -> discord.Embed:
        title = random.choice(STEAM_DIGEST_TITLES)
        description = (
            f"{random.choice(STEAM_DIGEST_INTROS)}\n\n"
            f"[Steam Charts]({STEAM_CHARTS_URL}) • [Steam Support Stats]({STEAM_SUPPORT_URL})"
        )
        embed = discord.Embed(
            title=title,
            description=description,
            colour=_steam_color(),
            timestamp=report.generated_at,
        )

        if report.steam_server_time is not None:
            api_lines = [
                "Статус: **на связи**",
                f"Серверное время Steam: {discord.utils.format_dt(report.steam_server_time, style='F')}",
            ]
            if report.steam_api_latency_ms is not None:
                api_lines.append(f"Ответ API: **{report.steam_api_latency_ms} мс**")
            if report.chart_rollup_date is not None:
                api_lines.append(f"Свежий weekly rollup: {discord.utils.format_dt(report.chart_rollup_date, style='D')}")
        else:
            api_lines = [random.choice(STEAM_API_DOWN_LINES)]
        embed.add_field(name="Steam API", value="\n".join(api_lines), inline=False)

        if report.daily_deal is not None:
            deal = report.daily_deal
            deal_lines = [
                random.choice(STEAM_DAILY_DEAL_LINES),
                f"Сегодняшняя цель: **[{discord.utils.escape_markdown(deal.title)}]({deal.url})**",
            ]
            if deal.discount_percent is not None:
                deal_lines.append(f"Скидка: **-{deal.discount_percent}%**")
            if deal.initial_formatted and deal.final_formatted:
                deal_lines.append(f"Цена: ~~{deal.initial_formatted}~~ -> **{deal.final_formatted}**")
            elif deal.final_formatted:
                deal_lines.append(f"Цена сейчас: **{deal.final_formatted}**")
            if deal.discount_expires_at is not None:
                deal_lines.append(f"Финиш акции: {discord.utils.format_dt(deal.discount_expires_at, style='R')}")
            embed.add_field(name="Скидка дня", value="\n".join(deal_lines), inline=False)

        if report.weekend_promotions:
            weekend_lines = [random.choice(STEAM_WEEKEND_LINES)]
            for promotion in report.weekend_promotions[:2]:
                line = f"• **[{discord.utils.escape_markdown(promotion.title)}]({promotion.url})**"
                details: list[str] = []
                if promotion.label:
                    details.append(promotion.label)
                if promotion.discount_percent is not None:
                    details.append(f"-{promotion.discount_percent}%")
                if promotion.initial_formatted and promotion.final_formatted:
                    details.append(f"{promotion.initial_formatted} -> {promotion.final_formatted}")
                elif promotion.final_formatted:
                    details.append(promotion.final_formatted)
                if details:
                    line += " — " + ", ".join(details)
                weekend_lines.append(line)
            embed.add_field(name="Steam на выходных", value="\n".join(weekend_lines), inline=False)

        if report.pubg_game is not None:
            pubg = report.pubg_game
            pubg_lines = [
                random.choice(STEAM_PUBG_LINES),
                f"Сейчас в игре: **{_format_number(pubg.current_players)}**",
                f"Место в свежем Steam-чарте: **#{pubg.weekly_rank}**",
                f"Пик в чарте: **{_format_number(pubg.weekly_peak)}**",
            ]
            if pubg.last_week_rank is not None:
                pubg_lines.append(f"Недельная динамика: **{_format_rank_shift(pubg.weekly_rank, pubg.last_week_rank)}**")
            embed.add_field(name="PUBG на радаре", value="\n".join(pubg_lines), inline=False)

        if report.support is not None:
            support = report.support
            support_lines = [
                f"Ждут ответа: **{support.waiting_for_response}**",
                f"Пик за 90 дней: **{support.peak_waiting_90d}**",
            ]
            if support.refund_requests_24h and support.refund_response_time:
                support_lines.append(
                    f"Refund Requests: **{support.refund_requests_24h}** за 24ч, обычно **{support.refund_response_time}**"
                )
            embed.add_field(name="Поддержка Steam", value="\n".join(support_lines), inline=False)

        top_lines = []
        for index, game in enumerate(report.top_games, start=1):
            top_lines.append(
                f"`{index:>2}.` **{discord.utils.escape_markdown(game.name)}** — {_format_number(game.current_players)}"
            )
        embed.add_field(
            name=f"Топ {len(report.top_games)} по текущему онлайну",
            value="\n".join(top_lines) or "Не удалось собрать список.",
            inline=False,
        )

        embed.set_footer(text=f"{EMBED_FOOTER} • Steam digest")
        return embed

    async def _fetch_server_info(self, session: aiohttp.ClientSession) -> tuple[datetime | None, int | None]:
        url = f"{STEAM_WEB_API_BASE}/ISteamWebAPIUtil/GetServerInfo/v1/"
        started = perf_counter()
        try:
            async with session.get(url, params={"format": "json"}) as response:
                response.raise_for_status()
                payload = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None, None

        latency_ms = max(int((perf_counter() - started) * 1000), 0)
        response_payload = payload.get("response") if isinstance(payload, dict) else None
        server_time_raw = payload.get("servertime") if isinstance(payload, dict) else None
        if isinstance(response_payload, dict):
            server_time_raw = response_payload.get("servertime", server_time_raw)
        if not isinstance(server_time_raw, int):
            return None, latency_ms
        return datetime.fromtimestamp(server_time_raw, tz=timezone.utc), latency_ms

    async def _fetch_most_played_candidates(
        self,
        session: aiohttp.ClientSession,
    ) -> tuple[datetime | None, list[tuple[int, int, int | None, int]]]:
        url = f"{STEAM_WEB_API_BASE}/ISteamChartsService/GetMostPlayedGames/v1/"
        async with session.get(url, params={"format": "json"}) as response:
            response.raise_for_status()
            payload = await response.json()

        response_payload = payload.get("response", {}) if isinstance(payload, dict) else {}
        ranks = response_payload.get("ranks", [])
        result: list[tuple[int, int, int | None, int]] = []
        for item in ranks:
            if not isinstance(item, dict):
                continue
            appid = item.get("appid")
            weekly_rank = item.get("rank")
            weekly_peak = item.get("peak_in_game")
            last_week_rank = item.get("last_week_rank")
            if not isinstance(appid, int) or not isinstance(weekly_rank, int) or not isinstance(weekly_peak, int):
                continue
            result.append((weekly_rank, appid, last_week_rank if isinstance(last_week_rank, int) else None, weekly_peak))

        rollup_raw = response_payload.get("rollup_date")
        rollup_date = datetime.fromtimestamp(rollup_raw, tz=timezone.utc) if isinstance(rollup_raw, int) else None
        if not result:
            raise RuntimeError("Steam не вернул список популярных игр.")
        return rollup_date, result

    async def _fetch_store_promotions(
        self,
        session: aiohttp.ClientSession,
    ) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
        try:
            async with session.get(STEAM_FEATURED_CATEGORIES_URL, params={"l": "english", "cc": "us"}) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None, []

        if not isinstance(payload, dict):
            return None, []

        nodes = [node for node in payload.values() if isinstance(node, dict)]

        daily_deal_raw: dict[str, object] | None = None
        for node in nodes:
            if node.get("id") != "cat_dailydeal":
                continue
            items = node.get("items")
            if not isinstance(items, list) or not items:
                continue
            first_item = items[0]
            if not isinstance(first_item, dict):
                continue
            appid = first_item.get("id")
            url = f"{STEAM_STORE_BASE}/app/{appid}" if isinstance(appid, int) else STEAM_STORE_BASE
            expires_ts = first_item.get("discount_expiration")
            daily_deal_raw = {
                "title": str(first_item.get("name") or "Daily Deal").strip(),
                "url": url,
                "label": "Daily Deal",
                "appid": appid if isinstance(appid, int) else None,
                "discount_percent": first_item.get("discount_percent") if isinstance(first_item.get("discount_percent"), int) else None,
                "original_price": first_item.get("original_price") if isinstance(first_item.get("original_price"), int) else None,
                "final_price": first_item.get("final_price") if isinstance(first_item.get("final_price"), int) else None,
                "currency": str(first_item.get("currency")).strip() if first_item.get("currency") else None,
                "discount_expiration": datetime.fromtimestamp(expires_ts, tz=timezone.utc) if isinstance(expires_ts, int) else None,
            }
            break

        weekend_promotions: list[dict[str, object]] = []
        seen_urls: set[str] = set()
        for node in nodes:
            if node.get("id") != "cat_spotlight":
                continue
            items = node.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                raw_title = str(item.get("name") or "").strip()
                body = str(item.get("body") or "").strip()
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                text_blob = f"{raw_title} {body} {url}".lower()
                if not any(hint in text_blob for hint in WEEKEND_PROMO_HINTS):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                appid = _extract_appid_from_url(url)
                weekend_promotions.append(
                    {
                        "title": raw_title or _prettify_sale_slug(url) or "Weekend promo",
                        "url": url,
                        "label": raw_title or "Weekend promo",
                        "appid": appid,
                        "discount_percent": None,
                        "original_price": None,
                        "final_price": None,
                        "currency": None,
                        "discount_expiration": None,
                    }
                )
                if len(weekend_promotions) >= 3:
                    return daily_deal_raw, weekend_promotions

        return daily_deal_raw, weekend_promotions

    async def _fetch_current_player_counts(
        self,
        session: aiohttp.ClientSession,
        appids: list[int],
    ) -> dict[int, int]:
        semaphore = asyncio.Semaphore(CURRENT_PLAYER_REQUEST_CONCURRENCY)
        results: dict[int, int] = {}

        async def worker(appid: int) -> None:
            async with semaphore:
                url = f"{STEAM_WEB_API_BASE}/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
                try:
                    async with session.get(url, params={"appid": appid, "format": "json"}) as response:
                        response.raise_for_status()
                        payload = await response.json()
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    results[appid] = 0
                    return

                response_payload = payload.get("response", {}) if isinstance(payload, dict) else {}
                player_count = response_payload.get("player_count")
                results[appid] = player_count if isinstance(player_count, int) else 0

        await asyncio.gather(*(worker(appid) for appid in appids))
        return results

    async def _populate_app_names(self, session: aiohttp.ClientSession, appids: set[int]) -> None:
        missing = [appid for appid in appids if appid not in self._app_name_cache]
        if not missing:
            return

        semaphore = asyncio.Semaphore(NAME_REQUEST_CONCURRENCY)

        async def worker(appid: int) -> None:
            async with semaphore:
                url = f"{STEAM_STORE_BASE}/api/appdetails"
                params = {
                    "appids": str(appid),
                    "filters": "basic",
                    "l": "english",
                }
                try:
                    async with session.get(url, params=params) as response:
                        response.raise_for_status()
                        payload = await response.json(content_type=None)
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    self._app_name_cache[appid] = f"App {appid}"
                    return

                node = payload.get(str(appid), {}) if isinstance(payload, dict) else {}
                data = node.get("data", {}) if isinstance(node, dict) else {}
                raw_name = data.get("name")
                self._app_name_cache[appid] = str(raw_name).strip() if raw_name else f"App {appid}"

        await asyncio.gather(*(worker(appid) for appid in missing))

    async def _fetch_price_overviews(
        self,
        session: aiohttp.ClientSession,
        appids: set[int],
    ) -> dict[int, dict[str, object]]:
        if not appids:
            return {}

        semaphore = asyncio.Semaphore(PRICE_REQUEST_CONCURRENCY)
        results: dict[int, dict[str, object]] = {}

        async def worker(appid: int) -> None:
            async with semaphore:
                url = f"{STEAM_STORE_BASE}/api/appdetails"
                params = {
                    "appids": str(appid),
                    "filters": "price_overview",
                    "l": "english",
                    "cc": "us",
                }
                try:
                    async with session.get(url, params=params) as response:
                        response.raise_for_status()
                        payload = await response.json(content_type=None)
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    return

                node = payload.get(str(appid), {}) if isinstance(payload, dict) else {}
                data = node.get("data", {}) if isinstance(node, dict) else {}
                price_overview = data.get("price_overview")
                if isinstance(price_overview, dict):
                    results[appid] = price_overview

        await asyncio.gather(*(worker(appid) for appid in appids))
        return results

    async def _fetch_support_snapshot(self, session: aiohttp.ClientSession) -> SteamSupportSnapshot | None:
        try:
            async with session.get(STEAM_SUPPORT_URL, params={"l": "english"}) as response:
                response.raise_for_status()
                html = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

        backlog_match = SUPPORT_BACKLOG_RE.search(html)
        if backlog_match is None:
            return None

        waiting_for_response = _clean_html_text(backlog_match.group(1))
        peak_waiting_90d = _clean_html_text(backlog_match.group(2))

        refund_requests_24h: str | None = None
        refund_response_time: str | None = None
        for row_match in SUPPORT_ROW_RE.finditer(html):
            label = _clean_html_text(row_match.group(1))
            submitted = _clean_html_text(row_match.group(2))
            response_time = _clean_html_text(row_match.group(3))
            if label.lower() == "refund requests":
                refund_requests_24h = submitted
                refund_response_time = response_time
                break

        return SteamSupportSnapshot(
            waiting_for_response=waiting_for_response,
            peak_waiting_90d=peak_waiting_90d,
            refund_requests_24h=refund_requests_24h,
            refund_response_time=refund_response_time,
        )

    def _materialize_promotion(
        self,
        raw: dict[str, object] | None,
        price_overviews: dict[int, dict[str, object]],
    ) -> SteamPromotion | None:
        if not raw:
            return None

        appid = raw.get("appid") if isinstance(raw.get("appid"), int) else None
        raw_title = str(raw.get("title") or "Steam promo").strip()
        title = raw_title
        if _looks_generic_promo_title(raw_title):
            if appid is not None:
                title = self._app_name_cache.get(appid, raw_title)
            else:
                title = _prettify_sale_slug(str(raw.get("url") or "")) or raw_title
        elif raw_title == "Publisher Sale":
            title = _prettify_sale_slug(str(raw.get("url") or "")) or raw_title

        price_info = price_overviews.get(appid or -1, {})
        discount_percent = price_info.get("discount_percent")
        if not isinstance(discount_percent, int):
            discount_percent = raw.get("discount_percent") if isinstance(raw.get("discount_percent"), int) else None

        initial_formatted = price_info.get("initial_formatted")
        if not isinstance(initial_formatted, str):
            initial_formatted = _format_price_fallback(
                raw.get("original_price") if isinstance(raw.get("original_price"), int) else None,
                raw.get("currency") if isinstance(raw.get("currency"), str) else None,
            )

        final_formatted = price_info.get("final_formatted")
        if not isinstance(final_formatted, str):
            final_formatted = _format_price_fallback(
                raw.get("final_price") if isinstance(raw.get("final_price"), int) else None,
                raw.get("currency") if isinstance(raw.get("currency"), str) else None,
            )

        return SteamPromotion(
            title=title,
            url=str(raw.get("url") or STEAM_STORE_BASE),
            label=str(raw.get("label") or "Steam promo"),
            appid=appid,
            discount_percent=discount_percent,
            initial_formatted=initial_formatted,
            final_formatted=final_formatted,
            discount_expires_at=raw.get("discount_expiration") if isinstance(raw.get("discount_expiration"), datetime) else None,
        )

    @staticmethod
    def local_today(now: datetime, target_tz: ZoneInfo | timezone) -> date:
        return now.astimezone(target_tz).date()
