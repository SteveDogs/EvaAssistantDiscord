from types import SimpleNamespace
import unittest

import wavelink

from roseblade_bot.config import MusicConfig
from roseblade_bot.music.service import (
    MusicAutocompleteSuggestion,
    MusicService,
    _build_soundcloud_search_queries,
    _build_autocomplete_suggestion,
    _select_best_soundcloud_candidate,
    _summarize_track_exception,
    _truncate_choice_text,
)


class MusicServiceFormattingTests(unittest.TestCase):
    def test_truncate_choice_text_keeps_short_value(self) -> None:
        self.assertEqual(_truncate_choice_text("Алла Пугачева"), "Алла Пугачева")

    def test_truncate_choice_text_limits_length(self) -> None:
        value = _truncate_choice_text("a" * 140)
        self.assertLessEqual(len(value), 100)
        self.assertTrue(value.endswith("…"))

    def test_build_autocomplete_suggestion_prefers_short_uri(self) -> None:
        track = SimpleNamespace(
            title="Миллион алых роз",
            author="Алла Пугачева",
            length=257000,
            uri="https://youtu.be/example123",
        )

        suggestion = _build_autocomplete_suggestion(track)

        self.assertIsInstance(suggestion, MusicAutocompleteSuggestion)
        self.assertEqual(suggestion.value, "https://youtu.be/example123")
        self.assertIn("Алла Пугачева", suggestion.label)
        self.assertIn("Миллион алых роз", suggestion.label)

    def test_build_autocomplete_suggestion_falls_back_from_long_uri(self) -> None:
        track = SimpleNamespace(
            title="Песня " + ("очень " * 20),
            author="Артист",
            length=190000,
            uri="https://example.com/" + ("x" * 120),
        )

        suggestion = _build_autocomplete_suggestion(track)

        self.assertLessEqual(len(suggestion.label), 100)
        self.assertLessEqual(len(suggestion.value), 100)
        self.assertNotEqual(suggestion.value, track.uri)
        self.assertIn("Артист", suggestion.value)

    def test_summarize_track_exception_recognizes_login_block(self) -> None:
        text = _summarize_track_exception("All clients failed to load the item. This video requires login.")
        self.assertIn("YouTube", text)
        self.assertIn("авториза", text.lower())

    def test_build_soundcloud_queries_strips_topic_suffix(self) -> None:
        track = SimpleNamespace(title="Dark", author="DEADLUVE - Topic")
        queries = _build_soundcloud_search_queries(track, "https://music.youtube.com/watch?v=test")
        self.assertEqual(queries[0], "DEADLUVE Dark")
        self.assertIn("Dark", queries)

    def test_select_best_soundcloud_candidate_prefers_matching_title(self) -> None:
        best = SimpleNamespace(title="Dark", author="DEADLUVE")
        wrong = SimpleNamespace(title="I Adore You (Dj Dark Remix)", author="Dj Dark")
        selected = _select_best_soundcloud_candidate(
            [wrong, best],
            target_title="Dark",
            target_author="DEADLUVE - Topic",
        )
        self.assertIs(selected, best)


class _FakeQueue:
    def __init__(self, *items: object) -> None:
        self._items = list(items)

    def get(self) -> object:
        if not self._items:
            raise wavelink.QueueEmpty
        return self._items.pop(0)


class _FakePlayer:
    def __init__(self, *queued_tracks: object) -> None:
        self.guild = SimpleNamespace(id=77)
        self.queue = _FakeQueue(*queued_tracks)
        self.volume = 35
        self.current = None
        self.play_calls: list[tuple[object, dict[str, object]]] = []

    async def play(self, track: object, **kwargs: object) -> None:
        self.current = track
        self.play_calls.append((track, kwargs))


class MusicServiceRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def _build_service(self) -> MusicService:
        config = MusicConfig(
            enabled=True,
            lavalink_uri="http://127.0.0.1:2333",
            lavalink_password="youshallnotpass",
            node_identifier="eva-node",
            default_volume=30,
            inactive_timeout_seconds=60,
            default_search_source="ytmsearch",
            fallback_search_source="ytsearch",
            allowed_role_ids=frozenset(),
            spotify_client_id="",
            spotify_client_secret="",
            spotify_country_code="US",
        )
        return MusicService(config)

    async def test_track_exception_continues_with_next_queue_item_without_channel(self) -> None:
        service = self._build_service()
        next_track = SimpleNamespace(title="Следующий трек")
        player = _FakePlayer(next_track)
        broken_track = SimpleNamespace(
            title="Сломанный трек",
            author="Broken Artist",
            source="youtube",
            uri="https://youtube.example/broken",
            extras={},
        )
        payload = SimpleNamespace(
            player=player,
            track=broken_track,
            exception="source exploded",
        )

        async def no_rescue(_bot: object, _payload: object) -> bool:
            return False

        service._try_soundcloud_rescue = no_rescue  # type: ignore[method-assign]

        await service.announce_track_exception(SimpleNamespace(), payload)

        self.assertEqual(len(player.play_calls), 1)
        played_track, kwargs = player.play_calls[0]
        self.assertIs(played_track, next_track)
        self.assertEqual(kwargs["volume"], 35)


if __name__ == "__main__":
    unittest.main()
