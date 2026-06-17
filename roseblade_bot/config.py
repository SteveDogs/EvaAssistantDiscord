"""
EVA Assistant configuration layer.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re


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
    nickname_prefix_rules: dict[int, str]
    nickname_prefix_legacy_prefixes: frozenset[str]
    nickname_prefix_excluded_user_ids: frozenset[int]
    nickname_prefix_resync_minutes: int
    ignored_channel_ids: frozenset[int]
    protected_bans_enabled: bool
    protected_bans_auto_capture: bool
    protected_bans_enforce_minutes: int
    protected_voice_guard_enabled: bool
    protected_voice_guard_user_ids: frozenset[int]
    chat_banter_enabled: bool
    chat_banter_reply_chance: float
    chat_banter_channel_cooldown_seconds: int
    chat_banter_user_cooldown_seconds: int
    pubg_lookup_enabled: bool
    pubg_lookup_channel_ids: frozenset[int]
    pubg_lookup_allowed_role_ids: frozenset[int]
    pubg_api_key: str
    steam_api_key: str
    pubg_platform: str
    pubg_lookup_include_ranked: bool
    pubg_lookup_include_lifetime_stats: bool
    pubg_lookup_cache_ttl_seconds: int
    pubg_lookup_user_cooldown_seconds: int
    steam_digest_enabled: bool
    steam_digest_channel_ids: frozenset[int]
    steam_digest_hour: int
    steam_digest_minute: int
    steam_digest_timezone: str
    steam_digest_top_count: int
    steam_digest_include_support_stats: bool


def _parse_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return float(raw_value.strip().replace(",", "."))


def _parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return int(raw_value.strip())


def _parse_id_set_env(name: str) -> frozenset[int]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return frozenset()

    values: set[int] = set()
    for chunk in re.split(r"[;,\s]+", raw_value):
        entry = chunk.strip()
        if not entry:
            continue
        values.add(int(entry))
    return frozenset(values)


def _parse_nickname_prefix_rules(name: str) -> dict[int, str]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return {}

    rules: dict[int, str] = {}
    for chunk in re.split(r"[;,]", raw_value):
        entry = chunk.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise RuntimeError(
                f"{name} has invalid entry '{entry}'. Use format ROLE_ID=PREFIX;ROLE_ID=PREFIX or ROLE_ID=PREFIX,ROLE_ID=PREFIX."
            )
        role_id_raw, prefix_raw = entry.split("=", 1)
        role_id = int(role_id_raw.strip())
        prefix = prefix_raw.strip()
        if not prefix:
            continue
        rules[role_id] = prefix
    return rules


def _parse_string_set_env(name: str) -> frozenset[str]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return frozenset()

    values: set[str] = set()
    for chunk in re.split(r"[;,]", raw_value):
        entry = chunk.strip()
        if entry:
            values.add(entry)
    return frozenset(values)


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
    nickname_prefix_rules = _parse_nickname_prefix_rules("NICK_PREFIX_RULES")
    nickname_prefix_legacy_prefixes = _parse_string_set_env("NICK_PREFIX_LEGACY_PREFIXES")
    nickname_prefix_excluded_user_ids = _parse_id_set_env("NICK_PREFIX_EXCLUDED_USER_IDS")
    nickname_prefix_resync_minutes = max(0, _parse_int_env("NICK_PREFIX_RESYNC_MINUTES", default=180))
    ignored_channel_ids = _parse_id_set_env("IGNORED_CHANNEL_IDS")
    protected_bans_enabled = _parse_bool_env("PROTECTED_BANS_ENABLED", default=False)
    protected_bans_auto_capture = _parse_bool_env("PROTECTED_BANS_AUTO_CAPTURE", default=True)
    protected_bans_enforce_minutes = max(0, _parse_int_env("PROTECTED_BANS_ENFORCE_MINUTES", default=5))
    protected_voice_guard_enabled = _parse_bool_env("PROTECTED_VOICE_GUARD_ENABLED", default=False)
    protected_voice_guard_user_ids = _parse_id_set_env("PROTECTED_VOICE_GUARD_USER_IDS")
    chat_banter_enabled = _parse_bool_env("CHAT_BANTER_ENABLED", default=True)
    chat_banter_reply_chance = max(0.0, min(1.0, _parse_float_env("CHAT_BANTER_REPLY_CHANCE", default=0.35)))
    chat_banter_channel_cooldown_seconds = max(0, _parse_int_env("CHAT_BANTER_CHANNEL_COOLDOWN_SECONDS", default=120))
    chat_banter_user_cooldown_seconds = max(0, _parse_int_env("CHAT_BANTER_USER_COOLDOWN_SECONDS", default=300))
    pubg_lookup_enabled = _parse_bool_env("PUBG_LOOKUP_ENABLED", default=False)
    pubg_lookup_channel_ids = _parse_id_set_env("PUBG_LOOKUP_CHANNEL_IDS")
    pubg_lookup_allowed_role_ids = _parse_id_set_env("PUBG_LOOKUP_ALLOWED_ROLE_IDS")
    pubg_api_key = os.getenv("PUBG_API_KEY", "").strip()
    steam_api_key = os.getenv("STEAM_API_KEY", "").strip()
    pubg_platform = (os.getenv("PUBG_PLATFORM", "steam").strip().lower() or "steam")
    pubg_lookup_include_ranked = _parse_bool_env("PUBG_LOOKUP_INCLUDE_RANKED", default=True)
    pubg_lookup_include_lifetime_stats = _parse_bool_env("PUBG_LOOKUP_INCLUDE_LIFETIME_STATS", default=False)
    pubg_lookup_cache_ttl_seconds = max(60, _parse_int_env("PUBG_LOOKUP_CACHE_TTL_SECONDS", default=900))
    pubg_lookup_user_cooldown_seconds = max(0, _parse_int_env("PUBG_LOOKUP_USER_COOLDOWN_SECONDS", default=20))
    steam_digest_enabled = _parse_bool_env("STEAM_DIGEST_ENABLED", default=False)
    steam_digest_channel_ids = _parse_id_set_env("STEAM_DIGEST_CHANNEL_IDS")
    steam_digest_hour = min(23, max(0, _parse_int_env("STEAM_DIGEST_HOUR", default=20)))
    steam_digest_minute = min(59, max(0, _parse_int_env("STEAM_DIGEST_MINUTE", default=0)))
    steam_digest_timezone = os.getenv("STEAM_DIGEST_TIMEZONE", "Europe/Simferopol").strip() or "Europe/Simferopol"
    steam_digest_top_count = min(25, max(5, _parse_int_env("STEAM_DIGEST_TOP_COUNT", default=15)))
    steam_digest_include_support_stats = _parse_bool_env("STEAM_DIGEST_INCLUDE_SUPPORT_STATS", default=True)

    return BotConfig(
        token=token,
        guild_id=guild_id,
        audit_category_name=audit_category_name,
        audit_category_id=audit_category_id,
        state_file=state_file,
        enable_members_intent=enable_members_intent,
        enable_message_content_intent=enable_message_content_intent,
        nickname_prefix_rules=nickname_prefix_rules,
        nickname_prefix_legacy_prefixes=nickname_prefix_legacy_prefixes,
        nickname_prefix_excluded_user_ids=nickname_prefix_excluded_user_ids,
        nickname_prefix_resync_minutes=nickname_prefix_resync_minutes,
        ignored_channel_ids=ignored_channel_ids,
        protected_bans_enabled=protected_bans_enabled,
        protected_bans_auto_capture=protected_bans_auto_capture,
        protected_bans_enforce_minutes=protected_bans_enforce_minutes,
        protected_voice_guard_enabled=protected_voice_guard_enabled,
        protected_voice_guard_user_ids=protected_voice_guard_user_ids,
        chat_banter_enabled=chat_banter_enabled,
        chat_banter_reply_chance=chat_banter_reply_chance,
        chat_banter_channel_cooldown_seconds=chat_banter_channel_cooldown_seconds,
        chat_banter_user_cooldown_seconds=chat_banter_user_cooldown_seconds,
        pubg_lookup_enabled=pubg_lookup_enabled,
        pubg_lookup_channel_ids=pubg_lookup_channel_ids,
        pubg_lookup_allowed_role_ids=pubg_lookup_allowed_role_ids,
        pubg_api_key=pubg_api_key,
        steam_api_key=steam_api_key,
        pubg_platform=pubg_platform,
        pubg_lookup_include_ranked=pubg_lookup_include_ranked,
        pubg_lookup_include_lifetime_stats=pubg_lookup_include_lifetime_stats,
        pubg_lookup_cache_ttl_seconds=pubg_lookup_cache_ttl_seconds,
        pubg_lookup_user_cooldown_seconds=pubg_lookup_user_cooldown_seconds,
        steam_digest_enabled=steam_digest_enabled,
        steam_digest_channel_ids=steam_digest_channel_ids,
        steam_digest_hour=steam_digest_hour,
        steam_digest_minute=steam_digest_minute,
        steam_digest_timezone=steam_digest_timezone,
        steam_digest_top_count=steam_digest_top_count,
        steam_digest_include_support_stats=steam_digest_include_support_stats,
    )
