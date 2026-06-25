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
    user_rules: dict[int, str]
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
class SpecialDmConfig:
    enabled: bool
    user_ids: frozenset[int]
    events: frozenset[str]
    voice_join_cooldown_seconds: int
    avatar_change_cooldown_seconds: int


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
    excluded_channel_ids: frozenset[int]


@dataclass(slots=True)
class AirAlertConfig:
    enabled: bool
    channel_ids: frozenset[int]
    provider: str
    api_token: str
    ubilling_source: str
    poll_seconds: int
    title: str
    use_war_monitor_intel: bool
    intel_max_age_seconds: int
    bulletin_cooldown_seconds: int
    hot_regions_limit: int


@dataclass(slots=True)
class WarMonitorConfig:
    enabled: bool
    channel_ids: frozenset[int]
    channel_username: str
    poll_seconds: int
    announce_on_startup: bool


@dataclass(slots=True)
class MusicConfig:
    enabled: bool
    lavalink_uri: str
    lavalink_password: str
    node_identifier: str
    default_volume: int
    inactive_timeout_seconds: int
    default_search_source: str
    fallback_search_source: str
    allowed_role_ids: frozenset[int]
    spotify_client_id: str
    spotify_client_secret: str
    spotify_country_code: str


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
    "nickname_prefix_user_rules": "nickname_prefix.user_rules",
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
    "special_dm_enabled": "special_dm.enabled",
    "special_dm_user_ids": "special_dm.user_ids",
    "special_dm_events": "special_dm.events",
    "special_dm_voice_join_cooldown_seconds": "special_dm.voice_join_cooldown_seconds",
    "special_dm_avatar_change_cooldown_seconds": "special_dm.avatar_change_cooldown_seconds",
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
    "server_banner_excluded_channel_ids": "banner.excluded_channel_ids",
    "air_alert_enabled": "air_alert.enabled",
    "air_alert_channel_ids": "air_alert.channel_ids",
    "air_alert_provider": "air_alert.provider",
    "air_alert_api_token": "air_alert.api_token",
    "air_alert_ubilling_source": "air_alert.ubilling_source",
    "air_alert_poll_seconds": "air_alert.poll_seconds",
    "air_alert_title": "air_alert.title",
    "air_alert_use_war_monitor_intel": "air_alert.use_war_monitor_intel",
    "air_alert_intel_max_age_seconds": "air_alert.intel_max_age_seconds",
    "air_alert_bulletin_cooldown_seconds": "air_alert.bulletin_cooldown_seconds",
    "air_alert_hot_regions_limit": "air_alert.hot_regions_limit",
    "war_monitor_enabled": "war_monitor.enabled",
    "war_monitor_channel_ids": "war_monitor.channel_ids",
    "war_monitor_channel_username": "war_monitor.channel_username",
    "war_monitor_poll_seconds": "war_monitor.poll_seconds",
    "war_monitor_announce_on_startup": "war_monitor.announce_on_startup",
    "music_enabled": "music.enabled",
    "music_lavalink_uri": "music.lavalink_uri",
    "music_lavalink_password": "music.lavalink_password",
    "music_node_identifier": "music.node_identifier",
    "music_default_volume": "music.default_volume",
    "music_inactive_timeout_seconds": "music.inactive_timeout_seconds",
    "music_search_source": "music.default_search_source",
    "music_fallback_search_source": "music.fallback_search_source",
    "music_allowed_role_ids": "music.allowed_role_ids",
    "music_spotify_client_id": "music.spotify_client_id",
    "music_spotify_client_secret": "music.spotify_client_secret",
    "music_spotify_country_code": "music.spotify_country_code",
}


@dataclass(slots=True)
class BotConfig:
    discord: DiscordConfig
    audit: AuditConfig
    nickname_prefix: NicknamePrefixConfig
    protection: ProtectionConfig
    chat_banter: ChatBanterConfig
    special_dm: SpecialDmConfig
    pubg: PubgConfig
    steam: SteamDigestConfig
    banner: ServerBannerConfig
    air_alert: AirAlertConfig
    war_monitor: WarMonitorConfig
    music: MusicConfig

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


def _parse_event_names_env(name: str, *, default: tuple[str, ...]) -> frozenset[str]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return frozenset(default)

    values: set[str] = set()
    for chunk in re.split(r"[;,\s]+", raw_value):
        entry = chunk.strip().lower()
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
        user_rules=_parse_nickname_prefix_rules("NICK_PREFIX_USER_RULES"),
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
    special_dm_config = SpecialDmConfig(
        enabled=_parse_bool_env("SPECIAL_DM_ENABLED", default=False),
        user_ids=_parse_id_set_env("SPECIAL_DM_USER_IDS"),
        events=_parse_event_names_env(
            "SPECIAL_DM_EVENTS",
            default=("voice_joined", "avatar_changed"),
        ),
        voice_join_cooldown_seconds=max(0, _parse_int_env("SPECIAL_DM_VOICE_JOIN_COOLDOWN_SECONDS", default=600)),
        avatar_change_cooldown_seconds=max(0, _parse_int_env("SPECIAL_DM_AVATAR_CHANGE_COOLDOWN_SECONDS", default=300)),
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
        excluded_channel_ids=_parse_id_set_env("SERVER_BANNER_EXCLUDED_CHANNEL_IDS"),
    )
    air_alert_config = AirAlertConfig(
        enabled=_parse_bool_env("AIR_ALERT_ENABLED", default=False),
        channel_ids=_parse_id_set_env("AIR_ALERT_CHANNEL_IDS"),
        provider=(os.getenv("AIR_ALERT_PROVIDER", "auto").strip().lower() or "auto"),
        api_token=os.getenv("AIR_ALERT_API_TOKEN", "").strip(),
        ubilling_source=(os.getenv("AIR_ALERT_UBILLING_SOURCE", "default").strip().lower() or "default"),
        poll_seconds=max(30, _parse_int_env("AIR_ALERT_POLL_SECONDS", default=60)),
        title=os.getenv("AIR_ALERT_TITLE", "Карта повітряних тривог України").strip()
        or "Карта повітряних тривог України",
        use_war_monitor_intel=_parse_bool_env("AIR_ALERT_USE_WAR_MONITOR_INTEL", default=True),
        intel_max_age_seconds=max(60, _parse_int_env("AIR_ALERT_INTEL_MAX_AGE_SECONDS", default=600)),
        bulletin_cooldown_seconds=max(30, _parse_int_env("AIR_ALERT_BULLETIN_COOLDOWN_SECONDS", default=240)),
        hot_regions_limit=max(3, min(10, _parse_int_env("AIR_ALERT_HOT_REGIONS_LIMIT", default=5))),
    )
    war_monitor_config = WarMonitorConfig(
        enabled=_parse_bool_env("WAR_MONITOR_ENABLED", default=False),
        channel_ids=_parse_id_set_env("WAR_MONITOR_CHANNEL_IDS"),
        channel_username=os.getenv("WAR_MONITOR_CHANNEL_USERNAME", "war_monitor").strip() or "war_monitor",
        poll_seconds=max(30, _parse_int_env("WAR_MONITOR_POLL_SECONDS", default=45)),
        announce_on_startup=_parse_bool_env("WAR_MONITOR_ANNOUNCE_ON_STARTUP", default=False),
    )
    music_config = MusicConfig(
        enabled=_parse_bool_env("MUSIC_ENABLED", default=False),
        lavalink_uri=os.getenv("MUSIC_LAVALINK_URI", "http://127.0.0.1:2333").strip() or "http://127.0.0.1:2333",
        lavalink_password=os.getenv("MUSIC_LAVALINK_PASSWORD", "youshallnotpass").strip() or "youshallnotpass",
        node_identifier=os.getenv("MUSIC_NODE_IDENTIFIER", "eva-node").strip() or "eva-node",
        default_volume=min(150, max(1, _parse_int_env("MUSIC_DEFAULT_VOLUME", default=70))),
        inactive_timeout_seconds=max(30, _parse_int_env("MUSIC_INACTIVE_TIMEOUT_SECONDS", default=180)),
        default_search_source=os.getenv("MUSIC_SEARCH_SOURCE", "ytmsearch").strip() or "ytmsearch",
        fallback_search_source=os.getenv("MUSIC_FALLBACK_SEARCH_SOURCE", "ytsearch").strip() or "ytsearch",
        allowed_role_ids=_parse_id_set_env("MUSIC_ALLOWED_ROLE_IDS"),
        spotify_client_id=os.getenv("MUSIC_SPOTIFY_CLIENT_ID", "").strip(),
        spotify_client_secret=os.getenv("MUSIC_SPOTIFY_CLIENT_SECRET", "").strip(),
        spotify_country_code=os.getenv("MUSIC_SPOTIFY_COUNTRY_CODE", "US").strip() or "US",
    )

    return BotConfig(
        discord=discord_config,
        audit=audit_config,
        nickname_prefix=nickname_prefix_config,
        protection=protection_config,
        chat_banter=chat_banter_config,
        special_dm=special_dm_config,
        pubg=pubg_config,
        steam=steam_config,
        banner=banner_config,
        air_alert=air_alert_config,
        war_monitor=war_monitor_config,
        music=music_config,
    )
