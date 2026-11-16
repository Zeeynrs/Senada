"""What was listened to, and for how long: the one place that watches songs come and go.

The listening statistics (stats.py) and scrobbling (scrobble.py) both build on it. Time counts
only while a song plays and moves on by itself: a seek or a jump is not listening.
"""

import datetime
import time

from PySide6.QtCore import QObject, Signal

TRACK_KEYS = ("uri", "name", "artists", "album", "durationMs", "imageSmall", "image")
MAX_STEP_MS = 3000  # a bigger jump in position is a seek, not listening


class PlayTracker(QObject):
    started = Signal("QVariantMap")                # a song began playing (now playing)
    finished = Signal("QVariantMap", int, float)   # the song, ms listened, when it began (epoch seconds)
    listeningProgress = Signal("QVariantMap", int, float)  # actual listening to this song today, current time

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self._track = None
        self._listened = 0
        self._started_at = 0.0
        self._last_pos = None
        self._listening_day = None
        self._day_listened = 0
        player.trackChanged.connect(self._on_track)
        player.positionChanged.connect(self._on_position)

    def _on_track(self):
        self.flush()
        s = self.player.state
        if not (s.get("hasTrack") and s.get("uri")):
            return
        self._track = {k: s.get(k) for k in TRACK_KEYS}
        self._started_at = time.time()
        self._listening_day = datetime.date.fromtimestamp(self._started_at)
        self._day_listened = 0
        self._listened = 0
        self._last_pos = self.player.position
        self.started.emit(dict(self._track))

    def _on_position(self):
        pos = self.player.position
        s = self.player.state
        if self._track is not None and not self._track.get("durationMs") and s.get("uri") == self._track["uri"]:
            self._track["durationMs"] = s.get("durationMs") or 0  # mpv tells the length once it plays
        if self._track is not None and s.get("isPlaying") and self._last_pos is not None:
            step = pos - self._last_pos
            if 0 < step <= MAX_STEP_MS:
                self._listened += step
                now = time.time()
                day = datetime.date.fromtimestamp(now)
                day_step = step
                if day != self._listening_day:
                    midnight = datetime.datetime.combine(day, datetime.time()).timestamp()
                    day_step = min(step, max(0, int((now - midnight) * 1000)))
                    previous_step = step - day_step
                    if previous_step > 0 and self._listening_day == day - datetime.timedelta(days=1):
                        self._day_listened += previous_step
                        self.listeningProgress.emit(dict(self._track), int(self._day_listened), midnight - 0.001)
                    self._listening_day = day
                    self._day_listened = 0
                    # Only the part of a position update after local midnight
                    # belongs to the new day's listening.
                self._day_listened += day_step
                self.listeningProgress.emit(dict(self._track), int(self._day_listened), now)
        self._last_pos = pos

    def flush(self):
        """The song is over (another began, or Senada is quitting): report how much was heard."""
        if self._track is not None and self._listened > 0:
            self.finished.emit(dict(self._track), int(self._listened), self._started_at)
        self._track = None
        self._listened = 0
