"""
EVA Assistant threat-intel helpers.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


THREAT_KIND_LABELS = {
    "ballistic": "Балістика / ракети",
    "mig": "МіГ-31К / можливі Кинджали",
    "drone": "БпЛА / шахеди",
    "cab": "КАБ / КАР",
    "aviation": "Тактична авіація",
    "generic": "Повітряна загроза",
}

THREAT_KIND_SHORT_LABELS = {
    "ballistic": "Балістика",
    "mig": "МіГ-31К",
    "drone": "БпЛА",
    "cab": "КАБ",
    "aviation": "Авіація",
    "generic": "Загроза",
}

THREAT_KIND_PRIORITIES = {
    "ballistic": 100,
    "mig": 90,
    "cab": 80,
    "drone": 70,
    "aviation": 60,
    "generic": 40,
}


@dataclass(frozen=True, slots=True)
class ThreatIntelHint:
    post_id: int
    published_at: datetime
    kind: str
    label: str
    short_label: str
    excerpt: str
    raw_text: str
    regions: tuple[str, ...]
    is_national: bool
    url: str


def threat_priority(kind: str) -> int:
    return THREAT_KIND_PRIORITIES.get(kind, 0)
