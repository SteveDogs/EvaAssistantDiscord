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


def _normalize_markers(values: object) -> tuple[str, ...]:
    return tuple(
        normalized
        for normalized in (normalize_text(str(value)) for value in values if str(value).strip())
        if normalized
    )


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


def _compile_exact_terms(terms: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    patterns = []
    for term in terms:
        normalized_term = normalize_text(term)
        if not normalized_term:
            continue
        patterns.append(re.compile(rf"(?iu)\b{re.escape(normalized_term)}\b"))
    return tuple(patterns)


@dataclass(frozen=True, slots=True)
class ChatBanterPack:
    trigger_roots: tuple[str, ...]
    direct_replies: tuple[str, ...]
    openers: tuple[str, ...]
    redirects: tuple[str, ...]
    afterthoughts: tuple[str, ...]
    patterns: tuple[re.Pattern[str], ...]
    strict_trigger_roots: tuple[str, ...]
    strict_direct_replies: tuple[str, ...]
    strict_openers: tuple[str, ...]
    strict_redirects: tuple[str, ...]
    strict_afterthoughts: tuple[str, ...]
    strict_exact_terms: tuple[str, ...]
    strict_phrase_markers: tuple[str, ...]
    strict_patterns: tuple[re.Pattern[str], ...]
    strict_exact_patterns: tuple[re.Pattern[str], ...]

    @property
    def reply_variants_count(self) -> int:
        combo_count = len(self.openers) * len(self.redirects) * (len(self.afterthoughts) + 1)
        strict_combo_count = len(self.strict_openers) * len(self.strict_redirects) * (len(self.strict_afterthoughts) + 1)
        return len(self.direct_replies) + combo_count + len(self.strict_direct_replies) + strict_combo_count

    def _match_profile(self, text: str) -> str | None:
        normalized = normalize_text(text)
        if not normalized:
            return None
        if any(pattern.search(normalized) for pattern in self.strict_exact_patterns):
            return "strict"
        if any(marker in normalized for marker in self.strict_phrase_markers):
            return "strict"
        if any(pattern.search(normalized) for pattern in self.strict_patterns):
            return "strict"
        if any(pattern.search(normalized) for pattern in self.patterns):
            return "default"
        return None

    def contains_trigger(self, text: str) -> bool:
        return self._match_profile(text) is not None

    def _render_direct_reply(self, name: str, *, strict: bool) -> str:
        direct_replies = self.strict_direct_replies if strict else self.direct_replies
        if not direct_replies:
            return ""
        return random.choice(direct_replies).format(name=name).strip()

    def _render_combo_reply(self, name: str, *, strict: bool) -> str:
        openers = self.strict_openers if strict else self.openers
        redirects = self.strict_redirects if strict else self.redirects
        afterthoughts = self.strict_afterthoughts if strict else self.afterthoughts
        if not openers or not redirects:
            return ""
        parts = (
            random.choice(openers).format(name=name),
            random.choice(redirects).format(name=name),
        )
        rendered = [part.strip() for part in parts if part.strip()]
        if afterthoughts and random.random() < 0.35:
            rendered.append(random.choice(afterthoughts).format(name=name).strip())
        return " ".join(part for part in rendered if part)

    def render_reply(self, name: str, text: str, previous_reply: str | None = None) -> str:
        profile = self._match_profile(text)
        strict = profile == "strict"
        for _ in range(8):
            direct_replies = self.strict_direct_replies if strict else self.direct_replies
            openers = self.strict_openers if strict else self.openers
            redirects = self.strict_redirects if strict else self.redirects
            use_direct_reply = bool(direct_replies) and (
                not openers or not redirects or random.random() < 0.72
            )
            reply = (
                self._render_direct_reply(name, strict=strict)
                if use_direct_reply
                else self._render_combo_reply(name, strict=strict)
            )
            if reply and reply != previous_reply:
                return reply

        fallback = self._render_direct_reply(name, strict=strict) or self._render_combo_reply(name, strict=strict)
        if fallback and fallback != previous_reply:
            return fallback

        direct_replies = self.strict_direct_replies if strict else self.direct_replies
        if direct_replies:
            for template in direct_replies:
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
    strict_trigger_roots=("гитлер", "нацист", "nazi", "hitler", "nigger"),
    strict_direct_replies=(
        "{name}, расистский и нацистский мусор здесь не приживётся.",
        "{name}, нет. вот это уже не edgy, а просто дно.",
        "{name}, такие заходы не делают тебя страшным. только жалким.",
    ),
    strict_openers=(
        "{name}, стоп.",
        "{name}, даже не начинай.",
    ),
    strict_redirects=(
        "Нацистские и расистские вбросы оставь за дверью.",
        "Смени тему, пока чат окончательно не испачкал.",
    ),
    strict_afterthoughts=(
        "С этим у меня разговор короткий.",
        "И да, это не шутка.",
    ),
    strict_exact_terms=("жид", "жиды", "жидом", "жиды", "жыд", "жыды", "kike", "heeb"),
    strict_phrase_markers=("dirty jew", "kill jew", "gas the jew", "hate jew", "бей евр", "бей жид"),
    strict_patterns=_compile_roots(("гитлер", "нацист", "nazi", "hitler", "nigger")),
    strict_exact_patterns=_compile_exact_terms(("жид", "жиды", "жидом", "жиды", "жыд", "жыды", "kike", "heeb")),
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
    strict_trigger_roots = _as_text_tuple(payload.get("strict_trigger_roots"))
    strict_direct_replies = _as_text_tuple(payload.get("strict_direct_replies"))
    strict_openers = _as_text_tuple(payload.get("strict_openers"))
    strict_redirects = _as_text_tuple(payload.get("strict_redirects"))
    strict_afterthoughts = _as_text_tuple(payload.get("strict_afterthoughts"))
    strict_exact_terms = _as_text_tuple(payload.get("strict_exact_terms"))
    strict_phrase_markers = _normalize_markers(payload.get("strict_phrase_markers"))

    if not trigger_roots:
        return _FALLBACK_PACK
    if not direct_replies and not (openers and redirects):
        return _FALLBACK_PACK
    strict_is_configured = bool(strict_trigger_roots or strict_exact_terms or strict_phrase_markers)
    if strict_is_configured and not strict_direct_replies and not (strict_openers and strict_redirects):
        return _FALLBACK_PACK

    return ChatBanterPack(
        trigger_roots=trigger_roots,
        direct_replies=direct_replies,
        openers=openers,
        redirects=redirects,
        afterthoughts=afterthoughts,
        patterns=_compile_roots(trigger_roots),
        strict_trigger_roots=strict_trigger_roots,
        strict_direct_replies=strict_direct_replies,
        strict_openers=strict_openers,
        strict_redirects=strict_redirects,
        strict_afterthoughts=strict_afterthoughts,
        strict_exact_terms=strict_exact_terms,
        strict_phrase_markers=strict_phrase_markers,
        strict_patterns=_compile_roots(strict_trigger_roots),
        strict_exact_patterns=_compile_exact_terms(strict_exact_terms),
    )


CHAT_BANTER = load_chat_banter()
