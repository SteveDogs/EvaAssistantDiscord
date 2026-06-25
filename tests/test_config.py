import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from roseblade_bot.config import load_config


class ConfigTests(unittest.TestCase):
    def test_nested_and_legacy_config_access(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "DISCORD_TOKEN=test-token",
                        "GUILD_ID=123456789",
                        "ENABLE_MEMBERS_INTENT=true",
                        "ENABLE_PRESENCES_INTENT=true",
                        "ENABLE_MESSAGE_CONTENT_INTENT=true",
                        "NICK_PREFIX_RULES=1=🌸;2=⭐️",
                        "NICK_PREFIX_USER_RULES=380036631584833558=💅",
                        "PUBG_LOOKUP_ENABLED=true",
                        "PUBG_PLATFORM=steam",
                        "SPECIAL_DM_ENABLED=true",
                        "SPECIAL_DM_USER_IDS=495309668986388520",
                        "SPECIAL_DM_EVENTS=voice_joined;avatar_changed",
                        "SERVER_BANNER_ENABLED=true",
                        "SERVER_BANNER_EXCLUDED_CHANNEL_IDS=11;22,33",
                        "AIR_ALERT_ENABLED=true",
                        "AIR_ALERT_CHANNEL_IDS=1518950671163068567;1518950671163068568",
                        "AIR_ALERT_PROVIDER=ubilling",
                        "AIR_ALERT_API_TOKEN=alerts-token",
                        "AIR_ALERT_UBILLING_SOURCE=default",
                        "AIR_ALERT_POLL_SECONDS=75",
                        "AIR_ALERT_TITLE=Карта повітряних тривог України",
                        "AIR_ALERT_USE_WAR_MONITOR_INTEL=true",
                        "AIR_ALERT_INTEL_MAX_AGE_SECONDS=900",
                        "AIR_ALERT_BULLETIN_COOLDOWN_SECONDS=180",
                        "AIR_ALERT_HOT_REGIONS_LIMIT=7",
                        "WAR_MONITOR_ENABLED=true",
                        "WAR_MONITOR_CHANNEL_IDS=1518950671163068567",
                        "WAR_MONITOR_CHANNEL_USERNAME=war_monitor",
                        "WAR_MONITOR_POLL_SECONDS=30",
                        "WAR_MONITOR_ANNOUNCE_ON_STARTUP=false",
                        "MUSIC_ENABLED=true",
                        "MUSIC_LAVALINK_URI=http://127.0.0.1:2333",
                        "MUSIC_LAVALINK_PASSWORD=test-pass",
                        "MUSIC_NODE_IDENTIFIER=rose-node",
                        "MUSIC_DEFAULT_VOLUME=88",
                        "MUSIC_INACTIVE_TIMEOUT_SECONDS=222",
                        "MUSIC_SEARCH_SOURCE=ytmsearch",
                        "MUSIC_FALLBACK_SEARCH_SOURCE=ytsearch",
                        "MUSIC_ALLOWED_ROLE_IDS=7;8",
                        "MUSIC_SPOTIFY_CLIENT_ID=spotify-id",
                        "MUSIC_SPOTIFY_CLIENT_SECRET=spotify-secret",
                        "MUSIC_SPOTIFY_COUNTRY_CODE=UA",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(root)

            self.assertEqual(config.discord.token, "test-token")
            self.assertEqual(config.token, "test-token")
            self.assertEqual(config.discord.guild_id, 123456789)
            self.assertTrue(config.discord.intents.members)
            self.assertTrue(config.enable_message_content_intent)
            self.assertEqual(config.nickname_prefix.rules[1], "🌸")
            self.assertEqual(config.nickname_prefix.user_rules[380036631584833558], "💅")
            self.assertTrue(config.pubg.enabled)
            self.assertEqual(config.pubg.platform, "steam")
            self.assertTrue(config.special_dm.enabled)
            self.assertEqual(config.special_dm.user_ids, frozenset({495309668986388520}))
            self.assertEqual(config.special_dm.events, frozenset({"voice_joined", "avatar_changed"}))
            self.assertTrue(config.server_banner_enabled)
            self.assertEqual(config.banner.excluded_channel_ids, frozenset({11, 22, 33}))
            self.assertEqual(config.server_banner_excluded_channel_ids, frozenset({11, 22, 33}))
            self.assertTrue(config.air_alert.enabled)
            self.assertEqual(config.air_alert.channel_ids, frozenset({1518950671163068567, 1518950671163068568}))
            self.assertEqual(config.air_alert.provider, "ubilling")
            self.assertEqual(config.air_alert.api_token, "alerts-token")
            self.assertEqual(config.air_alert.ubilling_source, "default")
            self.assertEqual(config.air_alert.poll_seconds, 75)
            self.assertEqual(config.air_alert.title, "Карта повітряних тривог України")
            self.assertTrue(config.air_alert.use_war_monitor_intel)
            self.assertEqual(config.air_alert.intel_max_age_seconds, 900)
            self.assertEqual(config.air_alert.bulletin_cooldown_seconds, 180)
            self.assertEqual(config.air_alert.hot_regions_limit, 7)
            self.assertEqual(config.air_alert_channel_ids, frozenset({1518950671163068567, 1518950671163068568}))
            self.assertTrue(config.war_monitor.enabled)
            self.assertEqual(config.war_monitor.channel_ids, frozenset({1518950671163068567}))
            self.assertEqual(config.war_monitor.channel_username, "war_monitor")
            self.assertEqual(config.war_monitor.poll_seconds, 30)
            self.assertFalse(config.war_monitor.announce_on_startup)
            self.assertTrue(config.music.enabled)
            self.assertEqual(config.music.lavalink_uri, "http://127.0.0.1:2333")
            self.assertEqual(config.music.lavalink_password, "test-pass")
            self.assertEqual(config.music.node_identifier, "rose-node")
            self.assertEqual(config.music.default_volume, 88)
            self.assertEqual(config.music.inactive_timeout_seconds, 222)
            self.assertEqual(config.music.allowed_role_ids, frozenset({7, 8}))
            self.assertEqual(config.music.spotify_client_id, "spotify-id")
            self.assertEqual(config.music.spotify_country_code, "UA")
            self.assertEqual(config.music_search_source, "ytmsearch")


if __name__ == "__main__":
    unittest.main()
