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
                        "PUBG_LOOKUP_ENABLED=true",
                        "PUBG_PLATFORM=steam",
                        "SERVER_BANNER_ENABLED=true",
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
            self.assertTrue(config.pubg.enabled)
            self.assertEqual(config.pubg.platform, "steam")
            self.assertTrue(config.server_banner_enabled)


if __name__ == "__main__":
    unittest.main()
