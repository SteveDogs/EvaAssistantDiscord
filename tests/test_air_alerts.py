from datetime import datetime, timezone
from pathlib import Path
import unittest

from roseblade_bot.alert_intel import ThreatIntelHint
from roseblade_bot.air_alerts import (
    ActiveAlertRecord,
    AirAlertService,
    AirAlertSnapshot,
    OBLAST_STATUS_ORDER,
    RegionSnapshot,
    STATUS_ACTIVE,
    STATUS_NO_ALERT,
    STATUS_PARTIAL,
)
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
            enabled=True,
            channel_ids=frozenset({1518950671163068567}),
            provider="auto",
            api_token="alerts-token",
            ubilling_source="default",
            poll_seconds=60,
            title="Карта повітряних тривог України",
            use_war_monitor_intel=True,
            intel_max_age_seconds=600,
            bulletin_cooldown_seconds=240,
            hot_regions_limit=6,
        ),
        war_monitor=WarMonitorConfig(
            enabled=False,
            channel_ids=frozenset(),
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


def _build_snapshot(*, status_overrides: dict[str, str], started_at: datetime | None = None) -> AirAlertSnapshot:
    alert = ActiveAlertRecord(
        location_title="Київ",
        location_type="oblast",
        location_uid="test-uid",
        location_oblast="м. Київ",
        alert_type="air_raid",
        started_at=started_at,
        notes="",
    )
    regions = {
        title: RegionSnapshot(
            title=title,
            status=status_overrides.get(title, STATUS_NO_ALERT),
            alerts=(alert,) if status_overrides.get(title, STATUS_NO_ALERT) != STATUS_NO_ALERT else (),
            started_at=started_at if status_overrides.get(title, STATUS_NO_ALERT) != STATUS_NO_ALERT else None,
        )
        for title in OBLAST_STATUS_ORDER
    }
    status_string = "".join(regions[title].status for title in OBLAST_STATUS_ORDER)
    return AirAlertSnapshot(
        fetched_at=datetime.now(timezone.utc),
        oblast_status_string=status_string,
        regions=regions,
        provider_key="alerts_in_ua",
        source_label="alerts.in.ua",
    )


class AirAlertTests(unittest.TestCase):
    def test_detect_transitions_reports_started_alert(self) -> None:
        service = AirAlertService(_build_config())
        started_at = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
        snapshot = _build_snapshot(
            status_overrides={"м. Київ": STATUS_ACTIVE},
            started_at=started_at,
        )

        transitions = service.detect_transitions(STATUS_NO_ALERT * len(OBLAST_STATUS_ORDER), snapshot, {})

        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].region_title, "м. Київ")
        self.assertEqual(transitions[0].kind, "started")
        self.assertEqual(transitions[0].current_started_at, started_at)

    def test_detect_transitions_reports_alert_end(self) -> None:
        service = AirAlertService(_build_config())
        previous_started_at = datetime(2026, 6, 23, 10, 30, tzinfo=timezone.utc)
        snapshot = _build_snapshot(status_overrides={})
        previous_status_string = "".join(
            STATUS_PARTIAL if title == "Київська область" else STATUS_NO_ALERT
            for title in OBLAST_STATUS_ORDER
        )

        transitions = service.detect_transitions(
            previous_status_string,
            snapshot,
            {"Київська область": previous_started_at},
        )

        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].region_title, "Київська область")
        self.assertEqual(transitions[0].kind, "ended")
        self.assertEqual(transitions[0].previous_started_at, previous_started_at)

    def test_provider_auto_falls_back_to_ubilling_without_token(self) -> None:
        config = _build_config()
        config.air_alert.api_token = ""
        service = AirAlertService(config)

        self.assertEqual(service.requested_provider_key, "auto")
        self.assertEqual(service.resolved_provider_key, "ubilling")
        self.assertTrue(service.is_configured)

    def test_transition_embed_uses_matching_intel_hint(self) -> None:
        service = AirAlertService(_build_config())
        started_at = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
        snapshot = _build_snapshot(
            status_overrides={"Київська область": STATUS_ACTIVE},
            started_at=started_at,
        )
        transition = service.detect_transitions(STATUS_NO_ALERT * len(OBLAST_STATUS_ORDER), snapshot, {})[0]
        hint = ThreatIntelHint(
            post_id=101,
            published_at=snapshot.fetched_at,
            kind="drone",
            label="БпЛА / шахеди",
            short_label="БпЛА",
            excerpt="Група БпЛА курсом на Київщину.",
            raw_text="Група БпЛА курсом на Київщину.",
            regions=("Київська область",),
            is_national=False,
            url="https://t.me/war_monitor/101",
        )

        embed = service.build_transition_embed(transition, snapshot, (hint,))

        field_map = {field.name: field.value for field in embed.fields}
        self.assertIn("БпЛА / шахеди", field_map["Ймовірна загроза"])
        self.assertIn("Група БпЛА курсом на Київщину.", field_map["Сигнал"])

    def test_provider_label_uses_alerts_in_ua_when_token_present(self) -> None:
        service = AirAlertService(_build_config())

        self.assertEqual(service.provider_label(), "alerts.in.ua")

    def test_alerts_in_ua_error_message_for_401_is_human_readable(self) -> None:
        message = AirAlertService._alerts_in_ua_error_message(
            "https://api.alerts.in.ua/v1/alerts/active.json",
            401,
        )

        self.assertIn("токен не принят", message)
        self.assertIn("AIR_ALERT_API_TOKEN", message)

    def test_alerts_in_ua_error_message_for_429_mentions_poll_interval(self) -> None:
        message = AirAlertService._alerts_in_ua_error_message(
            "https://api.alerts.in.ua/v1/iot/active_air_raid_alerts_by_oblast.json",
            429,
        )

        self.assertIn("лимит", message)
        self.assertIn("AIR_ALERT_POLL_SECONDS", message)


if __name__ == "__main__":
    unittest.main()
