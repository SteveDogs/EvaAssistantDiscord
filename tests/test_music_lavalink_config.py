import unittest

from roseblade_bot.config import MusicConfig
from roseblade_bot.music import render_lavalink_application_yml


class LavalinkConfigRenderTests(unittest.TestCase):
    def test_render_disables_spotify_without_credentials(self) -> None:
        config = MusicConfig(
            enabled=True,
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
        )
        rendered = render_lavalink_application_yml(config)
        self.assertIn('spotify: false', rendered)
        self.assertIn('# clientId: ""', rendered)
        self.assertIn('allowDirectPlaylistIds: true', rendered)
        self.assertIn('- ANDROID_VR', rendered)
        self.assertIn('- TVHTML5_SIMPLY', rendered)

    def test_render_enables_spotify_when_credentials_exist(self) -> None:
        config = MusicConfig(
            enabled=True,
            lavalink_uri="http://127.0.0.1:2333",
            lavalink_password="pass",
            node_identifier="eva-node",
            default_volume=70,
            inactive_timeout_seconds=180,
            default_search_source="ytmsearch",
            fallback_search_source="ytsearch",
            allowed_role_ids=frozenset(),
            spotify_client_id="abc",
            spotify_client_secret="xyz",
            spotify_country_code="UA",
        )
        rendered = render_lavalink_application_yml(config)
        self.assertIn('spotify: true', rendered)
        self.assertIn('clientId: "abc"', rendered)
        self.assertIn('countryCode: "UA"', rendered)


if __name__ == "__main__":
    unittest.main()
