"""
EVA Assistant phrasebook loader.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True, slots=True)
class PhraseBook:
    default_eva_lines: tuple[str, ...]
    no_reason_lines: tuple[str, ...]
    flavor_texts: dict[str, tuple[str, ...]]


_FALLBACK_PHRASES = PhraseBook(
    default_eva_lines=(
        "Ева всё записала и пошла дальше держать сервер в тонусе.",
        "Сервер шумит, а Ева спокойно ведёт хронику.",
        "Я всё вижу. Иногда даже слишком многое.",
    ),
    no_reason_lines=(
        "Причину не оставили. Ева осуждающе молчит.",
        "Причина где-то потерялась по дороге. Классика.",
        "Без причины, зато с драмой. Сервер стабилен.",
    ),
    flavor_texts={},
)


def _as_text_tuple(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(value).strip() for value in values if str(value).strip())


def load_phrasebook(locale: str = "ru") -> PhraseBook:
    locale_path = Path(__file__).with_name("locales") / f"{locale}.toml"
    if not locale_path.exists():
        return _FALLBACK_PHRASES

    try:
        payload = tomllib.loads(locale_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return _FALLBACK_PHRASES

    flavor_texts_payload = payload.get("flavor_texts", {})
    flavor_texts: dict[str, tuple[str, ...]] = {}
    if isinstance(flavor_texts_payload, dict):
        for key, values in flavor_texts_payload.items():
            normalized = _as_text_tuple(values)
            if normalized:
                flavor_texts[str(key)] = normalized

    default_eva_lines = _as_text_tuple(payload.get("default_eva_lines"))
    no_reason_lines = _as_text_tuple(payload.get("no_reason_lines"))

    return PhraseBook(
        default_eva_lines=default_eva_lines or _FALLBACK_PHRASES.default_eva_lines,
        no_reason_lines=no_reason_lines or _FALLBACK_PHRASES.no_reason_lines,
        flavor_texts=flavor_texts,
    )


PHRASES = load_phrasebook()
