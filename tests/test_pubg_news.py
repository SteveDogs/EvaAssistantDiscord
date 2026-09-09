from types import SimpleNamespace
import unittest

from roseblade_bot.config import PubgNewsConfig
from roseblade_bot.pubg_news import PubgNewsService


def _service() -> PubgNewsService:
    return PubgNewsService(
        SimpleNamespace(
            pubg_news=PubgNewsConfig(
                enabled=True,
                channel_ids=frozenset({1398263697893359749}),
                poll_minutes=30,
                official_news_url="https://pubg.com/ru/news",
                telegram_username="iBakhmetNews",
                include_telegram=True,
                announce_on_startup=False,
                max_posts_per_run=2,
                translation_max_characters=500,
            )
        )
    )


class PubgNewsTests(unittest.TestCase):
    def test_parses_official_open_graph_metadata(self) -> None:
        html = (
            '<meta property="og:title" content="PUBG x Event - НОВОСТИ — PUBG: BATTLEGROUNDS">'
            '<meta property="og:description" content="A short announcement.">'
            '<meta property="og:image" content="https://cdn.example/image.jpg">'
            '<meta property="article:published_time" content="2026-09-09T10:00:00+00:00">'
        )
        post = _service()._parse_official_post("10991", "https://pubg.com/ru/news/10991", html)
        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post.title, "PUBG x Event")
        self.assertEqual(post.excerpt, "A short announcement.")
        self.assertEqual(post.image_url, "https://cdn.example/image.jpg")
        self.assertEqual(post.key, "official:10991")

    def test_shorten_preserves_readable_excerpt(self) -> None:
        result = _service()._shorten("one two three four five", 16)
        self.assertEqual(result, "one two three…")

    def test_parses_official_listing_without_html_links(self) -> None:
        html = (
            '<li class="post-contents__card"><img src="https://cdn.example/cover.jpg">'
            '<dl class="post__description"><dt>Update 43.1</dt><dd>New map rotation.</dd></dl>'
            '<dl class="post__bottom"><dd>2026.09.09</dd></dl></li>'
            'news:{posts:[{postId:11057,title:"Update 43.1"}],size:1}'
        )
        posts = _service()._parse_official_listing(html)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].key, "official:11057")
        self.assertEqual(posts[0].url, "https://pubg.com/ru/news/11057")


if __name__ == "__main__":
    unittest.main()
