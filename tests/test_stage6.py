"""Stage 6 tests: extended listening stats (topAlbums, byHour, streaks, recentPlays)."""

import datetime
import tempfile
import unittest
from pathlib import Path

from senada import stats


def make_track(uri, name, artist="Artist A", album="Album X", duration=200_000):
    return {
        "uri": uri,
        "name": name,
        "artists": artist,
        "album": album,
        "imageSmall": f"http://img/{uri}",
        "durationMs": duration,
    }


def local_ts(year, month, day, hour, minute=0) -> float:
    return datetime.datetime(year, month, day, hour, minute).timestamp()


class PlayLogStage6Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = stats.PlayLog(self.tmp / "plays.db")

    def tearDown(self):
        self.log.close()

    def test_top_albums_by_hour_and_recent_plays(self):
        now = datetime.datetime.now()
        base_day = (now - datetime.timedelta(days=1)).date()
        t_9 = datetime.datetime.combine(base_day, datetime.time(9, 15)).timestamp()
        t_21a = datetime.datetime.combine(base_day, datetime.time(21, 5)).timestamp()
        t_21b = datetime.datetime.combine(base_day, datetime.time(21, 35)).timestamp()

        self.log.add(make_track("yt:track:1", "Track 1", "Band A", "Album Alpha"), 120_000, t_9)
        self.log.add(make_track("yt:track:2", "Track 2", "Band A", "Album Alpha"), 180_000, t_21a)
        self.log.add(make_track("yt:track:3", "Track 3", "Band B", "Album Beta"), 240_000, t_21b)
        self.log.add(make_track("yt:track:4", "No Album Track", "Band C", ""), 60_000, t_21b + 10)

        s = self.log.summary(stats.period_start("week", now), "day")
        self.assertEqual([a["name"] for a in s["topAlbums"]], ["Album Alpha", "Album Beta"])
        self.assertEqual(s["topAlbums"][0]["plays"], 2)
        self.assertEqual(s["topAlbums"][0]["minutes"], 5)

        by_hour = s["byHour"]
        self.assertEqual(len(by_hour), 24)
        self.assertEqual(by_hour[9]["plays"], 1)
        self.assertEqual(by_hour[9]["minutes"], 2)
        self.assertEqual(by_hour[21]["plays"], 3)
        self.assertEqual(by_hour[21]["minutes"], 8)  # 180k + 240k + 60k = 480k ms = 8 min
        self.assertEqual(by_hour[0]["plays"], 0)

        self.assertEqual([r["uri"] for r in s["recentPlays"]], ["yt:track:4", "yt:track:3", "yt:track:2", "yt:track:1"])

    def test_streaks_current_and_longest(self):
        self.assertEqual(self.log.streaks(datetime.date(2026, 11, 16)), (0, 0))

        # Historic 4-day streak: Nov 1..4
        for day in (1, 2, 3, 4):
            self.log.add(make_track(f"yt:track:{day}", f"S{day}"), 60_000, local_ts(2026, 11, day, 12))
        # Current 2-day streak ending Nov 15 (yesterday relative to Nov 16)
        for day in (14, 15):
            self.log.add(make_track(f"yt:track:{day}", f"S{day}"), 60_000, local_ts(2026, 11, day, 20))

        # On Nov 16 before first play today: current=2, longest=4
        self.assertEqual(self.log.streaks(datetime.date(2026, 11, 16)), (2, 4))
        # If checked on Nov 17 without playing on Nov 16 or 17 -> current streak broken -> 0, longest=4
        self.assertEqual(self.log.streaks(datetime.date(2026, 11, 17)), (0, 4))

        # Adding a play on Nov 16 extends current streak to 3
        self.log.add(make_track("yt:track:16", "Today"), 60_000, local_ts(2026, 11, 16, 8))
        self.assertEqual(self.log.streaks(datetime.date(2026, 11, 16)), (3, 4))


class StatsControllerStage6Tests(unittest.TestCase):
    def test_summary_defaults_without_log_and_with_log(self):
        class FakeTracker:
            def __init__(self):
                self.finished = _Signal()

        class _Signal:
            def connect(self, _fn):
                pass

        tmp = Path(tempfile.mkdtemp())
        empty_log = stats.PlayLog(tmp / "empty.db")
        try:
            empty_stats = stats.Stats(FakeTracker(), player=None, log=empty_log)
            for src in (empty_stats.summary("month"), (setattr(empty_stats, "log", None) or empty_stats).summary("month")):
                self.assertEqual(src["topAlbums"], [])
                self.assertEqual(len(src["byHour"]), 24)
                self.assertEqual(src["recentPlays"], [])
                self.assertEqual(src["streakDays"], 0)
                self.assertEqual(src["longestStreak"], 0)
        finally:
            empty_log.close()

        log = stats.PlayLog(tmp / "plays.db")
        try:
            now = datetime.datetime.now()
            log.add(make_track("yt:track:now", "Now Song", "Solo", "Debut"), 90_000, now.timestamp())
            st = stats.Stats(FakeTracker(), player=None, log=log)
            res = st.summary("week")
            self.assertEqual(res["topAlbums"][0]["name"], "Debut")
            self.assertEqual(res["streakDays"], 1)
            self.assertEqual(res["longestStreak"], 1)
            self.assertEqual(res["recentPlays"][0]["uri"], "yt:track:now")
        finally:
            log.close()
