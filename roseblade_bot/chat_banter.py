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
    openers: tuple[str, ...]
    teases: tuple[str, ...]
    redirects: tuple[str, ...]
    closers: tuple[str, ...]
    patterns: tuple[re.Pattern[str], ...]

    @property
    def reply_variants_count(self) -> int:
        return len(self.openers) * len(self.teases) * len(self.redirects) * len(self.closers)

    def contains_trigger(self, text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        return any(pattern.search(normalized) for pattern in self.patterns)

    def render_reply(self, name: str) -> str:
        parts = (
            random.choice(self.openers).format(name=name),
            random.choice(self.teases).format(name=name),
            random.choice(self.redirects).format(name=name),
            random.choice(self.closers).format(name=name),
        )
        return " ".join(part.strip() for part in parts if part.strip())


_FALLBACK_PACK = ChatBanterPack(
    trigger_roots=("бля", "хуй", "fuck", "shit"),
    openers=(
        "{name}, полегче с фейерверком слов.",
        "{name}, у тебя лексика сегодня с дымком.",
    ),
    teases=(
        "Ева услышала это даже сквозь музыку сервера.",
        "Чат слегка покраснел и сделал вид, что привык.",
    ),
    redirects=(
        "Давай без ковровой бомбардировки словарём мата.",
        "Переходи на нормальный режим речи, ты же умеешь красиво.",
    ),
    closers=(
        "Я не ругаюсь, я просто элегантно напоминаю.",
        "Сделай вдох и выдай следующую реплику уже с шармом.",
    ),
    patterns=_compile_roots(("бля", "хуй", "fuck", "shit")),
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
    openers = _as_text_tuple(payload.get("openers"))
    teases = _as_text_tuple(payload.get("teases"))
    redirects = _as_text_tuple(payload.get("redirects"))
    closers = _as_text_tuple(payload.get("closers"))

    if not (trigger_roots and openers and teases and redirects and closers):
        return _FALLBACK_PACK

    return ChatBanterPack(
        trigger_roots=trigger_roots,
        openers=openers,
        teases=teases,
        redirects=redirects,
        closers=closers,
        patterns=_compile_roots(trigger_roots),
    )


CHAT_BANTER = load_chat_banter()
