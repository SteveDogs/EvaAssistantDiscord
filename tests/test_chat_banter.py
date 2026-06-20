import unittest

from roseblade_bot.chat_banter import load_chat_banter, normalize_text


class ChatBanterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = load_chat_banter()

    def test_normalize_text_flattens_variants(self) -> None:
        self.assertEqual(normalize_text("Ёпт,  test!!"), "епт test")

    def test_default_trigger_reply_is_not_empty(self) -> None:
        self.assertTrue(self.pack.contains_trigger("пиздец"))
        self.assertTrue(self.pack.render_reply("Стив", "пиздец"))

    def test_strict_trigger_reply_is_not_empty(self) -> None:
        self.assertTrue(self.pack.contains_trigger("гитлер"))
        self.assertTrue(self.pack.render_reply("Стив", "гитлер"))


if __name__ == "__main__":
    unittest.main()
