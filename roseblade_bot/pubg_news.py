"""
EVA Assistant PUBG news monitor.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import re
from typing import Any
from urllib.parse import urljoin

import discord

from roseblade_bot import EMBED_FOOTER
from roseblade_bot.config import BotConfig
from roseblade_bot.services.http import HttpRequestError, fetch_bytes, fetch_json


_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"(?P<name>[\w:-]+)\s*=\s*(['\"])(?P<value>.*?)\2", re.IGNORECASE | re.DOTALL)
_OFFICIAL_NEWS_LINK_RE = re.compile(r"(?:https://pubg\.com)?/ru/news/(?P<post_id>\d+)", re.IGNORECASE)
_OFFICIAL_NEWS_DATA_RE = re.compile(r"news:\{posts:\[(?P<posts>[\s\S]*?)\],size:", re.IGNORECASE)
_OFFICIAL_POST_ID_RE = re.compile(r"\bpostId:(?P<post_id>\d+)")
_OFFICIAL_CARD_RE = re.compile(
    r'<li class="post-contents__card"[\s\S]*?<img src="(?P<image>[^"]+)"[\s\S]*?'
    r'<dl class="post__description"[^>]*>\s*<dt[^>]*>(?P<title>[\s\S]*?)</dt>\s*'
    r'<dd[^>]*>(?P<excerpt>[\s\S]*?)</dd>[\s\S]*?'
    r'<dl class="post__bottom"[^>]*>[\s\S]*?<dd[^>]*>(?P<date>\d{4}\.\d{2}\.\d{2})</dd>',
    re.IGNORECASE,
)
_TG_POST_RE = re.compile(
    r'<div class="tgme_widget_message[^\"]*"[^>]*data-post="(?P<slug>[^"/]+)/(?P<post_id>\d+)"(?P<before_text>[\s\S]*?)'
    r'<div class="tgme_widget_message_text js-message_text" dir="auto">(?P<text_html>[\s\S]*?)</div>'
    r'(?P<tail>[\s\S]*?)<time datetime="(?P<published_at>[^"]+)"',
    re.IGNORECASE,
)
_TG_PHOTO_RE = re.compile(r"background-image:url\('(?P<url>[^']+)'\)", re.IGNORECASE)
_OFFICIAL_BODY_RE = re.compile(
    r'<div class="content-template__inner fr-view"[^>]*>(?P<body>[\s\S]*?)<div class="news-detail__banner"',
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BLOCK_END_RE = re.compile(r"</(?:p|div|li|h[1-6]|tr|blockquote)\s*>", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class PubgNewsPost:
    source: str
    post_id: str
    title: str
    excerpt: str
    url: str
    image_url: str | None
    published_at: datetime

    @property
    def key(self) -> str:
        return f"{self.source}:{self.post_id}"


class PubgNewsService:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self._translation_cache: dict[str, str] = {}

    @property
    def is_enabled(self) -> bool:
        return self.config.pubg_news.enabled

    @property
    def is_configured(self) -> bool:
        return self.is_enabled and bool(self.config.pubg_news.channel_ids)

    def channel_count(self) -> int:
        return len(self.config.pubg_news.channel_ids)

    def schedule_label(self) -> str:
        return f"every {self.config.pubg_news.poll_minutes}m"

    async def fetch_recent_posts(self) -> tuple[list[PubgNewsPost], list[str]]:
        tasks = [self._fetch_official_posts()]
        if self.config.pubg_news.include_telegram:
            tasks.append(self._fetch_telegram_posts())
        results = await asyncio.gather(*tasks, return_exceptions=True)

        posts: list[PubgNewsPost] = []
        errors: list[str] = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            else:
                posts.extend(result)
        posts.sort(key=lambda item: item.published_at)
        return posts, errors

    async def _fetch_official_posts(self) -> list[PubgNewsPost]:
        listing_html = await self._fetch_html(self.config.pubg_news.official_news_url)
        urls: list[tuple[str, str]] = []
        seen_ids: set[str] = set()
        for match in _OFFICIAL_NEWS_LINK_RE.finditer(listing_html):
            post_id = match.group("post_id")
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            urls.append((post_id, f"https://pubg.com/ru/news/{post_id}"))
            if len(urls) >= 6:
                break

        if not urls:
            posts = self._parse_official_listing(listing_html)
            if posts:
                return posts

        posts: list[PubgNewsPost] = []
        for post_id, url in urls:
            try:
                html = await self._fetch_html(url)
                post = self._parse_official_post(post_id, url, html)
            except Exception:
                continue
            if post is not None:
                posts.append(post)
        if not posts:
            raise RuntimeError("PUBG official news page did not return readable posts")
        return posts

    @classmethod
    def _parse_official_listing(cls, html: str) -> list[PubgNewsPost]:
        data_match = _OFFICIAL_NEWS_DATA_RE.search(html)
        if data_match is None:
            return []
        post_ids = [match.group("post_id") for match in _OFFICIAL_POST_ID_RE.finditer(data_match.group("posts"))]
        cards = list(_OFFICIAL_CARD_RE.finditer(html))
        posts: list[PubgNewsPost] = []
        for post_id, card in zip(post_ids, cards, strict=False):
            title = cls._clean_html_text(card.group("title"))
            excerpt = cls._clean_html_text(card.group("excerpt"))
            if not title or not excerpt:
                continue
            posts.append(
                PubgNewsPost(
                    source="official",
                    post_id=post_id,
                    title=title,
                    excerpt=excerpt,
                    url=f"https://pubg.com/ru/news/{post_id}",
                    image_url=unescape(card.group("image")),
                    published_at=cls._parse_datetime(card.group("date")),
                )
            )
            if len(posts) >= 8:
                break
        return posts

    async def _fetch_telegram_posts(self) -> list[PubgNewsPost]:
        username = self.config.pubg_news.telegram_username
        html = await self._fetch_html(f"https://t.me/s/{username}")
        posts: list[PubgNewsPost] = []
        for match in _TG_POST_RE.finditer(html):
            if match.group("slug").lower() != username.lower():
                continue
            text = self._clean_html_text(match.group("text_html"))
            if not text:
                continue
            title, excerpt = self._telegram_title_and_excerpt(text)
            photo_match = _TG_PHOTO_RE.search(match.group("before_text") + match.group("tail"))
            image_url = unescape(photo_match.group("url")) if photo_match else None
            posts.append(
                PubgNewsPost(
                    source="telegram",
                    post_id=match.group("post_id"),
                    title=title,
                    excerpt=excerpt,
                    url=f"https://t.me/{username}/{match.group('post_id')}",
                    image_url=image_url,
                    published_at=self._parse_datetime(match.group("published_at")),
                )
            )
            if len(posts) >= 8:
                break
        return posts

    async def _fetch_html(self, url: str) -> str:
        body, _ = await fetch_bytes(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; EVA Assistant PUBG News)",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout_total=25,
        )
        return body.decode("utf-8", "replace")

    @classmethod
    def _parse_official_post(cls, post_id: str, url: str, html: str) -> PubgNewsPost | None:
        title = cls._meta_content(html, "og:title") or cls._meta_content(html, "twitter:title")
        excerpt = cls._meta_content(html, "og:description") or cls._meta_content(html, "description")
        if not title or not excerpt:
            return None
        title = re.sub(r"\s*-\s*НОВОСТИ\s*[—-]\s*PUBG: BATTLEGROUNDS\s*$", "", title, flags=re.IGNORECASE).strip()
        image_url = cls._meta_content(html, "og:image") or cls._meta_content(html, "twitter:image")
        published_raw = cls._meta_content(html, "article:published_time")
        return PubgNewsPost(
            source="official",
            post_id=post_id,
            title=title,
            excerpt=excerpt,
            url=url,
            image_url=urljoin(url, image_url) if image_url else None,
            published_at=cls._parse_datetime(published_raw) if published_raw else datetime.now(timezone.utc),
        )

    async def translate_to_ukrainian(self, text: str) -> str:
        cleaned = self._shorten(text, self.config.pubg_news.translation_max_characters)
        if not cleaned or self._looks_ukrainian(cleaned):
            return cleaned
        cached = self._translation_cache.get(cleaned)
        if cached is not None:
            return cached
        translated_parts: list[str] = []
        for part in self._translation_parts(cleaned):
            translated = await self._translate_with_google(part)
            if not translated:
                translated = await self._translate_with_mymemory(part)
            translated_parts.append(translated or part)

        translated = self._localize_pubg_terms(" ".join(translated_parts))
        self._translation_cache[cleaned] = translated
        return translated

    async def build_embed(self, post: PubgNewsPost) -> discord.Embed:
        post = await self._expand_official_post(post)
        title = await self.translate_to_ukrainian(post.title)
        excerpt = await self.translate_to_ukrainian(post.excerpt)
        source_label = "Офіційний PUBG" if post.source == "official" else "@iBakhmetNews"
        embed = discord.Embed(
            title=f"🎮 {title or 'Новини PUBG'}",
            description=excerpt or "Є нова публікація, відкрий оригінал для деталей.",
            colour=discord.Colour.orange(),
            url=post.url,
            timestamp=post.published_at,
        )
        embed.add_field(name="Джерело", value=f"[{source_label}]({post.url})", inline=True)
        embed.add_field(name="Повний матеріал", value=f"[Відкрити оригінал]({post.url})", inline=True)
        if post.image_url:
            embed.set_image(url=post.image_url)
        embed.set_footer(text=f"{EMBED_FOOTER} • PUBG news")
        return embed

    async def _expand_official_post(self, post: PubgNewsPost) -> PubgNewsPost:
        if post.source != "official":
            return post
        try:
            html = await self._fetch_html(post.url)
        except (HttpRequestError, OSError, ValueError):
            return post
        body_match = _OFFICIAL_BODY_RE.search(html)
        if body_match is None:
            return post
        body = self._clean_html_text(body_match.group("body"))
        if len(body) <= len(post.excerpt):
            return post
        return PubgNewsPost(
            source=post.source,
            post_id=post.post_id,
            title=post.title,
            excerpt=body,
            url=post.url,
            image_url=post.image_url,
            published_at=post.published_at,
        )

    async def _translate_with_google(self, text: str) -> str | None:
        for attempt in range(2):
            try:
                payload, _ = await fetch_json(
                    "https://translate.googleapis.com/translate_a/single",
                    params={"client": "gtx", "sl": "auto", "tl": "uk", "dt": "t", "q": text},
                    headers={"User-Agent": "EVA Assistant PUBG News"},
                    timeout_total=20,
                )
            except (HttpRequestError, OSError, ValueError):
                if attempt == 0:
                    await asyncio.sleep(1)
                continue
            if isinstance(payload, list) and payload and isinstance(payload[0], list):
                chunks = [str(item[0]) for item in payload[0] if isinstance(item, list) and item and item[0]]
                translated = "".join(chunks).strip()
                if translated and "QUERY LENGTH LIMIT EXCEEDED" not in translated.upper():
                    return translated
        return None

    async def _translate_with_mymemory(self, text: str) -> str | None:
        source_language = "ru" if re.search(r"[А-Яа-яЁё]", text) else "en"
        try:
            payload, _ = await fetch_json(
                "https://api.mymemory.translated.net/get",
                params={"q": text, "langpair": f"{source_language}|uk"},
                headers={"User-Agent": "EVA Assistant PUBG News"},
                timeout_total=20,
            )
        except (HttpRequestError, OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        response = payload.get("responseData")
        if not isinstance(response, dict):
            return None
        translated = str(response.get("translatedText") or "").strip()
        return translated or None

    @staticmethod
    def _meta_content(html: str, wanted_name: str) -> str | None:
        target = wanted_name.casefold()
        for tag in _META_TAG_RE.findall(html):
            attrs = {match.group("name").casefold(): unescape(match.group("value")) for match in _ATTR_RE.finditer(tag)}
            if attrs.get("property", "").casefold() == target or attrs.get("name", "").casefold() == target:
                value = attrs.get("content", "").strip()
                if value:
                    return value
        return None

    @staticmethod
    def _clean_html_text(raw_html: str) -> str:
        text = _BREAK_RE.sub("\n", raw_html)
        text = _BLOCK_END_RE.sub("\n", text)
        text = _TAG_RE.sub("", text)
        return unescape(text).strip()

    @staticmethod
    def _telegram_title_and_excerpt(text: str) -> tuple[str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = lines[0] if lines else "Новини PUBG"
        if len(title) > 110:
            title = title[:109].rstrip() + "…"
        excerpt = " ".join(lines[1:]) or " ".join(lines)
        return title, excerpt

    @staticmethod
    def _shorten(text: str, limit: int) -> str:
        normalized = _SPACE_RE.sub(" ", text).strip()
        if len(normalized) <= limit:
            return normalized
        cut = normalized.rfind(" ", 0, limit - 1)
        minimum_word_cut = max(12, limit // 3)
        return normalized[: cut if cut >= minimum_word_cut else limit - 1].rstrip() + "…"

    @staticmethod
    def _translation_parts(text: str, limit: int = 450) -> list[str]:
        normalized = _SPACE_RE.sub(" ", text).strip()
        if len(normalized) <= limit:
            return [normalized] if normalized else []

        parts: list[str] = []
        remaining = normalized
        while remaining:
            if len(remaining) <= limit:
                parts.append(remaining)
                break
            sentence_cut = max(remaining.rfind(mark, 0, limit) for mark in ".!?;:")
            word_cut = remaining.rfind(" ", 0, limit)
            cut = sentence_cut if sentence_cut >= limit // 2 else word_cut
            if cut < limit // 3:
                cut = limit
            parts.append(remaining[:cut].strip())
            remaining = remaining[cut:].lstrip(" .!?;:")
        return [part for part in parts if part]

    @staticmethod
    def _localize_pubg_terms(text: str) -> str:
        localized = re.sub(
            r"PUBG\s*x\s*(?:Magic Battle|Jujutsu Kaisen|Магическая битва)",
            "PUBG x Магічна битва",
            text,
            flags=re.IGNORECASE,
        )
        return localized

    @staticmethod
    def _looks_ukrainian(text: str) -> bool:
        return any(char in text.casefold() for char in "іїєґ")

    @staticmethod
    def _parse_datetime(raw_value: str) -> datetime:
        cleaned = raw_value.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(cleaned)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)
