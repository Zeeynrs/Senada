import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from senada.player import Player
from tests.test_playback_extras import FakeResolver, FakeStore, FakeStreams, IdleEngine, SyncWorker, song


class FakeCatalog:
    def __init__(self, tracks):
        self._tracks = tracks

    def tracks_for(self, _ctx):
        return list(self._tracks)


class QueueManagementTests(unittest.TestCase):
    def setUp(self):
        self.tracks = [song(1), song(2), song(3), song(4), song(5)]
        matches = {f"spotify:track:{n}": {"v": f"v{n}", "s": 100} for n in range(1, 10)}
        self.engine = IdleEngine()
        self.player = Player(SyncWorker(), self.engine, FakeResolver(matches), {}, FakeStore(), FakeCatalog(self.tracks))
        self.player.streams = FakeStreams({f"v{n}": f"https://audio/{n}" for n in range(1, 10)})
        self.player.cache_tracks([song(n) for n in range(1, 10)])

    def test_unshuffle_restores_original_order(self):
        self.player._start_queue(self.tracks, index=1, context_uri="yt:playlist:p1")
        self.assertEqual([t["uri"] for t in self.player.queue],
                         ["spotify:track:3", "spotify:track:4", "spotify:track:5"])

        with patch("senada.player.random.shuffle", side_effect=lambda xs: xs.reverse()):
            self.player.toggleShuffle()
        self.assertTrue(self.player.state["shuffle"])
        self.assertEqual(self.player.state["uri"], "spotify:track:2")
        self.assertEqual([t["uri"] for t in self.player.queue],
                         ["spotify:track:5", "spotify:track:4", "spotify:track:3", "spotify:track:1"])

        self.player.toggleShuffle()
        self.assertFalse(self.player.state["shuffle"])
        self.assertEqual(self.player.state["uri"], "spotify:track:2")
        self.assertEqual([t["uri"] for t in self.player.queue],
                         ["spotify:track:3", "spotify:track:4", "spotify:track:5"])
        self.assertEqual(self.player._queue_index, 1)

    def test_shuffle_play_preserves_unshuffled_order(self):
        with patch("senada.player.random.shuffle", side_effect=lambda xs: xs.reverse()):
            self.player.shufflePlay("yt:playlist:p1")
        self.assertTrue(self.player.state["shuffle"])
        self.assertEqual(self.player.state["uri"], "spotify:track:5")

        self.player.toggleShuffle()
        self.assertFalse(self.player.state["shuffle"])
        self.assertEqual(self.player.state["uri"], "spotify:track:5")
        self.assertEqual(self.player._queue_index, 4)

    def test_play_next_move_remove_clear(self):
        self.player._start_queue([song(1), song(2), song(3)], index=0)
        self.player.playNext("spotify:track:6")
        self.assertEqual([t["uri"] for t in self.player.queue],
                         ["spotify:track:6", "spotify:track:2", "spotify:track:3"])

        self.player.moveInQueue(2, 0)
        self.assertEqual([t["uri"] for t in self.player.queue],
                         ["spotify:track:3", "spotify:track:6", "spotify:track:2"])

        self.player.removeFromQueue(1)
        self.assertEqual([t["uri"] for t in self.player.queue],
                         ["spotify:track:3", "spotify:track:2"])

        # out-of-bounds operations are safely ignored
        self.player.removeFromQueue(99)
        self.player.moveInQueue(0, 99)
        self.assertEqual(len(self.player.queue), 2)

        self.player.clearQueue()
        self.assertEqual(self.player.queue, [])
        self.assertEqual(self.player.state["uri"], "spotify:track:1")
        self.assertEqual([t["uri"] for t in self.player.fullQueue()], ["spotify:track:1"])


class AutoplayTests(unittest.TestCase):
    def setUp(self):
        self.matches = {
            **{f"spotify:track:{n}": {"v": f"v{n}", "s": 100} for n in (1, 2, 3)},
            **{f"yt:track:v{n}": {"v": f"v{n}", "s": 100} for n in (1, 2, 3)},
        }
        self.settings = {"autoplay": False}
        self.engine = IdleEngine()
        self.player = Player(SyncWorker(), self.engine, FakeResolver(self.matches), self.settings, FakeStore(), None)
        self.player.streams = FakeStreams({"v1": "https://audio/1", "v2": "https://audio/2", "v3": "https://audio/3"})

    def test_autoplay_setting_and_continuation(self):
        yt_seed = {**song(1), "uri": "yt:track:v1", "id": "v1"}
        radio_hits = [
            {**song(1), "uri": "yt:track:v1", "id": "v1"},  # duplicate seed should be skipped
            {**song(2), "uri": "yt:track:v2", "id": "v2"},
            {**song(3), "uri": "yt:track:v3", "id": "v3"},
        ]
        self.player._start_queue([yt_seed], index=0)

        # Disabled: next() at end stops playback
        self.player.next()
        self.assertFalse(self.player.state["isPlaying"])

        # Enable autoplay: prefetch or next() pulls radio tracks
        self.player.setAutoplay(True)
        self.assertTrue(self.settings["autoplay"])
        with patch("senada.player.ytmusic.up_next", return_value=radio_hits) as mock_up_next:
            self.player._start_queue([yt_seed], index=0)
            self.player.next()
        mock_up_next.assert_called_with("v1")
        self.assertEqual(self.player.state["uri"], "yt:track:v2")
        self.assertEqual([t["uri"] for t in self.player.queue], ["yt:track:v3"])


class SessionResumeTests(unittest.TestCase):
    def test_save_and_restore_playback_state_seeks_when_playing(self):
        matches = {f"spotify:track:{n}": {"v": f"v{n}", "s": 100} for n in (1, 2, 3)}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "playback.json"
            engine1 = IdleEngine()
            engine1.seek = lambda _ms: None
            p1 = Player(SyncWorker(), engine1, FakeResolver(matches), {}, FakeStore(), None)
            p1.streams = FakeStreams({"v1": "https://audio/1", "v2": "https://audio/2", "v3": "https://audio/3"})
            p1._start_queue([song(1), song(2), song(3)], index=1, context_uri="yt:album:a1")
            p1.setVolume(65)
            p1.seek(42000)
            p1.save_playback_state(path)

            engine2 = IdleEngine()
            engine2.seeks = []
            engine2.seek = lambda ms: engine2.seeks.append(ms)
            p2 = Player(SyncWorker(), engine2, FakeResolver(matches), {}, FakeStore(), None)
            p2.streams = FakeStreams({"v1": "https://audio/1", "v2": "https://audio/2", "v3": "https://audio/3"})

            self.assertTrue(p2.restore_playback_state(path))
            self.assertTrue(p2.state["hasTrack"])
            self.assertFalse(p2.state["isPlaying"])
            self.assertEqual(p2.state["uri"], "spotify:track:2")
            self.assertEqual(p2.state["volume"], 65)
            self.assertEqual(p2.position, 42000)
            self.assertEqual([t["uri"] for t in p2.queue], ["spotify:track:3"])
            self.assertEqual(engine2.played, [])

            # Seeking while still paused/restored updates position before engine starts
            p2.seek(51000)
            self.assertEqual(p2.position, 51000)
            self.assertEqual(engine2.seeks, [])

            # Resuming starts track and seeks to saved position once engine transitions to playing
            p2.togglePlay()
            self.assertEqual(engine2.played[-1], "https://audio/2")
            engine2.stateChanged.emit(True)
            self.assertEqual(engine2.seeks[-1], 51000)

    def test_restore_handles_missing_or_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "playback.json"
            p = Player(SyncWorker(), IdleEngine(), FakeResolver({}), {}, FakeStore(), None)
            self.assertFalse(p.restore_playback_state(path))
            path.write_text("{broken json", encoding="utf-8")
            self.assertFalse(p.restore_playback_state(path))


if __name__ == "__main__":
    unittest.main()
