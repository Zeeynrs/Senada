import unittest
from unittest.mock import patch

from senada.lru import BoundedCache


class BoundedCacheTests(unittest.TestCase):
    def test_oldest_entry_goes_first(self):
        c = BoundedCache(2)
        c["a"], c["b"], c["c"] = 1, 2, 3
        self.assertNotIn("a", c)
        self.assertEqual((c.get("b"), c["c"], len(c)), (2, 3, 2))

    def test_reading_keeps_an_entry(self):
        c = BoundedCache(2)
        c["a"], c["b"] = 1, 2
        c.get("a")
        c["c"] = 3
        self.assertIn("a", c)
        self.assertNotIn("b", c)

    def test_a_batch_over_the_limit_is_kept_whole(self):
        c = BoundedCache(3)
        c["old"] = 0
        c.put_many((n, n) for n in range(5))
        self.assertNotIn("old", c)
        self.assertEqual(len(c), 5)
        c["next"] = 9  # back to the limit with the next single entry
        self.assertEqual(len(c), 3)

    def test_pop_and_clear(self):
        c = BoundedCache(3)
        c["a"] = 1
        self.assertEqual((c.pop("a"), c.pop("a", "gone")), (1, "gone"))
        c["b"] = 2
        c.clear()
        self.assertEqual(len(c), 0)


class PlayerTrackCacheTests(unittest.TestCase):
    def setUp(self):
        from senada.player import Player
        from tests.test_playback_extras import FakeResolver, FakeStore, IdleEngine, SyncWorker, song

        class LikeStore(FakeStore):
            def __init__(self):
                self.liked = []

            def set_liked(self, track, liked):
                self.liked.append((track["uri"], liked))
                return True

        self.song = song
        self.store = LikeStore()
        with patch("senada.player.TRACK_CACHE_LIMIT", 3):
            self.player = Player(SyncWorker(), IdleEngine(), FakeResolver({}), {}, self.store, None)

    def test_pages_seen_long_ago_are_forgotten(self):
        for n in range(1, 6):
            self.player.cache_tracks([self.song(n)])
        self.assertIsNone(self.player._known("spotify:track:1"))
        self.assertIsNotNone(self.player._known("spotify:track:5"))

    def test_a_queued_track_can_still_be_liked_after_it_left_the_cache(self):
        self.player._queue = [self.song(1)]
        self.player.cache_tracks([self.song(n) for n in range(2, 6)])
        self.player.cache_tracks([self.song(9)])
        self.assertNotIn("spotify:track:1", self.player._track_cache)
        self.player.setLiked("spotify:track:1", True)
        self.assertEqual(self.store.liked, [("spotify:track:1", True)])


if __name__ == "__main__":
    unittest.main()
