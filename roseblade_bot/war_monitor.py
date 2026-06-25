"""
EVA Assistant real-threat monitor service.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import random
import re
from typing import Any

from roseblade_bot import APP_NAME
from roseblade_bot.alert_intel import THREAT_KIND_LABELS, THREAT_KIND_SHORT_LABELS, ThreatIntelHint
from roseblade_bot.config import BotConfig
from roseblade_bot.services.http import http_session


POST_BLOCK_RE = re.compile(
    r'<div class="tgme_widget_message[^"]*"[^>]*data-post="(?P<slug>[^"/]+)/(?P<post_id>\d+)"[\s\S]*?'
    r'<div class="tgme_widget_message_text js-message_text" dir="auto">(?P<text_html>[\s\S]*?)</div>'
    r'[\s\S]*?<time datetime="(?P<published_at>[^"]+)"',
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

EXCLUDE_PATTERNS = (
    "відбій",
    "чисто.",
    "чисто",
    "обстановка станом",
    "#обстановка",
    "наші співчуття",
    "сьогодні,",
    "генштаб",
    "раночку",
    "ймовірність масованої комбінованої атаки на низькому рівні",
)
THREAT_PATTERNS = (
    "загроза баліст",
    "балістика",
    "міг-31к",
    "кинджал",
    "іскандер",
    "бпла",
    "реактив",
    "каб",
    "кар",
    "активність тактичної авіації",
    "зліт",
    "шахед",
)
KIND_PATTERNS = (
    ("ballistic", ("загроза баліст", "балістика", "іскандер", "кинджал")),
    ("mig", ("міг-31к", "зліт міг-31к", "кинж")),
    ("drone", ("бпла", "шахед", "реактив")),
    ("cab", ("каб", "кар")),
    ("aviation", ("активність тактичної авіації",)),
)
REGION_ALIASES = {
    "Автономна Республіка Крим": ("крим",),
    "Волинська область": ("волинськ", "волинь"),
    "Вінницька область": ("вінницьк", "вінниччин"),
    "Дніпропетровська область": ("дніпропетровськ", "дніпропетровщин", "дніпро", "дніпрі"),
    "Донецька область": ("донецьк", "донеччин"),
    "Житомирська область": ("житомирськ", "житомирщин"),
    "Закарпатська область": ("закарпатськ", "закарпатт"),
    "Запорізька область": ("запорізьк", "запоріжж"),
    "Івано-Франківська область": ("івано-франківськ", "івано франківськ", "прикарпатт"),
    "м. Київ": ("київ", "києв"),
    "Київська область": ("київщина", "київськ"),
    "Кіровоградська область": ("кіровоградськ", "кіровоградщин", "кропивницьк"),
    "Луганська область": ("луганськ", "луганщин"),
    "Львівська область": ("львівськ", "львівщин", "львів"),
    "Миколаївська область": ("миколаївськ", "миколаївщин", "миколаїв"),
    "Одеська область": ("одеськ", "одещин", "одеса", "одесу", "одесі"),
    "Полтавська область": ("полтавськ", "полтавщин"),
    "Рівненська область": ("рівненськ", "рівненщин"),
    "м. Севастополь": ("севастопол",),
    "Сумська область": ("сумськ", "сумщин", "суми"),
    "Тернопільська область": ("тернопільськ", "тернопільщин"),
    "Харківська область": ("харківськ", "харківщин", "харків"),
    "Херсонська область": ("херсонськ", "херсонщин", "херсон"),
    "Хмельницька область": ("хмельницьк", "хмельниччин"),
    "Черкаська область": ("черкаськ", "черкащин", "черкаси"),
    "Чернівецька область": ("чернівецьк", "чернівеччин", "чернівці"),
    "Чернігівська область": ("чернігівськ", "чернігівщин", "чернігів"),
}
NATIONAL_PATTERNS = (
    "для всіх регіон",
    "для всієї країни",
    "для всієї україни",
    "по всій країні",
    "по усій країні",
    "всіх областей",
    "всіх регіонів",
    "для усіх областей",
    "для усієї країни",
)
EVA_VOICE_MODEL = """
Ева в war-monitor режиме:
- пишет коротко, живо, без канцелярита и без сухой дикторщины;
- говорит как внимательная, дерзкая, но собранная девушка;
- злится на вражеские атаки, но не скатывается в мусорные оскорбления;
- сначала даёт свой быстрый человеческий комментарий, потом цитирует угрозу;
- после своего комментария оставляет только саму суть угрозы, без лишних подписей и ссылок
""".strip()
THREAT_STYLES = {
    "ballistic": {
        "title": "🟣 Ева | балістика",
        "openers": (
            "Ева: балістика це вже не фон, це команда ховатись.",
            "Ева: ось це вже серйозно, пускова мерзота знову ворушиться.",
            "Ева: дуже поганий рух у небі. Зараз без пафосу, просто в укриття.",
            "Ева: якщо ти це бачиш, значить час не сперечатись, а ховатись.",
        ),
        "closers": (
            "Не стій біля вікон, будь ласка.",
            "Зараз головне швидкість, а не хоробрість.",
            "Бережи себе і не зволікай.",
        ),
    },
    "mig": {
        "title": "🛫 Ева | МіГ-31К",
        "openers": (
            "Ева: носій у повітрі, ці виродки знову тягнуть великий шум.",
            "Ева: МіГ підняли, а значить день знову псує ворожа наволоч.",
            "Ева: ось і почалось, авіаційна гидота знову грає на нервах країни.",
            "Ева: підняли МіГ, отже жарти закінчились дуже швидко.",
        ),
        "closers": (
            "Укриття зараз найрозумніша відповідь.",
            "Не чекай другого запрошення, йди в безпечне місце.",
            "Сховайся і потім вже пиши, що ти окей.",
        ),
    },
    "drone": {
        "title": "⚠️ Ева | БпЛА",
        "openers": (
            "Ева: ворожа бляшанка знову лізе в наше небо.",
            "Ева: дрони від цієї мерзоти самі не зникнуть, будь уважним.",
            "Ева: покидьки знову шлють залізо в наш бік.",
            "Ева: бачу чергову повітряну гидоту, тож краще вже бути в безпечному місці.",
        ),
        "closers": (
            "Якщо ти поруч із напрямком, не тупи біля вікон.",
            "Тримайся ближче до укриття.",
            "Перестрахуватись зараз точно не соромно.",
        ),
    },
    "cab": {
        "title": "💣 Ева | КАБ / КАР",
        "openers": (
            "Ева: авіація противника знову працює брудно і підло.",
            "Ева: КАБи це дуже злий сценарій, без геройства зараз.",
            "Ева: ворожа авіаційна мерзота знову взялась за своє.",
            "Ева: якщо коротко, у небі знову дуже погані наміри.",
        ),
        "closers": (
            "Будь ласка, одразу в укриття.",
            "Зараз головне не ловити момент, а перечекати його безпечно.",
            "Сховайся і тримай зв'язок.",
        ),
    },
    "aviation": {
        "title": "✈️ Ева | авіаційна загроза",
        "openers": (
            "Ева: ворожа авіація знову подає голос, день спокійним не буде.",
            "Ева: у небі недобрі рухи, окупанти знову не можуть жити тихо.",
            "Ева: авіаційна активність від цієї наволочі знову росте.",
            "Ева: бачу дуже неприємний повітряний сюжет, тому будь напоготові.",
        ),
        "closers": (
            "Слідкуй за напрямком загрози і не розслабляйся.",
            "Якщо ти в зоні ризику, краще одразу змістись у безпечне місце.",
            "Зараз обережність виграє у будь-якої сміливості.",
        ),
    },
    "generic": {
        "title": "🚨 Ева | загроза",
        "openers": (
            "Ева: схоже, ворожа гидота знову щось затіяла.",
            "Ева: знову поганий рух з того боку, тож будь уважним.",
            "Ева: окупанти знову лізуть у наш простір зі своїм безумством.",
            "Ева: картина тривожна, тож зараз краще без зайвого ризику.",
        ),
        "closers": (
            "Не ігноруй це повідомлення.",
            "Бережи себе і не затягуй з рішенням.",
            "Краще зайвий раз сховатись, ніж потім шкодувати.",
        ),
    },
}


@dataclass(frozen=True, slots=True)
class WarMonitorPost:
    post_id: int
    published_at: datetime
    text: str
    url: str


class WarMonitorService:
    def __init__(self, config: BotConfig) -> None:
        self.config = config

    @property
    def is_enabled(self) -> bool:
        return self.config.war_monitor.enabled

    @property
    def is_configured(self) -> bool:
        return self.is_enabled and bool(self.config.war_monitor.channel_ids) and bool(self.config.war_monitor.channel_username)

    def channel_count(self) -> int:
        return len(self.config.war_monitor.channel_ids)

    def schedule_label(self) -> str:
        return f"every {self.config.war_monitor.poll_seconds}s from @{self.config.war_monitor.channel_username}"

    def threat_kind(self, text: str) -> str:
        normalized = self._normalize(text)
        for kind, patterns in KIND_PATTERNS:
            if any(pattern in normalized for pattern in patterns):
                return kind
        return "generic"

    def is_relevant_threat(self, text: str) -> bool:
        normalized = self._normalize(text)
        if not normalized:
            return False
        if any(pattern in normalized for pattern in EXCLUDE_PATTERNS):
            return False
        return any(pattern in normalized for pattern in THREAT_PATTERNS)

    def extract_intel(self, post: WarMonitorPost) -> ThreatIntelHint | None:
        if not self.is_relevant_threat(post.text):
            return None

        normalized = self._normalize(post.text)
        kind = self.threat_kind(post.text)
        regions = self._extract_regions(normalized)
        is_national = any(pattern in normalized for pattern in NATIONAL_PATTERNS)
        if kind in {"ballistic", "mig"} and (
            not regions or regions == ("Автономна Республіка Крим",)
        ):
            is_national = True

        excerpt = self._excerpt(post.text, limit=220)
        return ThreatIntelHint(
            post_id=post.post_id,
            published_at=post.published_at,
            kind=kind,
            label=THREAT_KIND_LABELS.get(kind, THREAT_KIND_LABELS["generic"]),
            short_label=THREAT_KIND_SHORT_LABELS.get(kind, THREAT_KIND_SHORT_LABELS["generic"]),
            excerpt=excerpt,
            raw_text=post.text,
            regions=regions,
            is_national=is_national,
            url=post.url,
        )

    async def fetch_recent_posts(self, *, limit: int = 12) -> list[WarMonitorPost]:
        username = self.config.war_monitor.channel_username.strip().lstrip("@")
        url = f"https://t.me/s/{username}"
        headers = {
            "User-Agent": f"{APP_NAME} / war monitor",
            "Accept": "text/html,application/xhtml+xml",
        }
        async with http_session(timeout_total=20, headers=headers) as session:
            async with session.get(url) as response:
                body = await response.read()
                if response.status >= 400:
                    raise RuntimeError(f"war_monitor page returned {response.status}")
        html = body.decode("utf-8", "replace")

        posts: list[WarMonitorPost] = []
        for match in POST_BLOCK_RE.finditer(html):
            slug = str(match.group("slug") or "").strip()
            if slug.lower() != username.lower():
                continue
            text = self._clean_html_text(match.group("text_html"))
            if not text:
                continue
            posts.append(
                WarMonitorPost(
                    post_id=int(match.group("post_id")),
                    published_at=self._parse_datetime(match.group("published_at")),
                    text=text,
                    url=f"https://t.me/{username}/{int(match.group('post_id'))}",
                )
            )
            if len(posts) >= limit:
                break
        return posts

    def build_alert_message(self, post: WarMonitorPost) -> str:
        kind = self.threat_kind(post.text)
        style = THREAT_STYLES.get(kind, THREAT_STYLES["generic"])
        opener = random.choice(style["openers"])
        closer = random.choice(style["closers"])
        quoted = "\n".join(f"> {line}" for line in post.text.splitlines() if line.strip())
        return (
            f"{style['title']}\n"
            f"{opener} {closer}\n\n"
            f"{quoted}"
        )[:1950]

    def build_hint_message(
        self,
        hint: ThreatIntelHint,
        *,
        official_context: str | None = None,
    ) -> str:
        style = THREAT_STYLES.get(hint.kind, THREAT_STYLES["generic"])
        opener = random.choice(style["openers"])
        closer = random.choice(style["closers"])
        quoted = "\n".join(f"> {line}" for line in hint.raw_text.splitlines() if line.strip())
        parts = [
            style["title"],
            f"{opener} {closer}",
        ]
        if official_context:
            parts.append(official_context)
        parts.append(quoted)
        return "\n\n".join(parts)[:1950]

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().replace("ё", "е").split())

    @classmethod
    def _extract_regions(cls, normalized_text: str) -> tuple[str, ...]:
        matched: list[str] = []
        for region_title, aliases in REGION_ALIASES.items():
            if any(alias in normalized_text for alias in aliases):
                matched.append(region_title)
        return tuple(matched)

    @staticmethod
    def _excerpt(text: str, *, limit: int) -> str:
        joined = " ".join(line.strip() for line in text.splitlines() if line.strip())
        if len(joined) <= limit:
            return joined
        return joined[: limit - 1].rstrip() + "…"

    @staticmethod
    def _clean_html_text(raw_html: str) -> str:
        cleaned = BREAK_RE.sub("\n", raw_html)
        cleaned = TAG_RE.sub("", cleaned)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _parse_datetime(raw_value: str) -> datetime:
        cleaned = raw_value.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError:
            return datetime.now(timezone.utc)
