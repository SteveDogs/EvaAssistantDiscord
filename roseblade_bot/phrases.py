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
    pubg_titles: dict[str, tuple[str, ...]]
    steam_texts: dict[str, tuple[str, ...]]


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
    pubg_titles={
        "clean": (
            "Чисто. Пока без банной пощёчины.",
            "Живой, дышит, в бан не улетел.",
            "По PUBG вижу: пока всё спокойно.",
        ),
        "permaban": (
            "Пу-пу-пу... аккаунт уже отлетел.",
            "Ой. Тут уже бан-молоточек прилетел.",
            "Да-а-а... этого бойца уже списали с рейса.",
        ),
        "tempban": (
            "Ой-ой, тут временная посадка.",
            "Аккаунт присел остыть. Пока не навсегда.",
            "Тут бан не вечный, но уже неприятный.",
        ),
        "not_found": (
            "Ник не нашла, не ругайся.",
            "Пусто. Либо опечатка, либо не тот shard.",
            "Я покопалась, а ника там не видно.",
        ),
        "rate_limit": (
            "Стоп-стоп, я уткнулась в лимит PUBG API.",
            "Пабг сказал: не так быстро, красавчики.",
            "Сервак PUBG попросил очередь не ломать.",
        ),
        "error": (
            "Я сходила в PUBG, а там дверь заклинило.",
            "Сервер PUBG сегодня с характером.",
            "Постучалась в PUBG, а он сделал вид, что спит.",
        ),
    },
    steam_texts={
        "digest_intros": (
            "Ева на связи. Принесла вечерний Steam-срез, пока у кого-то уже кипит катка.",
            "Вечерний обход Steam готов. Смотрим, кто держит трон, а кто просто шумит красиво.",
            "Я заглянула в Steam и принесла сухую выжимку без лишней воды. Почти без воды.",
        ),
        "digest_titles": (
            "🌙 Вечерний Steam-дайджест",
            "📡 Steam-сводка на вечер",
            "🎮 Что творится в Steam",
        ),
        "pubg_lines": (
            "PUBG всё ещё держится уверенно и не собирается тихо уходить в тень.",
            "PUBG снова в строю и шумит так, будто весь лут уже разобрали без вас.",
            "PUBG в онлайне бодрится. Паника в лобби официально продолжается.",
        ),
        "api_down_lines": (
            "Steam Web API сегодня строит из себя молчуна. Бывает и у титанов плохое настроение.",
            "Steam API сейчас отвечает холодно или вовсе молчит. Не драматизируем, но я записала.",
            "С API у Steam сегодня лёгкая хандра. Остальную сводку всё равно дотащила.",
        ),
        "daily_deal_lines": (
            "На витрине дня у Steam сегодня вот такой соблазн.",
            "Steam сегодня сам подкинул скидку дня, я только красиво донесла.",
            "Если кошелёк рядом, лучше держать его покрепче: скидка дня уже машет рукой.",
        ),
        "weekend_lines": (
            "На выходные Steam тоже не молчит, там уже подкинули пару приманок.",
            "По уикенд-витрине у Steam тоже движ есть, так что вот короткая наводка.",
            "На выходных Steam снова расставил ловушки для вашего баланса. Смотрим.",
        ),
    },
)


def _as_text_tuple(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(value).strip() for value in values if str(value).strip())


def _as_text_map(values: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(values, dict):
        return {}
    mapped: dict[str, tuple[str, ...]] = {}
    for key, raw_values in values.items():
        normalized = _as_text_tuple(raw_values)
        if normalized:
            mapped[str(key)] = normalized
    return mapped


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
    pubg_titles = _as_text_map(payload.get("pubg_titles"))
    steam_texts = _as_text_map(payload.get("steam_texts"))

    return PhraseBook(
        default_eva_lines=default_eva_lines or _FALLBACK_PHRASES.default_eva_lines,
        no_reason_lines=no_reason_lines or _FALLBACK_PHRASES.no_reason_lines,
        flavor_texts=flavor_texts,
        pubg_titles=pubg_titles or _FALLBACK_PHRASES.pubg_titles,
        steam_texts=steam_texts or _FALLBACK_PHRASES.steam_texts,
    )


PHRASES = load_phrasebook()
