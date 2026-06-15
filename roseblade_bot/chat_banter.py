"""
EVA Assistant playful chat banter detector and reply generator.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
import re
import tomllib


def _as_text_tuple(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(value).strip() for value in values if str(value).strip())


def normalize_text(value: str) -> str:
    lowered = value.casefold()
    translation = str.maketrans(
        {
            "ё": "е",
            "є": "е",
            "ї": "і",
            "’": "'",
            "`": "'",
        }
    )
    lowered = lowered.translate(translation)
    lowered = re.sub(r"[^\w\s']", " ", lowered, flags=re.UNICODE)
    lowered = re.sub(r"\s+", " ", lowered, flags=re.UNICODE).strip()
    return lowered


def _compile_roots(roots: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    patterns = []
    for root in roots:
        normalized_root = normalize_text(root)
        if not normalized_root:
            continue
        patterns.append(re.compile(rf"(?iu)\b{re.escape(normalized_root)}\w*\b"))
    return tuple(patterns)


@dataclass(frozen=True, slots=True)
class ChatBanterPack:
    trigger_roots: tuple[str, ...]
    direct_replies: tuple[str, ...]
    openers: tuple[str, ...]
    redirects: tuple[str, ...]
    afterthoughts: tuple[str, ...]
    patterns: tuple[re.Pattern[str], ...]

    @property
    def reply_variants_count(self) -> int:
        combo_count = len(self.openers) * len(self.redirects) * (len(self.afterthoughts) + 1)
        return len(self.direct_replies) + combo_count

    def contains_trigger(self, text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        return any(pattern.search(normalized) for pattern in self.patterns)

    def _render_direct_reply(self, name: str) -> str:
        if not self.direct_replies:
            return ""
        return random.choice(self.direct_replies).format(name=name).strip()

    def _render_combo_reply(self, name: str) -> str:
        if not self.openers or not self.redirects:
            return ""
        parts = (
            random.choice(self.openers).format(name=name),
            random.choice(self.redirects).format(name=name),
        )
        rendered = [part.strip() for part in parts if part.strip()]
        if self.afterthoughts and random.random() < 0.35:
            rendered.append(random.choice(self.afterthoughts).format(name=name).strip())
        return " ".join(part for part in rendered if part)

    def render_reply(self, name: str, previous_reply: str | None = None) -> str:
        for _ in range(8):
            use_direct_reply = bool(self.direct_replies) and (
                not self.openers or not self.redirects or random.random() < 0.72
            )
            reply = self._render_direct_reply(name) if use_direct_reply else self._render_combo_reply(name)
            if reply and reply != previous_reply:
                return reply

        fallback = self._render_direct_reply(name) or self._render_combo_reply(name)
        if fallback and fallback != previous_reply:
            return fallback

        if self.direct_replies:
            for template in self.direct_replies:
                candidate = template.format(name=name).strip()
                if candidate and candidate != previous_reply:
                    return candidate

        return fallback


_FALLBACK_PACK = ChatBanterPack(
    trigger_roots=("бля", "хуй", "fuck", "shit", "пизд"),
    direct_replies=(
        "{name}, ну без этого. скажи нормально.",
        "{name}, дядя, полегче. мысль есть, мат убери.",
        "{name}, алло, эмоция долетела. теперь без словесного пожара.",
        "{name}, сильный заход, но давай по-человечески.",
    ),
    openers=(
        "{name}, ну ты чего.",
        "{name}, спокойно.",
        "{name}, алло.",
    ),
    redirects=(
        "Скажи то же самое, только без мата.",
        "Перефразируй красиво, я в тебя верю.",
    ),
    afterthoughts=(
        "Я же тут за красивый вайб.",
        "Чат тебе спасибо скажет.",
    ),
    patterns=_compile_roots(("бля", "хуй", "fuck", "shit", "пизд")),
)


def load_chat_banter(locale: str = "chat_banter") -> ChatBanterPack:
    locale_path = Path(__file__).with_name("locales") / f"{locale}.toml"
    if not locale_path.exists():
        return _FALLBACK_PACK

    try:
        payload = tomllib.loads(locale_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return _FALLBACK_PACK

    trigger_roots = _as_text_tuple(payload.get("trigger_roots"))
    direct_replies = _as_text_tuple(payload.get("direct_replies"))
    openers = _as_text_tuple(payload.get("openers"))
    redirects = _as_text_tuple(payload.get("redirects"))
    afterthoughts = _as_text_tuple(payload.get("afterthoughts"))

    if not trigger_roots:
        return _FALLBACK_PACK
    if not direct_replies and not (openers and redirects):
        return _FALLBACK_PACK

    return ChatBanterPack(
        trigger_roots=trigger_roots,
        direct_replies=direct_replies,
        openers=openers,
        redirects=redirects,
        afterthoughts=afterthoughts,
        patterns=_compile_roots(trigger_roots),
    )


CHAT_BANTER = load_chat_banter()
