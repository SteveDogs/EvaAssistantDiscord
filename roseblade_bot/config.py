"""
EVA Assistant configuration layer.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any


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
class DiscordIntentsConfig:
    members: bool
    presences: bool
    message_content: bool


@dataclass(slots=True)
class DiscordConfig:
    token: str
    guild_id: int | None
    state_file: Path
    intents: DiscordIntentsConfig


@dataclass(slots=True)
class AuditConfig:
    category_name: str
    category_id: int | None
    ignored_channel_ids: frozenset[int]


@dataclass(slots=True)
class NicknamePrefixConfig:
    rules: dict[int, str]
    legacy_prefixes: frozenset[str]
    excluded_user_ids: frozenset[int]
    resync_minutes: int


@dataclass(slots=True)
class ProtectedBanConfig:
    enabled: bool
    auto_capture: bool
    enforce_minutes: int


@dataclass(slots=True)
class ProtectedVoiceGuardConfig:
    enabled: bool
    user_ids: frozenset[int]


@dataclass(slots=True)
class ProtectionConfig:
    bans: ProtectedBanConfig
    voice_guard: ProtectedVoiceGuardConfig


@dataclass(slots=True)
class ChatBanterConfig:
    enabled: bool
    reply_chance: float
    channel_cooldown_seconds: int
    user_cooldown_seconds: int


@dataclass(slots=True)
class PubgConfig:
    enabled: bool
    channel_ids: frozenset[int]
    allowed_role_ids: frozenset[int]
    api_key: str
    steam_api_key: str
    platform: str
    include_ranked: bool
    include_lifetime_stats: bool
    cache_ttl_seconds: int
    user_cooldown_seconds: int


@dataclass(slots=True)
class SteamDigestConfig:
    enabled: bool
    channel_ids: frozenset[int]
    hour: int
    minute: int
    timezone: str
    top_count: int
    include_support_stats: bool


@dataclass(slots=True)
class ServerBannerConfig:
    enabled: bool
    update_minutes: int
    title: str
    background_url: str
    background_path: Path | None
    font_path: Path | None


_LEGACY_ALIASES = {
    "token": "discord.token",
    "guild_id": "discord.guild_id",
    "state_file": "discord.state_file",
    "enable_members_intent": "discord.intents.members",
    "enable_presences_intent": "discord.intents.presences",
    "enable_message_content_intent": "discord.intents.message_content",
    "audit_category_name": "audit.category_name",
    "audit_category_id": "audit.category_id",
    "ignored_channel_ids": "audit.ignored_channel_ids",
    "nickname_prefix_rules": "nickname_prefix.rules",
    "nickname_prefix_legacy_prefixes": "nickname_prefix.legacy_prefixes",
    "nickname_prefix_excluded_user_ids": "nickname_prefix.excluded_user_ids",
    "nickname_prefix_resync_minutes": "nickname_prefix.resync_minutes",
    "protected_bans_enabled": "protection.bans.enabled",
    "protected_bans_auto_capture": "protection.bans.auto_capture",
    "protected_bans_enforce_minutes": "protection.bans.enforce_minutes",
    "protected_voice_guard_enabled": "protection.voice_guard.enabled",
    "protected_voice_guard_user_ids": "protection.voice_guard.user_ids",
    "chat_banter_enabled": "chat_banter.enabled",
    "chat_banter_reply_chance": "chat_banter.reply_chance",
    "chat_banter_channel_cooldown_seconds": "chat_banter.channel_cooldown_seconds",
    "chat_banter_user_cooldown_seconds": "chat_banter.user_cooldown_seconds",
    "pubg_lookup_enabled": "pubg.enabled",
    "pubg_lookup_channel_ids": "pubg.channel_ids",
    "pubg_lookup_allowed_role_ids": "pubg.allowed_role_ids",
    "pubg_api_key": "pubg.api_key",
    "steam_api_key": "pubg.steam_api_key",
    "pubg_platform": "pubg.platform",
    "pubg_lookup_include_ranked": "pubg.include_ranked",
    "pubg_lookup_include_lifetime_stats": "pubg.include_lifetime_stats",
    "pubg_lookup_cache_ttl_seconds": "pubg.cache_ttl_seconds",
    "pubg_lookup_user_cooldown_seconds": "pubg.user_cooldown_seconds",
    "steam_digest_enabled": "steam.enabled",
    "steam_digest_channel_ids": "steam.channel_ids",
    "steam_digest_hour": "steam.hour",
    "steam_digest_minute": "steam.minute",
    "steam_digest_timezone": "steam.timezone",
    "steam_digest_top_count": "steam.top_count",
    "steam_digest_include_support_stats": "steam.include_support_stats",
    "server_banner_enabled": "banner.enabled",
    "server_banner_update_minutes": "banner.update_minutes",
    "server_banner_title": "banner.title",
    "server_banner_background_url": "banner.background_url",
    "server_banner_background_path": "banner.background_path",
    "server_banner_font_path": "banner.font_path",
}


@dataclass(slots=True)
class BotConfig:
    discord: DiscordConfig
    audit: AuditConfig
    nickname_prefix: NicknamePrefixConfig
    protection: ProtectionConfig
    chat_banter: ChatBanterConfig
    pubg: PubgConfig
    steam: SteamDigestConfig
    banner: ServerBannerConfig

    def __getattr__(self, name: str) -> Any:
        path = _LEGACY_ALIASES.get(name)
        if path is None:
            raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")
        value: Any = self
        for part in path.split("."):
            value = getattr(value, part)
        return value


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


def _parse_optional_path_env(name: str, root_dir: Path) -> Path | None:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return None
    raw_path = Path(raw_value)
    if raw_path.is_absolute():
        return raw_path
    return (root_dir / raw_path).resolve()


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

    discord_config = DiscordConfig(
        token=token,
        guild_id=guild_id,
        state_file=state_file,
        intents=DiscordIntentsConfig(
            members=_parse_bool_env("ENABLE_MEMBERS_INTENT", default=False),
            presences=_parse_bool_env("ENABLE_PRESENCES_INTENT", default=False),
            message_content=_parse_bool_env("ENABLE_MESSAGE_CONTENT_INTENT", default=False),
        ),
    )
    audit_config = AuditConfig(
        category_name=audit_category_name,
        category_id=audit_category_id,
        ignored_channel_ids=_parse_id_set_env("IGNORED_CHANNEL_IDS"),
    )
    nickname_prefix_config = NicknamePrefixConfig(
        rules=_parse_nickname_prefix_rules("NICK_PREFIX_RULES"),
        legacy_prefixes=_parse_string_set_env("NICK_PREFIX_LEGACY_PREFIXES"),
        excluded_user_ids=_parse_id_set_env("NICK_PREFIX_EXCLUDED_USER_IDS"),
        resync_minutes=max(0, _parse_int_env("NICK_PREFIX_RESYNC_MINUTES", default=180)),
    )
    protection_config = ProtectionConfig(
        bans=ProtectedBanConfig(
            enabled=_parse_bool_env("PROTECTED_BANS_ENABLED", default=False),
            auto_capture=_parse_bool_env("PROTECTED_BANS_AUTO_CAPTURE", default=True),
            enforce_minutes=max(0, _parse_int_env("PROTECTED_BANS_ENFORCE_MINUTES", default=5)),
        ),
        voice_guard=ProtectedVoiceGuardConfig(
            enabled=_parse_bool_env("PROTECTED_VOICE_GUARD_ENABLED", default=False),
            user_ids=_parse_id_set_env("PROTECTED_VOICE_GUARD_USER_IDS"),
        ),
    )
    chat_banter_config = ChatBanterConfig(
        enabled=_parse_bool_env("CHAT_BANTER_ENABLED", default=True),
        reply_chance=max(0.0, min(1.0, _parse_float_env("CHAT_BANTER_REPLY_CHANCE", default=0.35))),
        channel_cooldown_seconds=max(0, _parse_int_env("CHAT_BANTER_CHANNEL_COOLDOWN_SECONDS", default=120)),
        user_cooldown_seconds=max(0, _parse_int_env("CHAT_BANTER_USER_COOLDOWN_SECONDS", default=300)),
    )
    pubg_config = PubgConfig(
        enabled=_parse_bool_env("PUBG_LOOKUP_ENABLED", default=False),
        channel_ids=_parse_id_set_env("PUBG_LOOKUP_CHANNEL_IDS"),
        allowed_role_ids=_parse_id_set_env("PUBG_LOOKUP_ALLOWED_ROLE_IDS"),
        api_key=os.getenv("PUBG_API_KEY", "").strip(),
        steam_api_key=os.getenv("STEAM_API_KEY", "").strip(),
        platform=(os.getenv("PUBG_PLATFORM", "steam").strip().lower() or "steam"),
        include_ranked=_parse_bool_env("PUBG_LOOKUP_INCLUDE_RANKED", default=True),
        include_lifetime_stats=_parse_bool_env("PUBG_LOOKUP_INCLUDE_LIFETIME_STATS", default=False),
        cache_ttl_seconds=max(60, _parse_int_env("PUBG_LOOKUP_CACHE_TTL_SECONDS", default=900)),
        user_cooldown_seconds=max(0, _parse_int_env("PUBG_LOOKUP_USER_COOLDOWN_SECONDS", default=20)),
    )
    steam_config = SteamDigestConfig(
        enabled=_parse_bool_env("STEAM_DIGEST_ENABLED", default=False),
        channel_ids=_parse_id_set_env("STEAM_DIGEST_CHANNEL_IDS"),
        hour=min(23, max(0, _parse_int_env("STEAM_DIGEST_HOUR", default=20))),
        minute=min(59, max(0, _parse_int_env("STEAM_DIGEST_MINUTE", default=0))),
        timezone=os.getenv("STEAM_DIGEST_TIMEZONE", "Europe/Simferopol").strip() or "Europe/Simferopol",
        top_count=min(25, max(5, _parse_int_env("STEAM_DIGEST_TOP_COUNT", default=15))),
        include_support_stats=_parse_bool_env("STEAM_DIGEST_INCLUDE_SUPPORT_STATS", default=True),
    )
    banner_config = ServerBannerConfig(
        enabled=_parse_bool_env("SERVER_BANNER_ENABLED", default=False),
        update_minutes=max(1, _parse_int_env("SERVER_BANNER_UPDATE_MINUTES", default=2)),
        title=os.getenv("SERVER_BANNER_TITLE", "").strip(),
        background_url=os.getenv("SERVER_BANNER_BACKGROUND_URL", "").strip(),
        background_path=_parse_optional_path_env("SERVER_BANNER_BACKGROUND_PATH", root_dir),
        font_path=_parse_optional_path_env("SERVER_BANNER_FONT_PATH", root_dir),
    )

    return BotConfig(
        discord=discord_config,
        audit=audit_config,
        nickname_prefix=nickname_prefix_config,
        protection=protection_config,
        chat_banter=chat_banter_config,
        pubg=pubg_config,
        steam=steam_config,
        banner=banner_config,
    )
