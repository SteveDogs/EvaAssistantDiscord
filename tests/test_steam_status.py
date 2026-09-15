from types import SimpleNamespace
import unittest

from roseblade_bot.config import SteamStatusConfig
from roseblade_bot.steam_status import SteamServiceProbe, SteamStatusService


def _service() -> SteamStatusService:
    return SteamStatusService(
        SimpleNamespace(
            steam_status=SteamStatusConfig(
                enabled=True,
                channel_ids=frozenset({1398263697893359749}),
                poll_minutes=2,
                failure_threshold=2,
                cooldown_minutes=30,
                announce_on_startup=False,
            )
        )
    )


class SteamStatusTests(unittest.TestCase):
    def test_builds_incident_embed(self) -> None:
        embed = _service().build_incident_embed(
            (SteamServiceProbe("store", "Магазин Steam", False, None, "HTTP 503"),)
        )
        self.assertIn("неполадки", embed.title or "")
        self.assertIn("Магазин Steam", embed.fields[0].value)

    def test_builds_recovery_embed(self) -> None:
        embed = _service().build_recovery_embed(
            (SteamServiceProbe("web_api", "Steam Web API", True, 120, None),),
            "4 мин",
        )
        self.assertIn("снова отвечает", embed.title or "")
        self.assertEqual(embed.fields[1].value, "4 мин")

    def test_builds_normal_embed(self) -> None:
        embed = _service().build_normal_embed(
            (SteamServiceProbe("community", "Steam Community", True, 85, None),)
        )
        self.assertIn("работает штатно", embed.title or "")
        self.assertIn("85 мс", embed.fields[0].value)


if __name__ == "__main__":
    unittest.main()
