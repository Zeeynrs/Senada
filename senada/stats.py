"""Listening statistics ("Your stats"): what you played, how often and for how long.

Every song heard for at least 30 seconds (or half of a shorter one) is written to a small
SQLite file next to the library (plays.db), on this device only. The Stats page asks for a
period (the last 7 or 30 days, this year, or all time) and gets the totals, the top songs and
artists, and the minutes per day or per month for the bars.
"""

import datetime
import logging
import sqlite3
import threading
import time

from PySide6.QtCore import Property, QObject, Signal, Slot

from .config import CONFIG_DIR

logger = logging.getLogger("senada.stats")

PLAYS_FILE = CONFIG_DIR / "plays.db"
MIN_LISTEN_MS = 30_000
PERIODS = ("week", "month", "year", "all")


def counts_as_play(listened_ms: int, duration_ms: int) -> bool:
    return listened_ms >= MIN_LISTEN_MS or (duration_ms > 0 and listened_ms >= duration_ms / 2)


def primary_artist(artists: str) -> str:
    return (artists or "").split(",")[0].strip()


def period_start(period: str, now: datetime.datetime | None = None) -> float:
    now = now or datetime.datetime.now()
    if period == "week":
        start = now - datetime.timedelta(days=7)
    elif period == "month":
        start = now - datetime.timedelta(days=30)
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return 0.0
    return start.timestamp()


class PlayLog:
    """The plays, in SQLite. Safe to use from any thread."""

    def __init__(self, path=PLAYS_FILE):
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("""CREATE TABLE IF NOT EXISTS plays (
            at REAL NOT NULL, uri TEXT NOT NULL, name TEXT, artists TEXT, artist TEXT, album TEXT,
            image TEXT, listened_ms INTEGER NOT NULL, duration_ms INTEGER)""")
        self._db.execute("CREATE INDEX IF NOT EXISTS plays_at ON plays(at)")
        self._db.commit()

    def add(self, track: dict, listened_ms: int, at: float):
        with self._lock:
            self._db.execute("INSERT INTO plays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                at, track.get("uri", ""), track.get("name", ""), track.get("artists", ""),
                primary_artist(track.get("artists", "")), track.get("album", ""),
                track.get("imageSmall") or track.get("image") or "", int(listened_ms),
                int(track.get("durationMs") or 0)))
            self._db.commit()

    def _rows(self, sql, args=()):
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    def summary(self, since: float, buckets: str) -> dict:
        """Totals, top songs/artists/albums, recent plays, hourly and day/month breakdowns since `since`."""
        total = self._rows("SELECT COUNT(*), COALESCE(SUM(listened_ms), 0), COUNT(DISTINCT uri), "
                           "COUNT(DISTINCT artist) FROM plays WHERE at >= ?", (since,))[0]
        songs = self._rows("""SELECT uri, name, artists, album, image, COUNT(*) AS n, SUM(listened_ms)
            FROM plays WHERE at >= ? GROUP BY uri ORDER BY n DESC, SUM(listened_ms) DESC LIMIT 10""", (since,))
        artists = self._rows("""SELECT artist, COUNT(*) AS n, SUM(listened_ms), MAX(image)
            FROM plays WHERE at >= ? AND artist != '' GROUP BY artist
            ORDER BY n DESC, SUM(listened_ms) DESC LIMIT 10""", (since,))
        albums = self._rows("""SELECT album, MAX(artists), COUNT(*) AS n, SUM(listened_ms), MAX(image)
            FROM plays WHERE at >= ? AND album != '' GROUP BY album, artist
            ORDER BY n DESC, SUM(listened_ms) DESC LIMIT 10""", (since,))
        hour_rows = self._rows("""SELECT CAST(strftime('%H', at, 'unixepoch', 'localtime') AS INTEGER) AS hr,
            COUNT(*) AS n, SUM(listened_ms) FROM plays WHERE at >= ? GROUP BY hr ORDER BY hr""", (since,))
        recent = self._rows("""SELECT at, uri, name, artists, album, image, listened_ms
            FROM plays WHERE at >= ? ORDER BY at DESC LIMIT 15""", (since,))
        fmt = "%Y-%m" if buckets == "month" else "%Y-%m-%d"
        per = self._rows(f"""SELECT strftime('{fmt}', at, 'unixepoch', 'localtime') AS b, SUM(listened_ms)
            FROM plays WHERE at >= ? GROUP BY b ORDER BY b""", (since,))
        hour_map = {int(r[0]): (int(r[1]), round(r[2] / 60000)) for r in hour_rows if r[0] is not None}
        by_hour = [{"hour": h, "plays": hour_map.get(h, (0, 0))[0], "minutes": hour_map.get(h, (0, 0))[1]}
                   for h in range(24)]
        return {
            "plays": total[0], "minutes": round(total[1] / 60000), "songs": total[2], "artists": total[3],
            "topSongs": [{"uri": r[0], "name": r[1], "artists": r[2], "album": r[3], "imageSmall": r[4],
                          "image": r[4], "plays": r[5], "minutes": round(r[6] / 60000)} for r in songs],
            "topArtists": [{"name": r[0], "plays": r[1], "minutes": round(r[2] / 60000), "imageSmall": r[3]}
                           for r in artists],
            "topAlbums": [{"name": r[0], "artists": r[1], "plays": r[2], "minutes": round(r[3] / 60000),
                           "imageSmall": r[4]} for r in albums],
            "byHour": by_hour,
            "recentPlays": [{"at": float(r[0]), "uri": r[1], "name": r[2], "artists": r[3], "album": r[4],
                             "imageSmall": r[5], "image": r[5], "minutes": round(r[6] / 60000)}
                            for r in recent],
            "per": {r[0]: round(r[1] / 60000) for r in per},
        }

    def streaks(self, today: datetime.date | None = None) -> tuple[int, int]:
        """Return (current_streak_days, longest_streak_days) across all recorded local play dates."""
        rows = self._rows("""SELECT DISTINCT strftime('%Y-%m-%d', at, 'unixepoch', 'localtime') AS d
            FROM plays ORDER BY d""")
        dates = []
        for (raw,) in rows:
            if not raw:
                continue
            try:
                dates.append(datetime.date.fromisoformat(raw))
            except ValueError:
                continue
        if not dates:
            return 0, 0
        longest = run = 1
        for i in range(1, len(dates)):
            if dates[i] == dates[i - 1] + datetime.timedelta(days=1):
                run += 1
                longest = max(longest, run)
            else:
                run = 1
        today = today or datetime.date.today()
        date_set = set(dates)
        cursor = today if today in date_set else (today - datetime.timedelta(days=1))
        current = 0
        while cursor in date_set:
            current += 1
            cursor -= datetime.timedelta(days=1)
        return current, longest

    def first_play(self) -> float:
        row = self._rows("SELECT MIN(at) FROM plays")[0]
        return row[0] or 0.0

    def close(self):
        with self._lock:
            self._db.close()


def bars(per: dict, period: str, now: datetime.datetime | None = None, first: float = 0.0) -> list[dict]:
    """Every day (week, month) or month (year, all time) of the period, with its minutes."""
    now = now or datetime.datetime.now()
    out = []
    if period in ("week", "month"):
        days = 7 if period == "week" else 30
        for i in range(days - 1, -1, -1):
            d = (now - datetime.timedelta(days=i)).date()
            out.append({"key": d.isoformat(), "label": str(d.day), "minutes": per.get(d.isoformat(), 0)})
        return out
    if period == "year":
        start = now.replace(month=1, day=1)
    else:
        begin = datetime.datetime.fromtimestamp(first) if first else now
        start = begin.replace(day=1)
        # at least the last 12 months, so a new log still shows a year
        twelve_back = (now.replace(day=1) - datetime.timedelta(days=330)).replace(day=1)
        start = min(start, twelve_back)
    y, m = start.year, start.month
    while (y, m) <= (now.year, now.month):
        key = f"{y:04d}-{m:02d}"
        out.append({"key": key, "label": str(m), "minutes": per.get(key, 0)})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


class Stats(QObject):
    """The Stats page's data; records the plays the PlayTracker reports."""
    changed = Signal()

    def __init__(self, tracker, player=None, log: PlayLog | None = None, parent=None):
        super().__init__(parent)
        self.player = player
        try:
            self.log = log or PlayLog()
        except sqlite3.Error as e:  # the statistics are a nice-to-have: never stop Senada for them
            logger.warning("listening statistics are off: %s", e)
            self.log = None
        tracker.finished.connect(self._on_finished)

    def _on_finished(self, track, listened_ms, at):
        if self.log is None or not counts_as_play(listened_ms, int(track.get("durationMs") or 0)):
            return
        try:
            self.log.add(track, listened_ms, at)
        except sqlite3.Error as e:
            logger.warning("a play was not recorded: %s", e)
            return
        self.changed.emit()

    @Property(bool, constant=True)
    def available(self):
        return self.log is not None

    @Slot(str, result="QVariantMap")
    def summary(self, period):
        """{plays, minutes, songs, artists, topSongs, topArtists, topAlbums, byHour, recentPlays, streakDays, longestStreak, bars, since}."""
        if self.log is None:
            return {
                "plays": 0, "minutes": 0, "songs": 0, "artists": 0,
                "topSongs": [], "topArtists": [], "topAlbums": [],
                "byHour": [{"hour": h, "plays": 0, "minutes": 0} for h in range(24)],
                "recentPlays": [], "streakDays": 0, "longestStreak": 0, "bars": [], "since": "",
            }
        period = period if period in PERIODS else "month"
        data = self.log.summary(period_start(period), "month" if period in ("year", "all") else "day")
        first = self.log.first_play()
        data["bars"] = bars(data.pop("per"), period, first=first)
        cur_streak, best_streak = self.log.streaks()
        data["streakDays"] = cur_streak
        data["longestStreak"] = best_streak
        data["since"] = (datetime.date.fromtimestamp(first).isoformat() if first else "")
        return data

    @Slot("QVariantList", int)
    def play(self, tracks, index):
        """Play the top songs from this one on."""
        if self.player is None or not tracks:
            return
        tracks = [dict(t) for t in tracks]
        self.player.cache_tracks(tracks)
        self.player.playUris([t["uri"] for t in tracks], index)

    def close(self):
        if self.log is not None:
            self.log.close()

