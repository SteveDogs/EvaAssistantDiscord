import random
import unittest

from roseblade_bot.special_dm import SPECIAL_DM


class SpecialDmTests(unittest.TestCase):
    def test_voice_join_mentions_channel_and_has_variety(self) -> None:
        random.seed(42)
        rendered = {SPECIAL_DM.render_voice_join(channel_name="Розовый войс") for _ in range(40)}
        self.assertGreaterEqual(len(rendered), 10)
        for message in rendered:
            self.assertIsInstance(message, str)
            self.assertTrue(message.strip())

    def test_avatar_changed_has_variety(self) -> None:
        random.seed(1337)
        rendered = {SPECIAL_DM.render_avatar_changed() for _ in range(40)}
        self.assertGreaterEqual(len(rendered), 10)
        for message in rendered:
            self.assertIsInstance(message, str)
            self.assertTrue(message.strip())


if __name__ == "__main__":
    unittest.main()
