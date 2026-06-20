"""
EVA Assistant live server banner service.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import aiohttp
import discord

from roseblade_bot import APP_NAME, BRAND_SIGNATURE
from roseblade_bot.config import BotConfig
from roseblade_bot.services.http import fetch_bytes

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except ImportError:  # pragma: no cover - soft dependency in local dev
    Image = None
    ImageDraw = None
    ImageFilter = None
    ImageFont = None
    ImageOps = None


CANVAS_SIZE = (1920, 1080)
CARD_SIZE = (560, 250)
CARD_RADIUS = 56
CARD_MARGIN_X = 120
CARD_VERTICAL_OFFSET = 115
VALUE_VERTICAL_OFFSET = 0
MODULE_DIR = Path(__file__).resolve().parent
ASSET_DIR = MODULE_DIR / "assets"
BUNDLED_BACKGROUND_PATH = ASSET_DIR / "background.png"
BUNDLED_ICON_PATHS = {
    "microphone": ASSET_DIR / "microphone.png",
    "member": ASSET_DIR / "user.png",
}
FONT_CANDIDATES = (
    Path("assets/fonts/Unbounded-Bold.ttf"),
    Path("assets/fonts/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
)
ROSE = (255, 114, 163, 255)
ROSE_SOFT = (255, 186, 214, 255)
MIST = (249, 240, 245, 255)
GOLD = (255, 220, 116, 255)
CYAN = (108, 223, 255, 255)
GREEN = (110, 236, 164, 255)
TIFFANY = (132, 232, 221, 255)
ROSE_GOLD = (221, 177, 159, 255)


@dataclass(frozen=True, slots=True)
class ServerBannerStats:
    title: str
    member_count: int
    online_count: int | None
    voice_count: int
    boost_level: int
    boost_count: int
    rendered_at: datetime


@dataclass(frozen=True, slots=True)
class ServerBannerRenderResult:
    image_bytes: bytes
    stats: ServerBannerStats
    signature: str


class ServerBannerService:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self._background_cache_bytes: bytes | None = None
        self._background_cache_expires_at: datetime | None = None
        self._icon_cache: dict[str, Any] = {}

    @property
    def is_enabled(self) -> bool:
        return self.config.server_banner_enabled

    @property
    def dependencies_ready(self) -> bool:
        return all(module is not None for module in (Image, ImageDraw, ImageFilter, ImageFont, ImageOps))

    @property
    def online_count_supported(self) -> bool:
        return self.config.enable_members_intent and self.config.enable_presences_intent

    def channel_count(self) -> int:
        return 1 if self.is_enabled else 0

    def schedule_label(self) -> str:
        return f"every {self.config.server_banner_update_minutes}m"

    def custom_background_label(self) -> str:
        if self.config.server_banner_background_path is not None:
            return str(self.config.server_banner_background_path)
        if BUNDLED_BACKGROUND_PATH.exists():
            return str(BUNDLED_BACKGROUND_PATH)
        if self.config.server_banner_background_url:
            return self.config.server_banner_background_url
        return "fallback"

    def dependency_error(self) -> str | None:
        if self.dependencies_ready:
            return None
        return "Pillow не установлен. Обнови зависимости через `pip install -r requirements.txt`."

    async def collect_stats(self, guild: discord.Guild) -> ServerBannerStats:
        if self.online_count_supported and not guild.chunked:
            try:
                await guild.chunk(cache=True)
            except (discord.Forbidden, discord.HTTPException):
                pass

        member_count = int(guild.member_count or len(guild.members))
        online_count: int | None = None
        if self.online_count_supported:
            online_count = sum(
                1
                for member in guild.members
                if getattr(member, "status", discord.Status.offline) is not discord.Status.offline
            )

        connected_ids = {
            member.id
            for channel in [*guild.voice_channels, *guild.stage_channels]
            for member in channel.members
        }
        title = (self.config.server_banner_title.strip() or guild.name).strip().upper()
        return ServerBannerStats(
            title=title,
            member_count=member_count,
            online_count=online_count,
            voice_count=len(connected_ids),
            boost_level=int(getattr(guild, "premium_tier", 0) or 0),
            boost_count=int(getattr(guild, "premium_subscription_count", 0) or 0),
            rendered_at=datetime.now(timezone.utc),
        )

    def signature(self, stats: ServerBannerStats) -> str:
        return "|".join(
            [
                stats.title,
                str(stats.member_count),
                str(stats.online_count if stats.online_count is not None else "na"),
                str(stats.voice_count),
                str(stats.boost_level),
                str(stats.boost_count),
            ]
        )

    async def render_banner(self, guild: discord.Guild) -> ServerBannerRenderResult:
        dependency_error = self.dependency_error()
        if dependency_error is not None:
            raise RuntimeError(dependency_error)

        stats = await self.collect_stats(guild)
        background = await self._load_background_image()
        image = self._compose_banner(background, stats)
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        image_bytes = buffer.getvalue()
        return ServerBannerRenderResult(
            image_bytes=image_bytes,
            stats=stats,
            signature=self.signature(stats),
        )

    async def _load_background_image(self) -> Any:
        background_data = await self._background_bytes()
        if background_data is not None:
            opened = self._open_image(background_data)
            if opened is not None:
                return opened
        return self._build_fallback_background()

    async def _background_bytes(self) -> bytes | None:
        now = datetime.now(timezone.utc)
        if self._background_cache_bytes is not None and self._background_cache_expires_at is not None:
            if now <= self._background_cache_expires_at:
                return self._background_cache_bytes

        if self.config.server_banner_background_path is not None and self.config.server_banner_background_path.exists():
            data = self.config.server_banner_background_path.read_bytes()
            self._cache_background(data, now)
            return data

        if BUNDLED_BACKGROUND_PATH.exists():
            data = BUNDLED_BACKGROUND_PATH.read_bytes()
            self._cache_background(data, now)
            return data

        if self.config.server_banner_background_url:
            headers = {"User-Agent": f"{APP_NAME} live banner / {BRAND_SIGNATURE}"}
            try:
                data, _ = await fetch_bytes(
                    self.config.server_banner_background_url,
                    headers=headers,
                    timeout_total=15,
                )
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):  # type: ignore[name-defined]
                return self._background_cache_bytes

            if data:
                self._cache_background(data, now)
                return data

        return self._background_cache_bytes

    def _cache_background(self, data: bytes, now: datetime) -> None:
        cache_minutes = max(15, self.config.server_banner_update_minutes * 3)
        self._background_cache_bytes = data
        self._background_cache_expires_at = now + timedelta(minutes=cache_minutes)

    def _open_image(self, data: bytes) -> Any | None:
        if Image is None:
            return None
        try:
            return Image.open(BytesIO(data)).convert("RGBA")
        except Exception:
            return None

    def _build_fallback_background(self) -> Any:
        assert Image is not None
        assert ImageDraw is not None
        assert ImageFilter is not None

        image = Image.new("RGBA", CANVAS_SIZE, (18, 8, 14, 255))
        draw = ImageDraw.Draw(image)
        width, height = CANVAS_SIZE

        for index, color in enumerate(((44, 16, 30, 255), (16, 12, 26, 255), (58, 18, 42, 255))):
            ellipse = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
            ellipse_draw = ImageDraw.Draw(ellipse)
            size = 520 + index * 180
            ellipse_draw.ellipse(
                (
                    width - (size + 120 * index),
                    90 + 120 * index,
                    width - 120 * index,
                    90 + 120 * index + size,
                ),
                fill=color,
            )
            ellipse = ellipse.filter(ImageFilter.GaussianBlur(60))
            image.alpha_composite(ellipse)

        draw.rectangle((0, 0, width, height), fill=(8, 4, 10, 96))
        draw.line((width - 380, 140, width - 70, 450), fill=(255, 120, 172, 90), width=8)
        draw.line((width - 320, 120, width - 10, 430), fill=(255, 225, 236, 52), width=3)
        draw.line((width - 520, 720, width - 210, 1030), fill=(255, 120, 172, 74), width=10)
        draw.line((width - 470, 700, width - 160, 1010), fill=(255, 225, 236, 42), width=3)
        return image

    def _compose_banner(self, background: Any, stats: ServerBannerStats) -> Any:
        assert Image is not None
        assert ImageDraw is not None
        assert ImageFilter is not None
        assert ImageFont is not None
        assert ImageOps is not None

        image = self._cover_background(background)
        image.alpha_composite(self._build_scene_overlay())

        card_width, card_height = CARD_SIZE
        card_top = ((CANVAS_SIZE[1] - card_height) // 2) + CARD_VERTICAL_OFFSET
        left_box = (
            CARD_MARGIN_X,
            card_top,
            CARD_MARGIN_X + card_width,
            card_top + card_height,
        )
        right_box = (
            CANVAS_SIZE[0] - CARD_MARGIN_X - card_width,
            card_top,
            CANVAS_SIZE[0] - CARD_MARGIN_X,
            card_top + card_height,
        )

        self._draw_glass_metric_card(
            image,
            box=left_box,
            value=self._format_number(stats.voice_count),
            accent=TIFFANY,
            icon_kind="microphone",
        )
        self._draw_glass_metric_card(
            image,
            box=right_box,
            value=self._format_number(stats.member_count),
            accent=ROSE_GOLD,
            icon_kind="member",
        )
        return image

    def _cover_background(self, background: Any) -> Any:
        assert Image is not None
        assert ImageOps is not None

        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        return ImageOps.fit(background, CANVAS_SIZE, method=resample, centering=(0.5, 0.5))

    def _build_scene_overlay(self) -> Any:
        assert Image is not None
        assert ImageDraw is not None
        assert ImageFilter is not None

        overlay = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle((0, 0, *CANVAS_SIZE), fill=(8, 8, 12, 58))

        sheen = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        sheen_draw = ImageDraw.Draw(sheen)
        sheen_draw.ellipse(
            (220, -260, CANVAS_SIZE[0] - 220, 460),
            fill=(255, 255, 255, 32),
        )
        overlay.alpha_composite(sheen.filter(ImageFilter.GaussianBlur(72)))

        lower_haze = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        lower_haze_draw = ImageDraw.Draw(lower_haze)
        lower_haze_draw.ellipse(
            (360, 720, CANVAS_SIZE[0] - 360, CANVAS_SIZE[1] + 160),
            fill=(255, 255, 255, 16),
        )
        overlay.alpha_composite(lower_haze.filter(ImageFilter.GaussianBlur(88)))

        vignette = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        vignette_draw = ImageDraw.Draw(vignette)
        vignette_draw.rounded_rectangle(
            (36, 28, CANVAS_SIZE[0] - 36, CANVAS_SIZE[1] - 28),
            radius=92,
            outline=(255, 255, 255, 22),
            width=2,
        )
        overlay.alpha_composite(vignette)
        return overlay

    def _draw_glass_metric_card(
        self,
        image: Any,
        *,
        box: tuple[int, int, int, int],
        value: str,
        accent: tuple[int, int, int, int],
        icon_kind: str,
    ) -> None:
        assert Image is not None
        assert ImageDraw is not None
        assert ImageFilter is not None

        x1, y1, x2, y2 = box
        width = x2 - x1
        height = y2 - y1
        radius = CARD_RADIUS

        outer_glow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        outer_glow_draw = ImageDraw.Draw(outer_glow)
        outer_glow_draw.rounded_rectangle(
            (x1 - 8, y1 - 8, x2 + 8, y2 + 8),
            radius=radius + 10,
            fill=(accent[0], accent[1], accent[2], 20),
            outline=(accent[0], accent[1], accent[2], 80),
            width=3,
        )
        image.alpha_composite(outer_glow.filter(ImageFilter.GaussianBlur(24)))

        shadow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            (x1 + 4, y1 + 12, x2 + 4, y2 + 18),
            radius=radius,
            fill=(8, 10, 18, 64),
        )
        image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(26)))

        blurred = image.crop(box).filter(ImageFilter.GaussianBlur(22))
        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
        image.paste(blurred, box, mask)

        card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card)
        card_draw.rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=radius,
            fill=(255, 255, 255, 24),
            outline=(255, 255, 255, 104),
            width=2,
        )
        card_draw.rounded_rectangle(
            (12, 10, width - 13, height - 13),
            radius=radius - 10,
            outline=(255, 255, 255, 40),
            width=1,
        )
        card_draw.rounded_rectangle(
            (18, 16, width - 19, (height // 2) + 10),
            radius=radius - 16,
            fill=(255, 255, 255, 28),
        )

        accent_glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        accent_draw = ImageDraw.Draw(accent_glow)
        accent_draw.ellipse((34, 58, 184, 198), fill=(accent[0], accent[1], accent[2], 74))
        accent_glow = accent_glow.filter(ImageFilter.GaussianBlur(20))
        card.alpha_composite(accent_glow)

        icon_box = (38, 50, 194, 206)
        self._draw_icon_chip(card, icon_box=icon_box, accent=accent, icon_kind=icon_kind)

        value_font = self._load_font(102, bold=True)
        value_draw = ImageDraw.Draw(card)
        text_box = value_draw.textbbox((0, 0), value, font=value_font, stroke_width=1)
        text_height = text_box[3] - text_box[1]
        text_y = (height - text_height) // 2 - text_box[1] - 4 + VALUE_VERTICAL_OFFSET
        value_draw.text(
            (228, text_y),
            value,
            font=value_font,
            fill=MIST,
            stroke_width=1,
            stroke_fill=(0, 0, 0, 105),
        )

        image.alpha_composite(card, dest=(x1, y1))

    def _draw_icon_chip(
        self,
        image: Any,
        *,
        icon_box: tuple[int, int, int, int],
        accent: tuple[int, int, int, int],
        icon_kind: str,
    ) -> None:
        assert ImageDraw is not None

        draw = ImageDraw.Draw(image)
        x1, y1, x2, y2 = icon_box
        draw.rounded_rectangle(
            icon_box,
            radius=44,
            fill=(accent[0], accent[1], accent[2], 22),
            outline=(255, 255, 255, 82),
            width=2,
        )
        draw.rounded_rectangle((x1 + 9, y1 + 9, x2 - 9, y2 - 9), radius=36, outline=(255, 255, 255, 34), width=1)
        draw.ellipse((x1 + 12, y1 + 10, x2 - 22, y1 + 76), fill=(255, 255, 255, 16))

        if self._paste_icon_asset(image, icon_box=icon_box, accent=accent, icon_kind=icon_kind):
            return
        if icon_kind == "microphone":
            self._draw_microphone_icon(draw, icon_box=icon_box, accent=accent)
            return
        self._draw_member_icon(draw, icon_box=icon_box, accent=accent)

    def _paste_icon_asset(
        self,
        image: Any,
        *,
        icon_box: tuple[int, int, int, int],
        accent: tuple[int, int, int, int],
        icon_kind: str,
    ) -> bool:
        assert Image is not None
        assert ImageFilter is not None
        assert ImageOps is not None

        source = self._icon_asset(icon_kind)
        if source is None:
            return False

        x1, y1, x2, y2 = icon_box
        box_width = x2 - x1
        box_height = y2 - y1
        target_size = (box_width - 48, box_height - 48)
        prepared = ImageOps.contain(source, target_size, method=Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)
        alpha = prepared.getchannel("A")
        if alpha.getbbox() is None:
            return False

        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        glow_icon = Image.new("RGBA", prepared.size, (accent[0], accent[1], accent[2], 122))
        glow_icon.putalpha(alpha)
        glow.paste(
            glow_icon,
            (
                x1 + (box_width - prepared.width) // 2,
                y1 + (box_height - prepared.height) // 2 + 2,
            ),
            glow_icon,
        )
        image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))

        symbol = Image.new("RGBA", prepared.size, (247, 242, 247, 240))
        symbol.putalpha(alpha)
        shadow = Image.new("RGBA", prepared.size, (0, 0, 0, 68))
        shadow.putalpha(alpha)

        shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_layer.paste(
            shadow,
            (
                x1 + (box_width - prepared.width) // 2,
                y1 + (box_height - prepared.height) // 2 + 5,
            ),
            shadow,
        )
        image.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(4)))

        image.alpha_composite(
            symbol,
            dest=(
                x1 + (box_width - prepared.width) // 2,
                y1 + (box_height - prepared.height) // 2,
            ),
        )
        return True

    def _icon_asset(self, icon_kind: str) -> Any | None:
        assert Image is not None

        cached = self._icon_cache.get(icon_kind)
        if cached is not None:
            return cached.copy()

        path = BUNDLED_ICON_PATHS.get(icon_kind)
        if path is None or not path.exists():
            return None
        try:
            icon = Image.open(path).convert("RGBA")
        except Exception:
            return None

        alpha = icon.getchannel("A")
        bbox = alpha.getbbox()
        if bbox is not None:
            icon = icon.crop(bbox)

        self._icon_cache[icon_kind] = icon
        return icon.copy()

    def _draw_microphone_icon(
        self,
        draw: Any,
        *,
        icon_box: tuple[int, int, int, int],
        accent: tuple[int, int, int, int],
    ) -> None:
        x1, y1, x2, y2 = icon_box
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2 - 2
        symbol = (246, 243, 247, 236)
        shadow = (accent[0], accent[1], accent[2], 90)

        draw.rounded_rectangle((cx - 22, cy - 46, cx + 22, cy + 10), radius=22, fill=shadow)
        draw.rounded_rectangle((cx - 18, cy - 42, cx + 18, cy + 6), radius=18, fill=symbol)
        draw.rounded_rectangle((cx - 4, cy + 8, cx + 4, cy + 36), radius=4, fill=symbol)
        draw.arc((cx - 36, cy - 4, cx + 36, cy + 48), start=18, end=162, fill=symbol, width=6)
        draw.line((cx - 20, cy + 46, cx + 20, cy + 46), fill=symbol, width=6)
        draw.line((cx, cy + 36, cx, cy + 46), fill=symbol, width=6)
        draw.ellipse((cx - 10, cy - 34, cx + 10, cy - 14), fill=(255, 255, 255, 54))

    def _draw_member_icon(
        self,
        draw: Any,
        *,
        icon_box: tuple[int, int, int, int],
        accent: tuple[int, int, int, int],
    ) -> None:
        x1, y1, x2, y2 = icon_box
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2 - 2
        symbol = (246, 243, 247, 236)
        shadow = (accent[0], accent[1], accent[2], 84)

        draw.ellipse((cx - 25, cy - 48, cx + 25, cy + 2), fill=shadow)
        draw.ellipse((cx - 20, cy - 43, cx + 20, cy - 3), fill=symbol)
        draw.pieslice((cx - 54, cy - 2, cx + 54, cy + 78), start=203, end=337, fill=shadow)
        draw.pieslice((cx - 46, cy + 4, cx + 46, cy + 70), start=205, end=335, fill=symbol)
        draw.ellipse((cx - 10, cy - 36, cx + 8, cy - 18), fill=(255, 255, 255, 54))

    def _load_font(self, size: int, *, bold: bool = False) -> Any:
        assert ImageFont is not None

        candidates: list[Path] = []
        if self.config.server_banner_font_path is not None:
            candidates.append(self.config.server_banner_font_path)
        candidates.extend(FONT_CANDIDATES)

        for candidate in candidates:
            try:
                if candidate.exists():
                    return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue

        return ImageFont.load_default()

    @staticmethod
    def _format_number(value: int | None) -> str:
        if value is None:
            return "—"
        return f"{value:,}".replace(",", " ")
