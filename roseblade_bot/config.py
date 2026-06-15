"""
EVA Assistant configuration layer.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(slots=True)
class BotConfig:
    token: str
    guild_id: int | None
    audit_category_name: str
    audit_category_id: int | None
    state_file: Path
    enable_members_intent: bool
    enable_message_content_intent: bool


def _parse_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(base_dir: Path | None = None) -> BotConfig:
    root_dir = base_dir or Path.cwd()
    _load_dotenv(root_dir / ".env")

    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")

    guild_id_raw = os.getenv("GUILD_ID", "").strip()
    guild_id = int(guild_id_raw) if guild_id_raw else None
    audit_category_id_raw = os.getenv("AUDIT_CATEGORY_ID", "").strip()
    audit_category_id = int(audit_category_id_raw) if audit_category_id_raw else None

    audit_category_name = os.getenv("AUDIT_CATEGORY_NAME", "Аудит").strip() or "Аудит"
    state_file_raw = os.getenv("STATE_FILE", "data/audit_state.json").strip() or "data/audit_state.json"
    state_file = (root_dir / state_file_raw).resolve()
    enable_members_intent = _parse_bool_env("ENABLE_MEMBERS_INTENT", default=False)
    enable_message_content_intent = _parse_bool_env("ENABLE_MESSAGE_CONTENT_INTENT", default=False)

    return BotConfig(
        token=token,
        guild_id=guild_id,
        audit_category_name=audit_category_name,
        audit_category_id=audit_category_id,
        state_file=state_file,
        enable_members_intent=enable_members_intent,
        enable_message_content_intent=enable_message_content_intent,
    )
