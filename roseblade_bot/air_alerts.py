"""
EVA Assistant Ukraine air alert service.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from roseblade_bot import EMBED_FOOTER
from roseblade_bot.alert_intel import ThreatIntelHint, threat_priority
from roseblade_bot.config import BotConfig
from roseblade_bot.services.http import http_session

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover
    Image = None
    ImageDraw = None
    ImageFilter = None
    ImageFont = None


MODULE_DIR = Path(__file__).resolve().parent
ASSET_DIR = MODULE_DIR / "assets"
GEOJSON_PATH = ASSET_DIR / "ukraine_alert_regions.geojson"
KYIV_TZ_NAME = "Europe/Kyiv"
FALLBACK_TZ = timezone(timedelta(hours=3), name=KYIV_TZ_NAME)
CANVAS_SIZE = (1600, 900)
MAP_BOX = (80, 110, 980, 820)
CARD_X = 1040
CARD_WIDTH = 500
FONT_CANDIDATES = (
    Path("assets/fonts/Unbounded-Bold.ttf"),
    Path("assets/fonts/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
)
STATUS_NO_ALERT = "N"
STATUS_ACTIVE = "A"
STATUS_PARTIAL = "P"
OBLAST_STATUS_ORDER = (
    "Автономна Республіка Крим",
    "Волинська область",
    "Вінницька область",
    "Дніпропетровська область",
    "Донецька область",
    "Житомирська область",
    "Закарпатська область",
    "Запорізька область",
    "Івано-Франківська область",
    "м. Київ",
    "Київська область",
    "Кіровоградська область",
    "Луганська область",
    "Львівська область",
    "Миколаївська область",
    "Одеська область",
    "Полтавська область",
    "Рівненська область",
    "м. Севастополь",
    "Сумська область",
    "Тернопільська область",
    "Харківська область",
    "Херсонська область",
    "Хмельницька область",
    "Черкаська область",
    "Чернівецька область",
    "Чернігівська область",
)
REGION_TITLE_BY_SHAPE_ISO = {
    "UA-43": "Автономна Республіка Крим",
    "UA-07": "Волинська область",
    "UA-05": "Вінницька область",
    "UA-12": "Дніпропетровська область",
    "UA-14": "Донецька область",
    "UA-18": "Житомирська область",
    "UA-21": "Закарпатська область",
    "UA-23": "Запорізька область",
    "UA-26": "Івано-Франківська область",
    "UA-30": "м. Київ",
    "UA-32": "Київська область",
    "UA-35": "Кіровоградська область",
    "UA-09": "Луганська область",
    "UA-46": "Львівська область",
    "UA-48": "Миколаївська область",
    "UA-51": "Одеська область",
    "UA-53": "Полтавська область",
    "UA-56": "Рівненська область",
    "UA-40": "м. Севастополь",
    "UA-59": "Сумська область",
    "UA-61": "Тернопільська область",
    "UA-63": "Харківська область",
    "UA-65": "Херсонська область",
    "UA-68": "Хмельницька область",
    "UA-71": "Черкаська область",
    "UA-77": "Чернівецька область",
    "UA-74": "Чернігівська область",
}
STATUS_TEXT = {
    STATUS_NO_ALERT: "Немає тривоги",
    STATUS_ACTIVE: "Тривога по всій області",
    STATUS_PARTIAL: "Часткова тривога",
}
ALERT_TYPE_LABELS = {
    "air_raid": "Повітряна тривога",
    "artillery_shelling": "Артобстріл",
    "urban_fights": "Вуличні бої",
    "chemical": "Хімічна загроза",
    "nuclear": "Радіаційна загроза",
}
ALERT_TYPE_SHORT_LABELS = {
    "air_raid": "Сирена",
    "artillery_shelling": "Артобстріл",
    "urban_fights": "Бої",
    "chemical": "Хімзагроза",
    "nuclear": "Радзагроза",
}
STATUS_FILL = {
    STATUS_NO_ALERT: (38, 46, 70, 255),
    STATUS_ACTIVE: (255, 96, 118, 255),
    STATUS_PARTIAL: (255, 183, 77, 255),
}
STATUS_GLOW = {
    STATUS_NO_ALERT: (70, 86, 129, 60),
    STATUS_ACTIVE: (255, 96, 118, 125),
    STATUS_PARTIAL: (255, 183, 77, 110),
}
TRANSITION_COLORS = {
    "started": discord.Colour.from_rgb(255, 96, 118),
    "scaled_up": discord.Colour.from_rgb(255, 128, 96),
    "scaled_down": discord.Colour.from_rgb(255, 183, 77),
    "ended": discord.Colour.from_rgb(93, 201, 126),
}
INTEL_COLORS = {
    "ballistic": discord.Colour.from_rgb(173, 110, 255),
    "mig": discord.Colour.from_rgb(84, 194, 255),
    "drone": discord.Colour.from_rgb(255, 164, 82),
    "cab": discord.Colour.from_rgb(255, 108, 108),
    "aviation": discord.Colour.from_rgb(122, 189, 255),
    "generic": discord.Colour.from_rgb(87, 143, 255),
}


@dataclass(frozen=True, slots=True)
class ActiveAlertRecord:
    location_title: str
    location_type: str
    location_uid: str
    location_oblast: str
    alert_type: str
    started_at: datetime | None
    notes: str


@dataclass(frozen=True, slots=True)
class RegionGeometry:
    title: str
    rings: tuple[tuple[tuple[float, float], ...], ...]


@dataclass(frozen=True, slots=True)
class RegionSnapshot:
    title: str
    status: str
    alerts: tuple[ActiveAlertRecord, ...]
    started_at: datetime | None


@dataclass(frozen=True, slots=True)
class AirAlertSnapshot:
    fetched_at: datetime
    oblast_status_string: str
    regions: dict[str, RegionSnapshot]
    provider_key: str
    source_label: str


@dataclass(frozen=True, slots=True)
class AirAlertRenderResult:
    image_bytes: bytes
    signature: str
    active_count: int
    partial_count: int


@dataclass(frozen=True, slots=True)
class AirAlertTransition:
    region_title: str
    previous_status: str
    current_status: str
    current_alerts: tuple[ActiveAlertRecord, ...]
    current_started_at: datetime | None
    previous_started_at: datetime | None
    kind: str


@dataclass(slots=True)
class CachedApiPayload:
    last_modified: str | None
    value: Any


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _parse_local_datetime(value: str | None, tz: timezone | ZoneInfo) -> datetime | None:
    parsed = _parse_datetime(value)
    if parsed is not None:
        if parsed.tzinfo is not None:
            return parsed
        return parsed.replace(tzinfo=tz)
    return None


def _format_local_time(value: datetime | None, tz: timezone | ZoneInfo) -> str:
    if value is None:
        return "н/д"
    return value.astimezone(tz).strftime("%d.%m %H:%M")


def _format_duration(started_at: datetime | None, ended_at: datetime | None) -> str | None:
    if started_at is None or ended_at is None:
        return None
    delta = ended_at - started_at
    total_seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} год {minutes} хв"
    return f"{minutes} хв"


def _alert_type_label(alert_type: str) -> str:
    return ALERT_TYPE_LABELS.get(alert_type, alert_type)


def _truncate(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 1:
        return cleaned[:limit]
    return cleaned[: limit - 1].rstrip() + "…"


def _transition_kind(previous_status: str, current_status: str) -> str:
    if previous_status == STATUS_NO_ALERT and current_status in {STATUS_ACTIVE, STATUS_PARTIAL}:
        return "started"
    if previous_status == STATUS_PARTIAL and current_status == STATUS_ACTIVE:
        return "scaled_up"
    if previous_status == STATUS_ACTIVE and current_status == STATUS_PARTIAL:
        return "scaled_down"
    if previous_status in {STATUS_ACTIVE, STATUS_PARTIAL} and current_status == STATUS_NO_ALERT:
        return "ended"
    return "changed"


def _iter_exterior_rings(geometry: dict[str, Any]) -> list[list[tuple[float, float]]]:
    geometry_type = str(geometry.get("type") or "")
    coordinates = geometry.get("coordinates") or []
    rings: list[list[tuple[float, float]]] = []
    if geometry_type == "Polygon":
        if coordinates:
            rings.append([(float(lon), float(lat)) for lon, lat in coordinates[0]])
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            if polygon:
                rings.append([(float(lon), float(lat)) for lon, lat in polygon[0]])
    return rings


class AirAlertService:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self._regions = self._load_regions()
        self._alerts_in_ua_cache: dict[str, CachedApiPayload] = {}
        try:
            self.timezone: timezone | ZoneInfo = ZoneInfo(KYIV_TZ_NAME)
        except ZoneInfoNotFoundError:
            self.timezone = FALLBACK_TZ

    @property
    def is_enabled(self) -> bool:
        return self.config.air_alert.enabled

    @property
    def is_configured(self) -> bool:
        return self.is_enabled and bool(self.config.air_alert.channel_ids) and self.resolved_provider_key is not None

    @property
    def requested_provider_key(self) -> str:
        requested = self.config.air_alert.provider.strip().lower()
        if requested in {"auto", "alerts_in_ua", "ubilling"}:
            return requested
        return "auto"

    @property
    def resolved_provider_key(self) -> str | None:
        requested = self.requested_provider_key
        if requested == "alerts_in_ua":
            return "alerts_in_ua" if self.config.air_alert.api_token else None
        if requested == "ubilling":
            return "ubilling"
        if self.config.air_alert.api_token:
            return "alerts_in_ua"
        return "ubilling"

    def channel_count(self) -> int:
        return len(self.config.air_alert.channel_ids)

    def schedule_label(self) -> str:
        provider = self.provider_label()
        return f"every {self.config.air_alert.poll_seconds}s via {provider}"

    def provider_label(self) -> str:
        provider = self.resolved_provider_key
        if provider == "alerts_in_ua":
            return "alerts.in.ua"
        if provider == "ubilling":
            source = self.config.air_alert.ubilling_source.strip().lower() or "default"
            return f"ubilling/{source}"
        return "not configured"

    def dependency_error(self) -> str | None:
        if Image is None or ImageDraw is None or ImageFilter is None or ImageFont is None:
            return "Pillow не установлен. Обнови зависимости через `pip install -r requirements.txt`."
        if not GEOJSON_PATH.exists():
            return f"Не найден GeoJSON карты: {GEOJSON_PATH}"
        return None

    async def fetch_snapshot(self) -> AirAlertSnapshot:
        provider = self.resolved_provider_key
        if provider == "alerts_in_ua":
            return await self._fetch_snapshot_alerts_in_ua()
        if provider == "ubilling":
            return await self._fetch_snapshot_ubilling()
        raise RuntimeError(
            "Air alert provider не настроен. Для alerts.in.ua нужен AIR_ALERT_API_TOKEN, "
            "либо переключи AIR_ALERT_PROVIDER=ubilling."
        )

    async def _fetch_snapshot_alerts_in_ua(self) -> AirAlertSnapshot:
        if not self.config.air_alert.api_token:
            raise RuntimeError("AIR_ALERT_API_TOKEN пустой. Нужен токен alerts.in.ua API.")

        headers = {
            "Authorization": f"Bearer {self.config.air_alert.api_token}",
            "User-Agent": "EVA Assistant / Ukraine air alerts",
            "Accept": "application/json",
        }
        async with http_session(timeout_total=20, headers=headers) as session:
            compact_raw = await self._fetch_alerts_in_ua_json(
                session,
                cache_key="compact_by_oblast",
                url="https://api.alerts.in.ua/v1/iot/active_air_raid_alerts_by_oblast.json",
            )
            if not isinstance(compact_raw, str):
                raise RuntimeError("Неожиданный формат compact статуса от alerts.in.ua.")
            compact_status = compact_raw.strip()

            active_payload = await self._fetch_alerts_in_ua_json(
                session,
                cache_key="active_alerts",
                url="https://api.alerts.in.ua/v1/alerts/active.json",
            )
            if not isinstance(active_payload, dict):
                raise RuntimeError("Неожиданный формат списка активных тревог от alerts.in.ua.")

        alerts_by_oblast: dict[str, list[ActiveAlertRecord]] = {title: [] for title in OBLAST_STATUS_ORDER}
        for item in active_payload.get("alerts", []):
            location_oblast = str(item.get("location_oblast") or item.get("location_title") or "").strip()
            if not location_oblast:
                continue
            record = ActiveAlertRecord(
                location_title=str(item.get("location_title") or location_oblast),
                location_type=str(item.get("location_type") or "unknown"),
                location_uid=str(item.get("location_uid") or ""),
                location_oblast=location_oblast,
                alert_type=str(item.get("alert_type") or "air_raid"),
                started_at=_parse_datetime(item.get("started_at")),
                notes=str(item.get("notes") or "").strip(),
            )
            alerts_by_oblast.setdefault(location_oblast, []).append(record)

        regions: dict[str, RegionSnapshot] = {}
        for index, title in enumerate(OBLAST_STATUS_ORDER):
            status = compact_status[index] if index < len(compact_status) else STATUS_NO_ALERT
            if status not in {STATUS_NO_ALERT, STATUS_ACTIVE, STATUS_PARTIAL}:
                status = STATUS_NO_ALERT
            alerts = tuple(sorted(alerts_by_oblast.get(title, []), key=lambda item: item.started_at or datetime.min.replace(tzinfo=timezone.utc)))
            started_at = min((alert.started_at for alert in alerts if alert.started_at is not None), default=None)
            regions[title] = RegionSnapshot(
                title=title,
                status=status,
                alerts=alerts,
                started_at=started_at,
            )

        return AirAlertSnapshot(
            fetched_at=datetime.now(timezone.utc),
            oblast_status_string=compact_status,
            regions=regions,
            provider_key="alerts_in_ua",
            source_label="alerts.in.ua",
        )

    async def _fetch_alerts_in_ua_json(
        self,
        session: Any,
        *,
        cache_key: str,
        url: str,
    ) -> Any:
        cached = self._alerts_in_ua_cache.get(cache_key)
        request_headers: dict[str, str] = {}
        if cached is not None and cached.last_modified:
            request_headers["If-Modified-Since"] = cached.last_modified

        async with session.get(url, headers=request_headers or None) as response:
            body = await response.read()
            if response.status == 304:
                if cached is None:
                    raise RuntimeError("alerts.in.ua вернул 304, но локального кеша ещё нет.")
                return cached.value
            if response.status >= 400:
                raise RuntimeError(self._alerts_in_ua_error_message(url, response.status))

        payload = json.loads(body.decode("utf-8"))
        self._alerts_in_ua_cache[cache_key] = CachedApiPayload(
            last_modified=response.headers.get("Last-Modified"),
            value=payload,
        )
        return payload

    @staticmethod
    def _alerts_in_ua_error_message(url: str, status: int) -> str:
        endpoint = url.rsplit("/", 1)[-1]
        if status == 401:
            return (
                f"alerts.in.ua отклонил запрос `{endpoint}`: токен не принят. "
                "Проверь AIR_ALERT_API_TOKEN."
            )
        if status == 403:
            return (
                f"alerts.in.ua отклонил запрос `{endpoint}`: доступ запрещён для текущего IP "
                "или API недоступно из этой страны."
            )
        if status == 429:
            return (
                f"alerts.in.ua вернул лимит по `{endpoint}`. "
                "Увеличь AIR_ALERT_POLL_SECONDS, чтобы не упереться в rate limit."
            )
        return f"alerts.in.ua endpoint `{endpoint}` returned {status}"

    async def _fetch_snapshot_ubilling(self) -> AirAlertSnapshot:
        params: dict[str, str] = {}
        source = self.config.air_alert.ubilling_source.strip().lower()
        if source and source != "default":
            params["source"] = source

        headers = {
            "User-Agent": "EVA Assistant / Ukraine air alerts",
            "Accept": "application/json",
        }
        async with http_session(timeout_total=20, headers=headers) as session:
            async with session.get("https://ubilling.net.ua/aerialalerts/", params=params) as response:
                body = await response.read()
                if response.status >= 400:
                    raise RuntimeError(f"ubilling aerialalerts returned {response.status}")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Неожиданный формат ответа от ubilling aerialalerts.")

        states = payload.get("states")
        if not isinstance(states, dict):
            raise RuntimeError("В ответе ubilling нет ключа `states`.")

        regions: dict[str, RegionSnapshot] = {}
        status_chunks: list[str] = []
        for title in OBLAST_STATUS_ORDER:
            raw_state = states.get(title)
            state_payload = raw_state if isinstance(raw_state, dict) else {}
            is_active = bool(state_payload.get("alertnow"))
            status = STATUS_ACTIVE if is_active else STATUS_NO_ALERT
            changed_at = _parse_local_datetime(state_payload.get("changed"), self.timezone)
            alerts: tuple[ActiveAlertRecord, ...] = ()
            if is_active:
                alerts = (
                    ActiveAlertRecord(
                        location_title=title,
                        location_type="oblast",
                        location_uid="",
                        location_oblast=title,
                        alert_type="air_raid",
                        started_at=changed_at,
                        notes="Дані отримані через публічний проксі ubilling.",
                    ),
                )
            regions[title] = RegionSnapshot(
                title=title,
                status=status,
                alerts=alerts,
                started_at=changed_at if is_active else None,
            )
            status_chunks.append(status)

        fetched_at = _parse_local_datetime(payload.get("cachedat"), self.timezone) or datetime.now(timezone.utc)
        source_label = str(payload.get("source") or "ubilling").strip() or "ubilling"
        return AirAlertSnapshot(
            fetched_at=fetched_at,
            oblast_status_string="".join(status_chunks),
            regions=regions,
            provider_key="ubilling",
            source_label=source_label,
        )

    def detect_transitions(
        self,
        previous_status_string: str | None,
        snapshot: AirAlertSnapshot,
        previous_started_at_by_region: dict[str, datetime | None] | None = None,
    ) -> list[AirAlertTransition]:
        previous = previous_status_string or ""
        previous_started = previous_started_at_by_region or {}
        transitions: list[AirAlertTransition] = []
        for index, region_title in enumerate(OBLAST_STATUS_ORDER):
            current_status = snapshot.regions[region_title].status
            old_status = previous[index] if index < len(previous) else STATUS_NO_ALERT
            if old_status == current_status:
                continue
            transitions.append(
                AirAlertTransition(
                    region_title=region_title,
                    previous_status=old_status,
                    current_status=current_status,
                    current_alerts=snapshot.regions[region_title].alerts,
                    current_started_at=snapshot.regions[region_title].started_at,
                    previous_started_at=previous_started.get(region_title),
                    kind=_transition_kind(old_status, current_status),
                )
            )
        return transitions

    def build_map_embed(
        self,
        snapshot: AirAlertSnapshot,
        render: AirAlertRenderResult,
        intel_hints: tuple[ThreatIntelHint, ...] = (),
    ) -> discord.Embed:
        active_regions = [region for region in snapshot.regions.values() if region.status == STATUS_ACTIVE]
        partial_regions = [region for region in snapshot.regions.values() if region.status == STATUS_PARTIAL]
        calm_count = len(OBLAST_STATUS_ORDER) - len(active_regions) - len(partial_regions)
        freshest_hint = self._freshest_hint(intel_hints, snapshot.fetched_at)
        description = (
            "Єва тримає live-карту повітряних тривог по областях України. "
            f"Стан мапи оновлюється через `{snapshot.source_label}`."
        )
        if freshest_hint is not None:
            description += (
                f"\nОстанній тривожний сигнал: **{freshest_hint.short_label}**"
                f"{self._format_hint_regions(freshest_hint)}."
            )

        embed = discord.Embed(
            title=self.config.air_alert.title,
            description=description,
            colour=discord.Colour.from_rgb(87, 143, 255),
            timestamp=snapshot.fetched_at,
        )
        embed.add_field(name="Активно по області", value=str(render.active_count), inline=True)
        embed.add_field(name="Частково", value=str(render.partial_count), inline=True)
        embed.add_field(name="Без тривоги", value=str(calm_count), inline=True)

        hottest = active_regions + partial_regions
        if hottest:
            lines = []
            for region in hottest[:10]:
                types = ", ".join(sorted({_alert_type_label(alert.alert_type) for alert in region.alerts})) or "Повітряна тривога"
                lines.append(f"• **{region.title}** — {STATUS_TEXT[region.status]} · {types}")
            embed.add_field(name="Що зараз шумить", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Стан", value="По областях зараз без активної повітряної тривоги.", inline=False)

        embed.set_footer(text=f"{EMBED_FOOTER} • {snapshot.source_label}")
        return embed

    def build_transition_embed(
        self,
        transition: AirAlertTransition,
        snapshot: AirAlertSnapshot,
        intel_hints: tuple[ThreatIntelHint, ...] = (),
    ) -> discord.Embed:
        title_map = {
            "started": "🚨 Почалась тривога",
            "scaled_up": "⚠️ Тривога посилилась",
            "scaled_down": "🟠 Тривога стала частковою",
            "ended": "✅ Відбій тривоги",
            "changed": "ℹ️ Оновлення тривоги",
        }
        region = snapshot.regions[transition.region_title]
        region_hint = self._best_region_hint(transition.region_title, intel_hints, snapshot.fetched_at)
        embed = discord.Embed(
            title=title_map.get(transition.kind, "ℹ️ Оновлення тривоги"),
            description=self._transition_description(transition, region_hint),
            colour=TRANSITION_COLORS.get(transition.kind, discord.Colour.blurple()),
            timestamp=snapshot.fetched_at,
        )
        embed.add_field(name="Область", value=transition.region_title, inline=False)
        embed.add_field(name="Було", value=STATUS_TEXT.get(transition.previous_status, transition.previous_status), inline=True)
        embed.add_field(name="Стало", value=STATUS_TEXT.get(transition.current_status, transition.current_status), inline=True)

        if transition.kind != "ended":
            threat_types = ", ".join(sorted({_alert_type_label(alert.alert_type) for alert in transition.current_alerts})) or "Повітряна тривога"
            embed.add_field(name="Загроза", value=threat_types, inline=False)
            if region.alerts:
                locations = ", ".join(_truncate(alert.location_title, 48) for alert in region.alerts[:5])
                embed.add_field(name="Активні локації", value=locations, inline=False)
            notes = [alert.notes for alert in region.alerts if alert.notes]
            if notes:
                embed.add_field(name="Нотатки", value=_truncate(" | ".join(dict.fromkeys(notes)), 900), inline=False)
            embed.add_field(name="Початок", value=_format_local_time(region.started_at, self.timezone), inline=True)
            if region_hint is not None:
                embed.add_field(name="Ймовірна загроза", value=region_hint.label, inline=True)
                embed.add_field(name="Сигнал", value=_truncate(region_hint.excerpt, 280), inline=False)
        else:
            embed.add_field(name="Стан", value="Тривогу в цій області знято.", inline=False)
            duration = _format_duration(transition.previous_started_at, snapshot.fetched_at)
            if duration is not None:
                embed.add_field(name="Тривалість", value=duration, inline=True)

        embed.set_footer(text=f"{EMBED_FOOTER} • {snapshot.source_label}")
        return embed

    def build_transition_summary_embed(
        self,
        transitions: list[AirAlertTransition],
        snapshot: AirAlertSnapshot,
        intel_hints: tuple[ThreatIntelHint, ...] = (),
    ) -> discord.Embed:
        lines = []
        for transition in transitions[:18]:
            region_hint = self._best_region_hint(transition.region_title, intel_hints, snapshot.fetched_at)
            hint_suffix = f" · {region_hint.short_label}" if region_hint is not None else ""
            lines.append(
                f"• **{transition.region_title}**: "
                f"{STATUS_TEXT.get(transition.previous_status, transition.previous_status)} → "
                f"{STATUS_TEXT.get(transition.current_status, transition.current_status)}{hint_suffix}"
            )
        embed = discord.Embed(
            title="📡 Масове оновлення повітряних тривог",
            description="\n".join(lines),
            colour=discord.Colour.from_rgb(255, 128, 96),
            timestamp=snapshot.fetched_at,
        )
        embed.set_footer(text=f"{EMBED_FOOTER} • {snapshot.source_label}")
        return embed

    def build_intel_bulletin_embed(
        self,
        hint: ThreatIntelHint,
        snapshot: AirAlertSnapshot,
    ) -> discord.Embed:
        title_map = {
            "ballistic": "🟣 Єва | балістична загроза",
            "mig": "🛫 Єва | зліт МіГ-31К",
            "drone": "⚠️ Єва | БпЛА / шахеди",
            "cab": "💣 Єва | КАБ / КАР",
            "aviation": "✈️ Єва | авіаційна активність",
            "generic": "🚨 Єва | повітряна загроза",
        }
        intro_map = {
            "ballistic": "Це вже не просто сирена фоном. Якщо ти в зоні ризику, ховайся без зайвих пауз.",
            "mig": "Носій у повітрі, отже зайва сміливість зараз точно ні до чого.",
            "drone": "У небі знову ворожий мотлох. Краще бути ближче до укриття, ніж до вікна.",
            "cab": "Поганий сценарій для прифронтових і не тільки. Зараз потрібна холодна голова.",
            "aviation": "У небі недобрий рух, тож уважність зараз важливіша за будь-який спокій.",
            "generic": "Є новий тривожний сигнал. Перевір офіційні вказівки і не затягуй з реакцією.",
        }
        embed = discord.Embed(
            title=title_map.get(hint.kind, title_map["generic"]),
            description=intro_map.get(hint.kind, intro_map["generic"]),
            colour=INTEL_COLORS.get(hint.kind, INTEL_COLORS["generic"]),
            timestamp=hint.published_at,
        )
        embed.add_field(name="Ймовірна загроза", value=hint.label, inline=False)
        embed.add_field(name="Куди дивимось", value=self._format_hint_regions(hint, fallback="Поки без точного регіону"), inline=False)
        embed.add_field(name="Що бачимо", value=_truncate(hint.excerpt, 320), inline=False)

        matched_regions = [
            region_title
            for region_title in hint.regions
            if snapshot.regions.get(region_title) is not None and snapshot.regions[region_title].status != STATUS_NO_ALERT
        ]
        if matched_regions:
            region_lines = []
            for region_title in matched_regions[:6]:
                region = snapshot.regions[region_title]
                started = _format_local_time(region.started_at, self.timezone)
                region_lines.append(f"• **{region_title}** — {STATUS_TEXT[region.status]} · з {started}")
            embed.add_field(name="На мапі зараз", value="\n".join(region_lines), inline=False)

        embed.set_footer(text=EMBED_FOOTER)
        return embed

    async def render_map(
        self,
        snapshot: AirAlertSnapshot,
        intel_hints: tuple[ThreatIntelHint, ...] = (),
    ) -> AirAlertRenderResult:
        dependency_error = self.dependency_error()
        if dependency_error is not None:
            raise RuntimeError(dependency_error)

        assert Image is not None
        assert ImageDraw is not None
        assert ImageFilter is not None

        image = Image.new("RGBA", CANVAS_SIZE, (8, 12, 24, 255))
        self._paint_background(image)
        self._paint_map(image, snapshot)
        self._paint_sidebar(image, snapshot, intel_hints)

        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        signature_raw = snapshot.oblast_status_string + "|" + "|".join(
            f"{region.title}:{region.status}:{','.join(sorted({_alert_type_label(item.alert_type) for item in region.alerts}))}"
            for region in snapshot.regions.values()
            if region.status != STATUS_NO_ALERT
        )
        return AirAlertRenderResult(
            image_bytes=buffer.getvalue(),
            signature=f"sha1:{hashlib.sha1(signature_raw.encode('utf-8')).hexdigest()[:16]}",
            active_count=sum(1 for region in snapshot.regions.values() if region.status == STATUS_ACTIVE),
            partial_count=sum(1 for region in snapshot.regions.values() if region.status == STATUS_PARTIAL),
        )

    def _transition_description(self, transition: AirAlertTransition, region_hint: ThreatIntelHint | None = None) -> str:
        if transition.kind == "started":
            if transition.current_status == STATUS_ACTIVE:
                base = "У регіоні оголошена повітряна тривога по всій області."
            else:
                base = "У регіоні зафіксована часткова тривога."
            if region_hint is not None:
                return f"{base} По живих сигналах зараз це схоже на **{region_hint.short_label.lower()}**."
            return f"{base} Без героїзму: орієнтуйтесь на місцеві вказівки та укриття."
        if transition.kind == "scaled_up":
            if region_hint is not None:
                return f"Часткова тривога розрослась до рівня всієї області. По живих сигналах фокус зараз на **{region_hint.short_label.lower()}**."
            return "Часткова тривога розрослась до рівня всієї області. Ситуацію краще не недооцінювати."
        if transition.kind == "scaled_down":
            return "Тривога ще не знята повністю, але перейшла в частковий режим."
        if transition.kind == "ended":
            return "В області пролунав відбій. Все одно виходити з укриття варто тільки за правилами вашої місцевості."
        return "Статус тривоги в області змінився."

    def _load_regions(self) -> tuple[RegionGeometry, ...]:
        if not GEOJSON_PATH.exists():
            return ()
        payload = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
        regions: list[RegionGeometry] = []
        for feature in payload.get("features", []):
            properties = feature.get("properties") or {}
            iso = str(properties.get("shapeISO") or "").strip()
            title = REGION_TITLE_BY_SHAPE_ISO.get(iso)
            if title is None:
                continue
            rings_raw = _iter_exterior_rings(feature.get("geometry") or {})
            rings = tuple(tuple(ring) for ring in rings_raw if ring)
            if rings:
                regions.append(RegionGeometry(title=title, rings=rings))
        return tuple(regions)

    def _paint_background(self, image: Any) -> None:
        assert ImageDraw is not None
        assert ImageFilter is not None
        draw = ImageDraw.Draw(image)
        width, height = image.size
        draw.rectangle((0, 0, width, height), fill=(7, 10, 22, 255))

        orbs = Image.new("RGBA", image.size, (0, 0, 0, 0))
        orb_draw = ImageDraw.Draw(orbs)
        orb_draw.ellipse((-120, -80, 760, 700), fill=(54, 88, 180, 120))
        orb_draw.ellipse((960, 10, 1520, 540), fill=(255, 104, 136, 95))
        orb_draw.ellipse((1180, 520, 1760, 1020), fill=(92, 204, 255, 90))
        image.alpha_composite(orbs.filter(ImageFilter.GaussianBlur(70)))

    def _paint_map(self, image: Any, snapshot: AirAlertSnapshot) -> None:
        assert ImageDraw is not None
        assert ImageFilter is not None
        if not self._regions:
            return

        min_lon = min(point[0] for region in self._regions for ring in region.rings for point in ring)
        max_lon = max(point[0] for region in self._regions for ring in region.rings for point in ring)
        min_lat = min(point[1] for region in self._regions for ring in region.rings for point in ring)
        max_lat = max(point[1] for region in self._regions for ring in region.rings for point in ring)

        map_left, map_top, map_right, map_bottom = MAP_BOX
        map_width = map_right - map_left
        map_height = map_bottom - map_top
        scale = min(map_width / (max_lon - min_lon), map_height / (max_lat - min_lat))
        used_width = (max_lon - min_lon) * scale
        used_height = (max_lat - min_lat) * scale
        offset_x = map_left + (map_width - used_width) / 2
        offset_y = map_top + (map_height - used_height) / 2

        glow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        base_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        base_draw = ImageDraw.Draw(base_layer)

        for region in self._regions:
            region_snapshot = snapshot.regions.get(region.title)
            status = region_snapshot.status if region_snapshot is not None else STATUS_NO_ALERT
            fill = STATUS_FILL[status]
            glow_fill = STATUS_GLOW[status]
            for ring in region.rings:
                transformed = [
                    (
                        offset_x + (lon - min_lon) * scale,
                        offset_y + (max_lat - lat) * scale,
                    )
                    for lon, lat in ring
                ]
                glow_draw.polygon(transformed, fill=glow_fill)
                base_draw.polygon(transformed, fill=fill, outline=(230, 238, 255, 180))

        image.alpha_composite(glow_layer.filter(ImageFilter.GaussianBlur(18)))
        image.alpha_composite(base_layer)

        draw = ImageDraw.Draw(image)
        title_font = self._load_font(38)
        subtitle_font = self._load_font(20)
        draw.text((MAP_BOX[0], 56), self.config.air_alert.title, font=title_font, fill=(243, 247, 255, 255))
        draw.text(
            (MAP_BOX[0], 96),
            "Червоний — тривога по області, бурштиновий — часткова, синій — спокійно",
            font=subtitle_font,
            fill=(171, 187, 226, 255),
        )

    def _paint_sidebar(
        self,
        image: Any,
        snapshot: AirAlertSnapshot,
        intel_hints: tuple[ThreatIntelHint, ...],
    ) -> None:
        assert ImageDraw is not None
        assert ImageFilter is not None

        panel = Image.new("RGBA", image.size, (0, 0, 0, 0))
        panel_draw = ImageDraw.Draw(panel)
        panel_draw.rounded_rectangle(
            (CARD_X, 84, CARD_X + CARD_WIDTH, 816),
            radius=44,
            fill=(16, 22, 38, 182),
            outline=(245, 248, 255, 58),
            width=1,
        )
        image.alpha_composite(panel.filter(ImageFilter.GaussianBlur(2)))
        draw = ImageDraw.Draw(image)
        title_font = self._load_font(28)
        value_font = self._load_font(52)
        label_font = self._load_font(18)
        text_font = self._load_font(20)
        tiny_font = self._load_font(16)
        chip_font = self._load_font(15)

        active_count = sum(1 for region in snapshot.regions.values() if region.status == STATUS_ACTIVE)
        partial_count = sum(1 for region in snapshot.regions.values() if region.status == STATUS_PARTIAL)
        calm_count = len(OBLAST_STATUS_ORDER) - active_count - partial_count

        draw.text((CARD_X + 32, 116), "Живий статус по областях", font=title_font, fill=(242, 246, 255, 255))
        draw.text((CARD_X + 32, 154), _format_local_time(snapshot.fetched_at, self.timezone), font=label_font, fill=(154, 170, 212, 255))

        self._draw_stat_pill(draw, CARD_X + 32, 198, 130, 108, "Активно", str(active_count), (255, 96, 118, 255), value_font, label_font)
        self._draw_stat_pill(draw, CARD_X + 186, 198, 130, 108, "Частково", str(partial_count), (255, 183, 77, 255), value_font, label_font)
        self._draw_stat_pill(draw, CARD_X + 340, 198, 130, 108, "Спокійно", str(calm_count), (119, 216, 156, 255), value_font, label_font)

        draw.text((CARD_X + 32, 338), "Гарячі області", font=title_font, fill=(242, 246, 255, 255))
        y = 384
        hot_cards = self._hot_region_cards(snapshot, intel_hints)
        hot_limit = min(self.config.air_alert.hot_regions_limit, 5)
        if not hot_cards:
            draw.text((CARD_X + 32, y), "По областях зараз без активної тривоги.", font=text_font, fill=(195, 207, 236, 255))
            y += 42
        else:
            for card in hot_cards[:hot_limit]:
                self._draw_hot_region_card(draw, card, CARD_X + 26, y, CARD_WIDTH - 52, chip_font, text_font, tiny_font)
                y += 52
            remaining = len(hot_cards) - hot_limit
            if remaining > 0:
                draw.text(
                    (CARD_X + 32, y + 6),
                    f"+ ще {remaining} областей під тривогою",
                    font=text_font,
                    fill=(195, 207, 236, 255),
                )
                y += 42

        freshest = self._latest_hint(intel_hints)
        section_y = max(y + 18, 694)
        draw.line((CARD_X + 32, section_y - 10, CARD_X + CARD_WIDTH - 32, section_y - 10), fill=(255, 255, 255, 26), width=1)
        draw.text((CARD_X + 32, section_y), "Свіжий сигнал", font=title_font, fill=(242, 246, 255, 255))
        section_y += 42
        if freshest is None:
            draw.text((CARD_X + 32, section_y), "Живих уточнень по загрозі зараз немає.", font=text_font, fill=(195, 207, 236, 255))
        else:
            draw.text((CARD_X + 32, section_y + 2), freshest.short_label, font=text_font, fill=(243, 247, 255, 255))
            draw.text(
                (CARD_X + 164, section_y + 4),
                self._format_hint_regions(freshest, fallback="без точного регіону"),
                font=tiny_font,
                fill=(163, 178, 214, 255),
            )
            draw.text(
                (CARD_X + 32, section_y + 28),
                _truncate(freshest.excerpt, 72),
                font=tiny_font,
                fill=(184, 198, 230, 255),
            )

    def _draw_stat_block(
        self,
        draw: Any,
        x: int,
        y: int,
        label: str,
        value: str,
        color: tuple[int, int, int, int],
        value_font: Any,
        label_font: Any,
    ) -> None:
        draw.text((x, y), value, font=value_font, fill=color)
        draw.text((x, y + 66), label, font=label_font, fill=(177, 191, 226, 255))

    def _draw_stat_pill(
        self,
        draw: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        label: str,
        value: str,
        color: tuple[int, int, int, int],
        value_font: Any,
        label_font: Any,
    ) -> None:
        draw.rounded_rectangle(
            (x, y, x + width, y + height),
            radius=26,
            fill=(24, 32, 56, 168),
            outline=(245, 248, 255, 36),
            width=1,
        )
        draw.text((x + 18, y + 12), value, font=value_font, fill=color)
        draw.text((x + 18, y + 74), label, font=label_font, fill=(177, 191, 226, 255))

    def _draw_hot_region_card(
        self,
        draw: Any,
        card: dict[str, str | tuple[int, int, int, int]],
        x: int,
        y: int,
        width: int,
        chip_font: Any,
        text_font: Any,
        tiny_font: Any,
    ) -> None:
        accent = card["accent"]
        assert isinstance(accent, tuple)
        draw.rounded_rectangle((x + 4, y + 8, x + 12, y + 32), radius=4, fill=accent)
        draw.text((x + 26, y + 2), str(card["title"]), font=text_font, fill=(243, 247, 255, 255))
        draw.text((x + 26, y + 24), str(card["subtitle"]), font=tiny_font, fill=(177, 191, 226, 255))

        chip_text = str(card["chip"])
        chip_width = max(70, min(144, 10 + len(chip_text) * 8))
        chip_left = x + width - chip_width
        draw.text((chip_left, y + 10), chip_text, font=chip_font, fill=(214, 225, 246, 255))
        draw.line((x, y + 44, x + width, y + 44), fill=(255, 255, 255, 22), width=1)

    def _hot_region_cards(
        self,
        snapshot: AirAlertSnapshot,
        intel_hints: tuple[ThreatIntelHint, ...],
    ) -> list[dict[str, str | tuple[int, int, int, int]]]:
        cards: list[dict[str, str | tuple[int, int, int, int]]] = []
        for region_title in OBLAST_STATUS_ORDER:
            region = snapshot.regions[region_title]
            if region.status == STATUS_NO_ALERT:
                continue
            hint = self._best_region_hint(region_title, intel_hints, snapshot.fetched_at)
            chip = hint.short_label if hint is not None else self._primary_alert_label(region)
            started = _format_local_time(region.started_at, self.timezone)
            status_label = "вся область" if region.status == STATUS_ACTIVE else "часткова"
            cards.append(
                {
                    "title": region.title,
                    "subtitle": f"{status_label} • з {started}",
                    "chip": chip,
                    "accent": STATUS_FILL[region.status],
                    "sort_key": (
                        0 if region.status == STATUS_ACTIVE else 1,
                        -threat_priority(hint.kind) if hint is not None else 0,
                        -(region.started_at.timestamp() if region.started_at is not None else 0.0),
                    ),
                }
            )
        cards.sort(key=lambda item: item["sort_key"])
        for card in cards:
            card.pop("sort_key", None)
        return cards

    def _primary_alert_label(self, region: RegionSnapshot) -> str:
        if region.alerts:
            return ALERT_TYPE_SHORT_LABELS.get(region.alerts[0].alert_type, _alert_type_label(region.alerts[0].alert_type))
        return STATUS_TEXT.get(region.status, "Тривога")

    def _fresh_intel_hints(
        self,
        intel_hints: tuple[ThreatIntelHint, ...],
        snapshot_time: datetime,
    ) -> tuple[ThreatIntelHint, ...]:
        max_age = timedelta(seconds=self.config.air_alert.intel_max_age_seconds)
        hints = [
            hint
            for hint in intel_hints
            if snapshot_time - hint.published_at <= max_age
        ]
        hints.sort(key=lambda item: (item.published_at, threat_priority(item.kind)), reverse=True)
        return tuple(hints)

    def _freshest_hint(
        self,
        intel_hints: tuple[ThreatIntelHint, ...],
        snapshot_time: datetime,
    ) -> ThreatIntelHint | None:
        hints = self._fresh_intel_hints(intel_hints, snapshot_time)
        return hints[0] if hints else None

    @staticmethod
    def _latest_hint(intel_hints: tuple[ThreatIntelHint, ...]) -> ThreatIntelHint | None:
        if not intel_hints:
            return None
        return max(intel_hints, key=lambda item: item.published_at)

    def _best_region_hint(
        self,
        region_title: str,
        intel_hints: tuple[ThreatIntelHint, ...],
        snapshot_time: datetime,
    ) -> ThreatIntelHint | None:
        candidates: list[ThreatIntelHint] = []
        for hint in self._fresh_intel_hints(intel_hints, snapshot_time):
            if region_title in hint.regions or hint.is_national:
                candidates.append(hint)
        if not candidates:
            return None
        candidates.sort(key=lambda item: (threat_priority(item.kind), item.published_at), reverse=True)
        return candidates[0]

    @staticmethod
    def _format_hint_regions(hint: ThreatIntelHint, fallback: str = "вся країна") -> str:
        if hint.regions:
            if len(hint.regions) == 1:
                return hint.regions[0]
            if len(hint.regions) == 2:
                return f"{hint.regions[0]} + {hint.regions[1]}"
            return f"{hint.regions[0]} + ще {len(hint.regions) - 1}"
        if hint.is_national:
            return "вся країна"
        return fallback

    def _load_font(self, size: int) -> Any:
        assert ImageFont is not None
        for candidate in FONT_CANDIDATES:
            try:
                if candidate.exists():
                    return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
        return ImageFont.load_default()
