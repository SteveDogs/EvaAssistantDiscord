import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from roseblade_bot.config import load_config
from roseblade_bot.steam_profile_watch import SteamProfileSnapshot, SteamProfileWatchService


class SteamProfileWatchTests(unittest.TestCase):
    def _build_service(self) -> SteamProfileWatchService:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "DISCORD_TOKEN=test-token",
                        "STEAM_API_KEY=test-steam-key",
                        "STEAM_PROFILE_WATCH_ENABLED=true",
                        "STEAM_PROFILE_WATCH_CHANNEL_IDS=1354908421811601520",
                        "STEAM_PROFILE_WATCH_TARGETS=76561199076106595=стив|steve|stevedogs",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = load_config(root)
        return SteamProfileWatchService(config)

    def test_resolve_target_from_human_request(self) -> None:
        service = self._build_service()
        self.assertTrue(service._looks_like_request("Ева а что там у стива?"))  # type: ignore[attr-defined]
        target = service.resolve_target("Ева а что там у стива?")
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.steamid, 76561199076106595)

    def test_describe_changes_tracks_game_and_name(self) -> None:
        service = self._build_service()
        previous = SteamProfileSnapshot(
            steamid=76561199076106595,
            persona_name="SteveDogs",
            profile_url="https://steamcommunity.com/profiles/76561199076106595/",
            avatar_url="https://cdn/a.png",
            avatar_hash="a.png",
            visibility_state=3,
            persona_state=0,
            current_game_name=None,
            current_game_appid=None,
            last_logoff=None,
            steam_level=30,
            owned_game_count=120,
            recent_games=(),
            community_banned=False,
            vac_banned=False,
            vac_ban_count=0,
            game_ban_count=0,
            economy_ban="none",
        )
        current = SteamProfileSnapshot(
            steamid=76561199076106595,
            persona_name="Steve Dogs",
            profile_url="https://steamcommunity.com/profiles/76561199076106595/",
            avatar_url="https://cdn/b.png",
            avatar_hash="b.png",
            visibility_state=3,
            persona_state=1,
            current_game_name="PUBG: BATTLEGROUNDS",
            current_game_appid=578080,
            last_logoff=None,
            steam_level=31,
            owned_game_count=121,
            recent_games=(),
            community_banned=False,
            vac_banned=False,
            vac_ban_count=0,
            game_ban_count=0,
            economy_ban="none",
        )
        changes = service.describe_changes(previous, current)
        joined = "\n".join(changes)
        self.assertIn("Ник сменился", joined)
        self.assertIn("Аватарка обновилась", joined)
        self.assertIn("Залетел в", joined)
        self.assertIn("Steam level", joined)
        self.assertIn("Библиотека изменилась", joined)


if __name__ == "__main__":
    unittest.main()
