from datetime import datetime, timezone
from pathlib import Path
import unittest

from roseblade_bot.config import (
    AirAlertConfig,
    AuditConfig,
    BotConfig,
    ChatBanterConfig,
    DiscordConfig,
    DiscordIntentsConfig,
    MusicConfig,
    NicknamePrefixConfig,
    ProtectedBanConfig,
    ProtectedVoiceGuardConfig,
    ProtectionConfig,
    PubgConfig,
    ServerBannerConfig,
    SpecialDmConfig,
    SteamDigestConfig,
    WarMonitorConfig,
)
from roseblade_bot.war_monitor import WarMonitorPost, WarMonitorService


def _build_config() -> BotConfig:
    return BotConfig(
        discord=DiscordConfig(
            token="test-token",
            guild_id=None,
            state_file=Path("data/test_state.json"),
            intents=DiscordIntentsConfig(members=False, presences=False, message_content=False),
        ),
        audit=AuditConfig(category_name="Аудит", category_id=None, ignored_channel_ids=frozenset()),
        nickname_prefix=NicknamePrefixConfig(
            rules={},
            user_rules={},
            legacy_prefixes=frozenset(),
            excluded_user_ids=frozenset(),
            resync_minutes=180,
        ),
        protection=ProtectionConfig(
            bans=ProtectedBanConfig(enabled=False, auto_capture=False, enforce_minutes=5),
            voice_guard=ProtectedVoiceGuardConfig(enabled=False, user_ids=frozenset()),
        ),
        chat_banter=ChatBanterConfig(
            enabled=False,
            reply_chance=0.0,
            channel_cooldown_seconds=0,
            user_cooldown_seconds=0,
        ),
        special_dm=SpecialDmConfig(
            enabled=False,
            user_ids=frozenset(),
            events=frozenset(),
            voice_join_cooldown_seconds=0,
            avatar_change_cooldown_seconds=0,
        ),
        pubg=PubgConfig(
            enabled=False,
            channel_ids=frozenset(),
            allowed_role_ids=frozenset(),
            api_key="",
            steam_api_key="",
            platform="steam",
            include_ranked=False,
            include_lifetime_stats=False,
            cache_ttl_seconds=900,
            user_cooldown_seconds=20,
        ),
        steam=SteamDigestConfig(
            enabled=False,
            channel_ids=frozenset(),
            hour=20,
            minute=0,
            timezone="Europe/Simferopol",
            top_count=15,
            include_support_stats=False,
        ),
        banner=ServerBannerConfig(
            enabled=False,
            update_minutes=2,
            title="ROSE BLADE",
            background_url="",
            background_path=None,
            font_path=None,
            excluded_channel_ids=frozenset(),
        ),
        air_alert=AirAlertConfig(
            enabled=False,
            channel_ids=frozenset(),
            provider="auto",
            api_token="",
            ubilling_source="default",
            poll_seconds=60,
            title="Карта повітряних тривог України",
            use_war_monitor_intel=True,
            intel_max_age_seconds=600,
            bulletin_cooldown_seconds=240,
            hot_regions_limit=6,
        ),
        war_monitor=WarMonitorConfig(
            enabled=True,
            channel_ids=frozenset({1518950671163068567}),
            channel_username="war_monitor",
            poll_seconds=45,
            announce_on_startup=False,
        ),
        music=MusicConfig(
            enabled=False,
            lavalink_uri="http://127.0.0.1:2333",
            lavalink_password="pass",
            node_identifier="eva-node",
            default_volume=70,
            inactive_timeout_seconds=180,
            default_search_source="ytmsearch",
            fallback_search_source="ytsearch",
            allowed_role_ids=frozenset(),
            spotify_client_id="",
            spotify_client_secret="",
            spotify_country_code="US",
        ),
    )


class WarMonitorTests(unittest.TestCase):
    def test_relevant_threat_detection(self) -> None:
        service = WarMonitorService(_build_config())
        self.assertTrue(service.is_relevant_threat("Загроза балістики з Криму. Увага."))
        self.assertTrue(service.is_relevant_threat("⚠️ 2х реактивних БпЛА над Київським водосховищем у напрямку Києва."))
        self.assertFalse(service.is_relevant_threat("⚪️ Відбій загрози МіГ-31К."))
        self.assertFalse(service.is_relevant_threat("Київщина чисто."))
        self.assertFalse(service.is_relevant_threat("Обстановка станом на 00:00 22.06.26"))

    def test_message_rendering_keeps_footer_and_quote(self) -> None:
        service = WarMonitorService(_build_config())
        post = WarMonitorPost(
            post_id=40860,
            published_at=datetime.now(timezone.utc),
            text="Загроза балістики з Криму. Увага.\nІмовірний пуск ракет системи «Іскандер».",
            url="https://t.me/war_monitor/40860",
        )

        message = service.build_alert_message(post)

        self.assertIn("Ева", message)
        self.assertIn("> Загроза балістики з Криму. Увага.", message)
        self.assertNotIn("Информация взята @war_monitor", message)
        self.assertNotIn("https://t.me/war_monitor/40860", message)

    def test_extract_intel_detects_regions_and_kind(self) -> None:
        service = WarMonitorService(_build_config())
        post = WarMonitorPost(
            post_id=40861,
            published_at=datetime.now(timezone.utc),
            text="⚠️ 2х реактивних БпЛА над Київським водосховищем у напрямку Києва.",
            url="https://t.me/war_monitor/40861",
        )

        hint = service.extract_intel(post)

        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertEqual(hint.kind, "drone")
        self.assertIn("м. Київ", hint.regions)
        self.assertEqual(hint.short_label, "БпЛА")

    def test_extract_intel_marks_national_ballistic_when_no_region(self) -> None:
        service = WarMonitorService(_build_config())
        post = WarMonitorPost(
            post_id=40862,
            published_at=datetime.now(timezone.utc),
            text="🟣 Загроза балістики з Криму. Увага.",
            url="https://t.me/war_monitor/40862",
        )

        hint = service.extract_intel(post)

        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertEqual(hint.kind, "ballistic")
        self.assertTrue(hint.is_national)


if __name__ == "__main__":
    unittest.main()
