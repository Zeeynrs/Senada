"""Playback state and controls using local AudioEngine and AudioResolver."""

import colorsys
import json
import logging
import random
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from . import net, ytmusic
from .config import IS_WINDOWS, PLAYBACK_FILE, read_json, write_private
from .i18n import tr
from .lru import BoundedCache
from .engine import AudioEngine
from .resolver import AudioResolver
from .sleep import SleepTimer
from .streams import StreamError, StreamResolver, is_blocked, watch_url

logger = logging.getLogger("senada.player")

DEFAULT_ACCENT = "#d9d9d9"  # neutral until the album art gives a colour
BACKGROUND_POSITION_MS = 250  # position updates while Senada is not in view (4 per second)
MAX_FAIL_STREAK = 3  # songs in a row that would not play before playback stops instead of skipping on
WINDOWS_AUDIO_IDLE_SECONDS = 300
TRACK_CACHE_LIMIT = 2000  # tracks remembered from the pages shown (about a few MB)


def download(url: str) -> bytes:
    with net.urlopen(url, timeout=10) as resp:
        return resp.read()


def accent_from_image(data: bytes) -> str:
    """Pick a lively, readable-on-dark colour from album art.
    Runs on the UI thread: PySide6 types are not safe to first-use from worker threads.
    """
    img = QImage.fromData(data)
    if img.isNull():
        return DEFAULT_ACCENT
    img = img.scaled(24, 24)
    bins = [[0.0, 0.0, 0.0, 0.0] for _ in range(12)]  # weight, r, g, b
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            r, g, b = c.redF(), c.greenF(), c.blueF()
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            w = s * s * v + 0.002
            slot = bins[int(h * 12) % 12]
            slot[0] += w
            slot[1] += r * w
            slot[2] += g * w
            slot[3] += b * w
    w, r, g, b = max(bins, key=lambda b: b[0])
    h, s, v = colorsys.rgb_to_hsv(r / w, g / w, b / w)
    s = min(max(s, 0.35), 0.75) if s > 0.08 else s
    v = max(v, 0.82)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


class Player(QObject):
    stateChanged = Signal()
    positionChanged = Signal()
    devicesChanged = Signal()
    queueChanged = Signal()
    accentChanged = Signal()
    trackChanged = Signal()
    likedChanged = Signal(str, bool)
    historyChanged = Signal()
    trackMatched = Signal(str, "QVariantMap")  # uri, {imageSmall, image, imageLarge, matchScore}
    autoplayChanged = Signal()

    def __init__(self, worker, engine: AudioEngine, resolver: AudioResolver, settings, store, catalog,
                 downloads=None, parent=None):
        super().__init__(parent)
        self.downloads = downloads  # songs saved for offline: played from the file, no internet needed
        self.store = store
        self.catalog = catalog
        self.worker = worker
        self.engine = engine
        self.resolver = resolver
        self.settings = settings
        self.streams = StreamResolver(quality=self._setting("audio_quality", "best"))
        self._audio_device = str(self._setting("audio_device", "auto") or "auto")

        self._state = {
            "hasTrack": False,
            "isPlaying": False,
            "shuffle": False,
            "repeat": "off",  # 'off', 'context', 'track'
            "volume": 80,
            "supportsVolume": True,
            "deviceId": self._audio_device,
            "deviceName": "Senada (Lokal)",
            "deviceType": "computer",
            "contextUri": "",
            "liked": False,
            "durationMs": 0,
        }
        self._accent = DEFAULT_ACCENT
        self._position = 0
        self._last_audio_activity = time.time()
        self._woke_from_sleep = False
        self._queue = []
        self._queue_index = -1
        self._unshuffled = None  # original upcoming order kept while shuffle is on
        # uri -> track dict, for what the pages showed: only the most recent ones are kept
        self._track_cache = BoundedCache(TRACK_CACHE_LIMIT)
        self._play_token = 0  # bumps on every track change; stale stream lookups are dropped
        self._prefetched = ""  # uri already being resolved ahead of time
        self._started = (0, "")  # (play token, video id) of the file last handed to the engine
        self._fallback_token = -1  # play token whose direct stream failed: mpv's yt-dlp hook plays it
        self._recovering = -1  # play token for which another upload is being (or was) tried
        self._fail_streak = 0  # songs in a row that could not be played
        self._resume_next = False  # stopped by the sleep timer at a song's end: play resumes with the next one
        self._autoplay_token = -1  # play token for which radio continuation was already fetched
        self._autoplay_advance_token = -1  # play token waiting on autoplay tracks to advance immediately
        self._restored_pending = False  # restored from previous session: play starts the track at saved position
        self._seek_on_start = None  # (play_token, position_ms) applied once playback begins
        self._sleep = SleepTimer(engine, lambda: self._state.get("volume", 80),
                                 lambda: bool(self._state.get("isPlaying")), self)
        self._sleep.changed.connect(self._prefetch_next)  # "after this song" takes the queued song back out
        self._devices = [{
            "id": "local",
            "name": "Senada (Lokal)",
            "type": "computer",
            "active": True,
            "volume": 80,
            "local": True,
            "restricted": False,
        }]

        # Connect audio engine signals
        self.engine.positionChanged.connect(self._on_engine_pos)
        self.engine.durationChanged.connect(self._on_engine_duration)
        self.engine.stateChanged.connect(self._on_engine_state)
        self.engine.trackEnded.connect(self._on_track_ended)
        self.engine.loadFailed.connect(self._on_load_failed)
        self.engine.errorOccurred.connect(lambda msg: self.worker.error.emit(msg))
        if hasattr(self.engine, "audioDevicesChanged"):
            self.engine.audioDevicesChanged.connect(self._on_audio_devices)
        if hasattr(self.engine, "audioDeviceChanged"):
            self.engine.audioDeviceChanged.connect(self._on_audio_device)

        # Apply saved volume, device, and quality settings
        self.engine.set_volume(80)
        if hasattr(self.engine, "set_audio_device") and self._audio_device != "auto":
            self.engine.set_audio_device(self._audio_device)
        if hasattr(self.engine, "set_quality"):
            self.engine.set_quality(self._setting("audio_quality", "best"))

    # ---- properties for QML ---------------------------------------------

    @Property("QVariantMap", notify=stateChanged)
    def state(self):
        return self._state

    @Property(int, notify=positionChanged)
    def position(self):
        return self._position

    @Property("QVariantList", notify=devicesChanged)
    def devices(self):
        return self._devices

    @Property("QVariantList", notify=queueChanged)
    def queue(self):
        # Expose queue tracks after current index
        if self._queue_index >= 0 and self._queue_index + 1 < len(self._queue):
            return self._queue[self._queue_index + 1:]
        return []

    @Property(str, notify=accentChanged)
    def accent(self):
        return self._accent

    @Property(QObject, constant=True)
    def sleep(self):
        return self._sleep

    def _setting(self, key: str, default=None):
        try:
            return self.settings[key]
        except (KeyError, TypeError):
            return default

    @Property(bool, notify=autoplayChanged)
    def autoplay(self):
        return bool(self._setting("autoplay", False))

    @autoplay.setter
    def autoplay(self, on):
        self.setAutoplay(on)

    @Slot(bool)
    def setAutoplay(self, on):
        on = bool(on)
        if on == self.autoplay:
            return
        if isinstance(self.settings, dict) or hasattr(self.settings, "__setitem__"):
            self.settings["autoplay"] = on
        self.autoplayChanged.emit()
        self._prefetch_next()

    # ---- playback engine callbacks --------------------------------------

    def _on_engine_pos(self, pos_ms: int):
        if IS_WINDOWS and self._state.get("isPlaying") and pos_ms != self._position:
            self._last_audio_activity = time.time()
        self._position = pos_ms
        self.positionChanged.emit()
        self._prefetch_next()  # cheap once the next track is ready

    def _on_engine_duration(self, dur_ms: int):
        if dur_ms > 0 and abs(dur_ms - self._state.get("durationMs", 0)) > 2000:
            self._state["durationMs"] = dur_ms
            self.stateChanged.emit()

    def _on_engine_state(self, is_playing: bool):
        if is_playing:
            self._fail_streak = 0
            if self._seek_on_start and self._seek_on_start[0] == self._play_token:
                _, pos = self._seek_on_start
                self._seek_on_start = None
                if pos > 0:
                    self._position = pos
                    self.positionChanged.emit()
                    self.engine.seek(pos)
        if self._state.get("isPlaying") != is_playing:
            self._state["isPlaying"] = is_playing
            self.stateChanged.emit()

    def _on_track_ended(self):
        if self._sleep.stops_after_track:  # nothing was queued: mpv stopped at the song's end
            self._sleep.track_ended()
            self._resume_next = True
            self._state["isPlaying"] = False
            self.stateChanged.emit()
            return
        if self._state.get("repeat") == "track":
            self._play_index(self._queue_index)
        else:
            self.next()

    def _on_load_failed(self):
        """The stream did not open or broke off: play the track through mpv's own yt-dlp hook instead,
        and when that fails too, another upload of the same song (or move on to the next song)."""
        token, video_id = self._started
        track = self._current_track()
        if track and track.get("uri", "").startswith("local:file:") and token == self._play_token:
            self._give_up(track, token, "unplayable")  # a music file: there is no other upload to try
            return
        if self._fallback_token == self._play_token:
            if token == self._play_token:  # the fallback failed too
                track = self._current_track()
                if self._recovering == token or not track:
                    self._give_up(track or self._state, token, "unplayable")
                else:
                    self._recover(track, token, video_id)
            return
        self._fallback_token = self._play_token
        if token == self._play_token and video_id:  # else the pending lookup starts it as a fallback
            self.streams.forget(video_id)
            self.engine.play(watch_url(video_id))

    def _next_track(self) -> dict | None:
        """The track that plays by itself when the current one ends."""
        if not 0 <= self._queue_index < len(self._queue) or self._sleep.stops_after_track:
            return None
        if self._state.get("repeat") == "track":
            return self._queue[self._queue_index]
        nxt_idx = self._queue_index + 1
        if nxt_idx >= len(self._queue):
            if self._state.get("repeat") != "context":
                return None
            nxt_idx = 0
        return self._queue[nxt_idx]

    def _resolve(self, track: dict) -> tuple[dict | None, str, str]:
        """(match, stream address, problem) for a track; blocking. The address is "" when yt-dlp
        could not get it, and the problem then says why."""
        info = self.resolver.match(track)
        url, problem = "", ""
        if info and info.get("v"):
            try:
                url = self.streams.resolve(info["v"])
            except StreamError as e:
                problem = str(e)
                logger.info("no direct stream for %s: %s", info["v"], e)
        return info, url, problem

    def _local_file(self, uri: str) -> str | None:
        """A file on this computer for the song: from the music folders, or a download."""
        if uri and uri.startswith("local:file:"):
            files = getattr(self, "localfiles", None)
            return files.path_for(uri) if files is not None else None
        return self.downloads.path_for(uri) if self.downloads is not None and uri else None

    def _current_track(self) -> dict | None:
        if 0 <= self._queue_index < len(self._queue):
            return self._queue[self._queue_index]
        return None

    def _recover(self, track: dict, token: int, failed_id: str):
        """The match would not play: look for another upload of the same song that does."""
        self._recovering = token
        self.worker.error.emit(tr("“{name}” would not play — trying another version…", name=track.get("name", "")))

        def find():
            return self.resolver.alternative(track, {failed_id} if failed_id else set(), self.streams.resolve)

        def done(found):
            if token != self._play_token:
                return
            if not found:
                self._give_up(track, token, "unplayable")
                return
            info, url = found
            self._apply_match(track, info)
            self._started = (token, info["v"])
            self._fallback_token = token  # a failure from here on ends in _give_up
            self.engine.play(url)

        def failed(e):
            self._give_up(track, token, "blocked" if is_blocked(e) else "unplayable")

        self.worker.run(find, done, failed)

    def _give_up(self, track: dict, token: int, reason: str):
        """This song cannot be played: say why, and go on with the next one unless that is pointless."""
        if token != self._play_token:
            return
        self._fail_streak += 1
        name = (track or {}).get("name", "")
        if reason == "blocked":
            # every song fails the same way for a while; skipping on would only make it last longer
            message = tr("YouTube is limiting requests from this network for now, so “{name}” can't play. "
                         "Wait a few minutes and try again.", name=name)
        elif self._fail_streak >= MAX_FAIL_STREAK:
            message = tr("Several songs in a row could not be found or played. Check the internet connection and try again.")
        else:
            self.worker.error.emit(
                tr("Not found on YouTube Music: {name} — try right-click → Pick another version", name=name)
                if reason == "not_found" else
                tr("“{name}” can't be played right now — skipped to the next song.", name=name))
            self.next()
            return
        self.worker.error.emit(message)
        self.engine.stop()
        if self._state.get("isPlaying"):
            self._state["isPlaying"] = False
            self.stateChanged.emit()

    def _should_autoplay(self) -> bool:
        return (self.autoplay
                and bool(self._queue)
                and 0 <= self._queue_index == len(self._queue) - 1
                and self._state.get("repeat", "off") == "off"
                and not self._sleep.stops_after_track)

    def _radio_for(self, track: dict) -> list[dict]:
        uri = (track or {}).get("uri", "")
        if uri.startswith("yt:track:"):
            return ytmusic.up_next(uri.split(":", 2)[2])
        query = f"{track.get('artists', '')} {track.get('name', '')}".strip()
        if not query:
            return []
        hits = ytmusic.search(query).get("tracks") or []
        return ytmusic.up_next(hits[0]["id"]) if hits else []

    def _fetch_autoplay(self, advance: bool = False):
        token = self._play_token
        seed = self._current_track()
        if not seed:
            if advance:
                self.stop()
            return
        if advance:
            self._autoplay_advance_token = token
        if self._autoplay_token == token:
            return
        self._autoplay_token = token
        existing_uris = {t.get("uri") for t in self._queue if t.get("uri")}
        existing_keys = {(t.get("name", "").lower(), t.get("artists", "").lower()) for t in self._queue}

        def fetch():
            try:
                tracks = self._radio_for(seed) or []
            except ytmusic.YTMusicError:
                return []
            fresh = []
            for t in tracks:
                uri = t.get("uri")
                key = (t.get("name", "").lower(), t.get("artists", "").lower())
                if uri and uri in existing_uris:
                    continue
                if key in existing_keys:
                    continue
                if uri:
                    existing_uris.add(uri)
                existing_keys.add(key)
                fresh.append(t)
            return fresh

        def on_done(fresh):
            if token != self._play_token:
                return
            should_advance = self._autoplay_advance_token == token
            self._autoplay_advance_token = -1
            if not self.autoplay and not should_advance:
                return
            if not fresh:
                if should_advance:
                    self.stop()
                return
            self.cache_tracks(fresh)
            self._queue.extend(fresh)
            if self._unshuffled is not None:
                self._unshuffled.extend(fresh)
            self.queueChanged.emit()
            if should_advance and self._queue_index + 1 < len(self._queue):
                self._play_index(self._queue_index + 1)
            else:
                self._prefetch_next()

        def on_fail(_e):
            if token == self._play_token and self._autoplay_advance_token == token:
                self._autoplay_advance_token = -1
                self.stop()

        self.worker.run(fetch, on_done, on_fail)

    def _prefetch_next(self):
        """Look the next track up ahead of time and hand it to the engine for a gapless change.
        Called on every position update, so it must stay cheap when there is nothing to do."""
        track = self._next_track()
        if track is None and self._should_autoplay():
            if self._autoplay_token != self._play_token and self._started[0] == self._play_token:
                self._fetch_autoplay(advance=False)
            self.engine.queue_next("")
            return
        uri = (track or {}).get("uri", "")
        if not uri or self._started[0] != self._play_token:  # nothing next, or a track change is under way
            self.engine.queue_next("")
            return
        local = self._local_file(uri)
        if local:
            self.engine.queue_next(local)
            return
        video_id = (self.resolver.cached(uri) or {}).get("v") or (uri.split(":", 2)[2] if uri.startswith("yt:track:") else "")
        url = self.streams.cached(video_id) if video_id else None
        if url:
            self.engine.queue_next(url)
        elif uri != self._prefetched:  # only one lookup per track
            self._prefetched = uri
            self.engine.queue_next("")
            self.worker.run(lambda: self._resolve(track),
                            lambda found: self._apply_match(track, found[0]),
                            lambda e: None)

    # ---- controls -------------------------------------------------------

    def start(self):
        self.refreshDevices()

    def on_system_resume(self):
        # Playback can be paused intentionally. Defer the reset until playback is requested.
        self._woke_from_sleep = True

    def _needs_audio_reset(self):
        # Wall time counts sleep as well as time spent paused or idle.
        return IS_WINDOWS and (self._woke_from_sleep
                               or time.time() - self._last_audio_activity >= WINDOWS_AUDIO_IDLE_SECONDS)

    def stop(self):
        self.engine.stop()
        self._state["isPlaying"] = False
        self.stateChanged.emit()

    @Slot(bool)
    def setFastPolling(self, fast):
        """Every position update while Senada is in view, a few per second otherwise."""
        step = getattr(self.engine, "set_position_step", None)
        if step:
            step(0 if fast else BACKGROUND_POSITION_MS)

    @Slot()
    def refresh(self):
        pass

    @Slot()
    def togglePlay(self):
        if not self._state.get("hasTrack"):
            if self._queue:
                self._play_index(max(0, self._queue_index))
            return
        if self._restored_pending and self._queue:
            resume_pos = self._position
            self._restored_pending = False
            idx = max(0, min(self._queue_index, len(self._queue) - 1))
            self._play_index(idx, start_position_ms=resume_pos)
            return
        if self._queue and not self._state.get("isPlaying"):
            if self.engine.idle is True:
                # At the end of the queue or after the sleep timer, there is no file to unpause.
                index = self._queue_index + 1 if self._resume_next else self._queue_index
                self._play_index(index if 0 <= index < len(self._queue) else max(0, self._queue_index))
                return
            if self._needs_audio_reset():
                self._play_index(self._queue_index, start_position_ms=self._position, resume_current=True)
                return
        self.engine.toggle()

    @Slot()
    def next(self):
        if not self._queue:
            return
        if self._queue_index + 1 < len(self._queue):
            self._play_index(self._queue_index + 1)
        elif self._state.get("repeat") == "context":
            self._play_index(0)
        elif self.autoplay:
            self._fetch_autoplay(advance=True)
        else:
            self.engine.stop()
            self._state["isPlaying"] = False
            self.stateChanged.emit()

    @Slot(int)
    def skip(self, count):
        target = self._queue_index + max(1, count)
        if target < len(self._queue):
            self._play_index(target)

    @Slot()
    def previous(self):
        if self._position > 4000:
            self.seek(0)
        elif self._queue_index > 0:
            self._play_index(self._queue_index - 1)
        else:
            self.seek(0)

    @Slot(int)
    def seek(self, ms):
        self._position = max(0, int(ms))
        self.positionChanged.emit()
        if not self._restored_pending:
            self.engine.seek(self._position)

    @Slot(int)
    def setVolume(self, pct):
        pct = max(0, min(100, int(pct)))
        self._state["volume"] = pct
        self._devices[0]["volume"] = pct
        self.engine.set_volume(pct)
        self.stateChanged.emit()

    @Slot()
    def toggleShuffle(self):
        new_val = not self._state.get("shuffle")
        self._state["shuffle"] = new_val
        self.stateChanged.emit()

        if new_val and self._queue:
            self._unshuffled = list(self._queue)
            current = self._queue[self._queue_index] if 0 <= self._queue_index < len(self._queue) else None
            remaining = [t for i, t in enumerate(self._queue) if i != self._queue_index]
            random.shuffle(remaining)
            self._queue = ([current] if current else []) + remaining
            self._queue_index = 0 if current else -1
            self.queueChanged.emit()
            self._prefetch_next()
        elif not new_val and self._unshuffled:
            current = self._current_track()
            restored = list(self._unshuffled)
            self._unshuffled = None
            if current is not None:
                cur_idx = next((i for i, t in enumerate(restored) if t is current), -1)
                if cur_idx < 0:
                    cur_uri = current.get("uri")
                    cur_idx = next((i for i, t in enumerate(restored) if cur_uri and t.get("uri") == cur_uri), 0)
                self._queue = restored
                self._queue_index = cur_idx
            else:
                self._queue = restored
                self._queue_index = -1
            self.queueChanged.emit()
            self._prefetch_next()

    @Slot()
    def cycleRepeat(self):
        nxt = {"off": "context", "context": "track", "track": "off"}[self._state.get("repeat", "off")]
        self._state["repeat"] = nxt
        self.stateChanged.emit()
        self._prefetch_next()

    # ---- play contexts & queues -----------------------------------------

    def _play_index(self, index: int, start_position_ms: int = 0, *, resume_current: bool = False):
        if index < 0 or index >= len(self._queue):
            return
        if self._needs_audio_reset():
            logger.info("reopening Windows audio after %s", "system resume" if self._woke_from_sleep else "inactivity")
            self._woke_from_sleep = False
            self.engine.restart_output()
            if self._started[1]:
                self.streams.forget(self._started[1])
            self._prefetched = ""
        self._last_audio_activity = time.time()
        self._restored_pending = False
        self._resume_next = False
        self._autoplay_token = -1
        self._autoplay_advance_token = -1
        self._queue_index = index
        track = self._queue[index]
        self._position = max(0, int(start_position_ms))
        self._play_token += 1
        self._seek_on_start = (self._play_token, self._position) if self._position > 0 else None
        token = self._play_token
        self._state = {
            **self._state,
            **track,
            "hasTrack": True,
            "isPlaying": True,
            "liked": self.store.is_liked(track.get("uri", "")),
        }
        self.stateChanged.emit()
        self.positionChanged.emit()
        if not resume_current:
            self.trackChanged.emit()
            self.queueChanged.emit()
            self._on_track_changed(track)

        # a downloaded song plays from its file; should that fail, it is streamed after all
        # (_on_load_failed falls back to the YouTube upload it was downloaded from)
        local = self._local_file(track.get("uri", ""))
        if local:
            video_id = self.downloads.video_id_for(track["uri"]) if self.downloads is not None else ""
            self._started = (token, video_id)  # a music file of your own has none
            self.engine.play(local)
            return

        # Resolve stream URL and play (imported tracks are matched to a YouTube Music upload first)
        def on_resolved(found):
            info, url, problem = found
            if token != self._play_token:
                return  # the user already moved on to another track
            if info and info.get("v"):
                self._apply_match(track, info)
                self._started = (token, info["v"])
                if not url and is_blocked(problem):
                    self._give_up(track, token, "blocked")
                    return
                if not url and "ERROR:" in problem:
                    # YouTube said this upload cannot be played (removed, private, not in this
                    # country…): mpv's own yt-dlp lookup would hear the same, so try another upload
                    self._fallback_token = token
                    self._recover(track, token, info["v"])
                    return
                if not url or self._fallback_token == token:
                    self.streams.forget(info["v"])
                    url = watch_url(info["v"])  # slower: mpv's yt-dlp hook looks the stream up
                self.engine.play(url)
            else:
                if (track.get("uri") or "").startswith("spotify:"):
                    self.trackMatched.emit(track["uri"], {"matchScore": 0})  # shows the "pick a version" mark
                self._give_up(track, token, "not_found")

        def on_fail(e):
            if token == self._play_token:
                self.worker.error.emit(tr("Could not play audio: {error}", error=e))

        self.worker.run(lambda: self._resolve(track), on_resolved, on_fail)

    def _apply_match(self, track: dict, info: dict | None):
        """Give an imported (metadata-only) track the cover and confidence of its match."""
        uri = track.get("uri", "")
        if not info or uri.startswith("yt:track:"):
            return
        patch = {k: info.get(k) for k in ("imageSmall", "image", "imageLarge") if info.get(k)}
        patch["matchScore"] = info.get("s", 0)
        def fill(t):  # the match score always; covers only where the track has none (keep Spotify art)
            t.update({k: v for k, v in patch.items() if k == "matchScore" or not t.get(k)})
        for t in [self._track_cache.get(uri)] + [q for q in self._queue if q.get("uri") == uri]:
            if t is not None:
                fill(t)
        if self._state.get("uri") == uri:
            first_cover = not self._state.get("imageSmall") and patch.get("imageSmall")
            fill(self._state)
            self.stateChanged.emit()
            if first_cover:
                self._on_cover(patch["imageSmall"])
        self.trackMatched.emit(uri, patch)

    def replaceMatch(self, uri: str, patch: dict):
        """A different upload was picked for this track: update it and restart it if it is playing."""
        for t in [self._track_cache.get(uri)] + [q for q in self._queue if q.get("uri") == uri]:
            if t is not None:
                t.update(patch)
        if self._state.get("uri") == uri and 0 <= self._queue_index < len(self._queue):
            self._play_index(self._queue_index)

    def _on_cover(self, art: str):
        self.worker.run(lambda: download(art), lambda data: self._set_accent(accent_from_image(data)), lambda e: None)

    def _on_track_changed(self, track: dict):
        if not track.get("uri"):
            return
        self.store.add_history(track)
        self.historyChanged.emit()

        art = track.get("imageSmall")
        if art:
            self.worker.run(
                lambda: download(art),
                lambda data: self._set_accent(accent_from_image(data)),
                lambda e: None
            )

    def _set_accent(self, color):
        if color != self._accent:
            self._accent = color
            self.accentChanged.emit()

    def cache_tracks(self, tracks: list):
        self._track_cache.put_many((t["uri"], t) for t in tracks or [] if isinstance(t, dict) and t.get("uri"))

    def _known(self, uri: str) -> dict | None:
        """A track's metadata without asking the internet: a page showed it, or it is in the queue."""
        t = self._track_cache.get(uri)
        if t is None:
            t = next((q for q in self._queue if q.get("uri") == uri), None)
        return t

    def _lookup(self, uri: str) -> dict | None:
        """Track metadata for a URI: from what the pages showed, else from YouTube Music."""
        t = self._known(uri)
        if t is None and uri.startswith("yt:track:"):
            t = ytmusic.track(uri.split(":", 2)[2])
            if t:
                self._track_cache[uri] = t
        return t

    def _start_queue(self, tracks: list, index: int = 0, context_uri: str = "", original_tracks: list | None = None):
        if not tracks:
            self.worker.error.emit(tr("No songs that can be played"))
            return
        self._queue = list(tracks)
        self._unshuffled = list(original_tracks) if original_tracks is not None else None
        self._state["contextUri"] = context_uri
        self._play_index(min(max(0, index), len(self._queue) - 1))

    @Slot("QVariantList", int)
    def playUris(self, uris, index=0):
        uris = [u for u in uris if u]
        if not uris:
            return
        target = uris[index] if 0 <= index < len(uris) else uris[0]

        def fetch_tracks():
            tracks = []
            for u in uris:
                try:
                    t = self._lookup(u)
                except ytmusic.YTMusicError:
                    t = None
                if t:
                    tracks.append(t)
            return tracks

        def on_done(tracks):
            idx = next((i for i, t in enumerate(tracks) if t.get("uri") == target), 0)
            self._start_queue(tracks, idx)

        self.worker.run(fetch_tracks, on_done, lambda e: self.worker.error.emit(str(e)))

    @Slot(str, str)
    def playContext(self, context_uri, offset_uri=""):
        def fetch_context():
            tracks = self.catalog.tracks_for(context_uri)
            self.cache_tracks(tracks)
            return tracks

        def on_done(tracks):
            idx = next((i for i, t in enumerate(tracks) if offset_uri and t.get("uri") == offset_uri), 0)
            original = None
            if self._state.get("shuffle") and tracks and not offset_uri:
                original = list(tracks)
                tracks = list(tracks)
                random.shuffle(tracks)
            self._start_queue(tracks, idx, context_uri, original_tracks=original)

        self.worker.run(fetch_context, on_done, lambda e: self.worker.error.emit(str(e)))

    @Slot(str)
    def shufflePlay(self, context_uri):
        self._state["shuffle"] = True
        self.stateChanged.emit()

        def fetch_and_shuffle():
            original = list(self.catalog.tracks_for(context_uri))
            self.cache_tracks(original)
            shuffled = list(original)
            random.shuffle(shuffled)
            return original, shuffled

        self.worker.run(fetch_and_shuffle,
                        lambda pair: self._start_queue(pair[1], 0, context_uri, original_tracks=pair[0]),
                        lambda e: self.worker.error.emit(str(e)))

    @Slot(str)
    def playRadio(self, uri):
        """Play a track followed by YouTube Music's radio for it."""
        if not uri.startswith("yt:track:"):
            seed = self._known(uri)
            if not seed:
                return
            fetch = lambda: self._radio_for(seed)
        else:
            fetch = lambda: ytmusic.up_next(uri.split(":", 2)[2])

        def on_done(tracks):
            self.cache_tracks(tracks)
            self._start_queue(tracks, 0, "")

        self.worker.run(fetch, on_done, lambda e: self.worker.error.emit(str(e)))

    def _remove_from_unshuffled(self, track: dict):
        if not self._unshuffled:
            return
        idx = next((i for i, t in enumerate(self._unshuffled) if t is track), -1)
        if idx < 0 and track.get("uri"):
            uri = track["uri"]
            idx = next((i for i, t in enumerate(self._unshuffled) if t.get("uri") == uri), -1)
        if idx >= 0:
            self._unshuffled.pop(idx)

    @Slot(str)
    def addToQueue(self, uri):
        def on_done(t):
            if t:
                item = dict(t)
                self._queue.append(item)
                if self._unshuffled is not None:
                    self._unshuffled.append(item)
                self.queueChanged.emit()
                self._prefetch_next()
                self.worker.error.emit(tr("Added to queue"))

        self.worker.run(lambda: self._lookup(uri), on_done, lambda e: self.worker.error.emit(str(e)))

    @Slot(str)
    def playNext(self, uri):
        def on_done(t):
            if not t:
                return
            item = dict(t)
            if not self._queue and not self._state.get("hasTrack"):
                self._start_queue([item], 0)
                return
            if 0 <= self._queue_index < len(self._queue):
                current = self._queue[self._queue_index]
                self._queue.insert(self._queue_index + 1, item)
                if self._unshuffled is not None:
                    cur_idx = next((i for i, u in enumerate(self._unshuffled) if u is current), -1)
                    if cur_idx < 0 and current.get("uri"):
                        cur_idx = next((i for i, u in enumerate(self._unshuffled) if u.get("uri") == current["uri"]), -1)
                    self._unshuffled.insert(cur_idx + 1 if cur_idx >= 0 else 0, item)
            else:
                self._queue.insert(0, item)
                self._queue_index = 0
                if self._unshuffled is not None:
                    self._unshuffled.insert(0, item)
            self.queueChanged.emit()
            self._prefetch_next()
            self.worker.error.emit(tr("Will play next"))

        self.worker.run(lambda: self._lookup(uri), on_done, lambda e: self.worker.error.emit(str(e)))

    @Slot(int)
    def removeFromQueue(self, offset):
        if self._queue_index < 0:
            return
        pos = self._queue_index + 1 + int(offset)
        if not (self._queue_index < pos < len(self._queue)):
            return
        removed = self._queue.pop(pos)
        self._remove_from_unshuffled(removed)
        self.queueChanged.emit()
        self._prefetch_next()

    @Slot(int, int)
    def moveInQueue(self, from_offset, to_offset):
        if self._queue_index < 0:
            return
        base = self._queue_index + 1
        from_pos = base + int(from_offset)
        to_pos = base + int(to_offset)
        if not (base <= from_pos < len(self._queue)) or not (base <= to_pos < len(self._queue)) or from_pos == to_pos:
            return
        item = self._queue.pop(from_pos)
        self._queue.insert(to_pos, item)
        self.queueChanged.emit()
        self._prefetch_next()

    @Slot()
    def clearQueue(self):
        cur = self._current_track()
        if cur is not None:
            self._queue = [cur]
            self._queue_index = 0
            self._unshuffled = [cur] if self._unshuffled is not None else None
        else:
            self._queue = []
            self._queue_index = -1
            self._unshuffled = None
        self.queueChanged.emit()
        self._prefetch_next()

    @Slot(result="QVariantList")
    def fullQueue(self):
        return list(self._queue)

    @Slot(result="QVariantList")
    def queueUris(self):
        return [t["uri"] for t in self._queue if t.get("uri")]

    @Slot()
    def toggleLike(self):
        uri = self._state.get("uri")
        if uri:
            self.setLiked(uri, not self._state.get("liked"))

    @Slot(str, bool)
    def setLiked(self, uri, liked):
        track = self._known(uri)
        if track is None and uri == self._state.get("uri"):
            track = {k: self._state.get(k) for k in ("uri", "id", "name", "artists", "artistId", "album",
                                                      "albumId", "imageSmall", "image", "imageLarge",
                                                      "durationMs", "explicit")}
        if not track:
            return
        if uri == self._state.get("uri"):
            self._state["liked"] = liked
            self.stateChanged.emit()
        if self.store.set_liked(track, liked):
            self.likedChanged.emit(uri, liked)
            self.worker.error.emit(tr("Saved to Liked Songs") if liked else tr("Removed from Liked Songs"))

    # ---- devices & queue --------------------------------------------------

    def _on_audio_devices(self, raw_devices: list):
        self._rebuild_devices(raw_devices)

    def _on_audio_device(self, dev_id: str):
        # Engine reports active device after startup/switch; rebuild list active highlight
        raw = self.engine.audio_devices() if hasattr(self.engine, "audio_devices") else []
        if raw:
            self._rebuild_devices(raw)

    def _rebuild_devices(self, raw_devices: list):
        vol = int(self._state.get("volume", 80))
        local_name = self._setting("device_name", "Senada")
        active_id = self._audio_device or "auto"
        items = []
        for d in raw_devices or []:
            dev_id = d.get("id") or d.get("name") or ""
            if not dev_id:
                continue
            is_auto = dev_id == "auto"
            desc = tr("System default") if is_auto else (d.get("description") or dev_id)
            items.append({
                "id": dev_id,
                "name": desc,
                "type": "computer" if is_auto else "speaker",
                "active": dev_id == active_id or (active_id == "local" and is_auto),
                "volume": vol,
                "local": is_auto,
                "restricted": False,
            })
        if not items:
            items = [{
                "id": "auto",
                "name": f"{local_name}",
                "type": "computer",
                "active": True,
                "volume": vol,
                "local": True,
                "restricted": False,
            }]
        elif not any(x["active"] for x in items):
            items[0]["active"] = True
        self._devices = items
        active_item = next((x for x in items if x["active"]), items[0])
        self._state["deviceId"] = active_item["id"]
        self._state["deviceName"] = active_item["name"]
        self._state["deviceType"] = active_item["type"]
        self.devicesChanged.emit()
        self.stateChanged.emit()

    @Slot()
    def applyAudioSettings(self):
        q = str(self._setting("audio_quality", "best") or "best").lower()
        self.streams.set_quality(q)
        if hasattr(self.engine, "set_quality"):
            self.engine.set_quality(q)
        if not (hasattr(self.engine, "audio_devices") and self.engine.audio_devices()):
            self._rebuild_devices([])

    @Slot()
    def refreshDevices(self):
        devs = self.engine.audio_devices() if hasattr(self.engine, "audio_devices") else []
        self._rebuild_devices(devs)
        if not devs and hasattr(self.engine, "probe_audio_devices"):
            self.worker.run(self.engine.probe_audio_devices,
                            lambda probed: self._rebuild_devices(probed),
                            lambda _e: None)

    @Slot(str)
    def transfer(self, device_id):
        dev = str(device_id or "auto").strip() or "auto"
        if dev == "local":
            dev = "auto"
        self._audio_device = dev
        if isinstance(self.settings, dict) or hasattr(self.settings, "__setitem__"):
            self.settings["audio_device"] = dev
        if hasattr(self.engine, "set_audio_device"):
            self.engine.set_audio_device(dev)
        devs = self.engine.audio_devices() if hasattr(self.engine, "audio_devices") else []
        self._rebuild_devices(devs)

    @Slot()
    def refreshQueue(self):
        self.queueChanged.emit()

    # ---- session persistence --------------------------------------------

    @staticmethod
    def _serialize_track(track: dict) -> dict:
        keys = ("uri", "id", "name", "artists", "artistId", "album", "albumId",
                "imageSmall", "image", "imageLarge", "durationMs", "explicit", "matchScore")
        return {k: track[k] for k in keys if k in track and track[k] is not None}

    def save_playback_state(self, path: Path = PLAYBACK_FILE):
        try:
            path = Path(path)
            if not self._queue or self._queue_index < 0:
                if path.exists():
                    path.unlink()
                return
            data = {
                "queue": [self._serialize_track(t) for t in self._queue],
                "index": self._queue_index,
                "positionMs": int(self._position or 0),
                "shuffle": bool(self._state.get("shuffle", False)),
                "repeat": self._state.get("repeat", "off"),
                "contextUri": self._state.get("contextUri", ""),
                "volume": int(self._state.get("volume", 80)),
            }
            if self._unshuffled is not None:
                data["unshuffled"] = [self._serialize_track(t) for t in self._unshuffled]
            write_private(path, data)
        except OSError as e:
            logger.debug("could not save playback state: %s", e)

    def restore_playback_state(self, path: Path = PLAYBACK_FILE) -> bool:
        path = Path(path)
        if not path.exists():
            return False
        data = read_json(path)
        if not isinstance(data, dict):
            return False
        queue = [t for t in (data.get("queue") or []) if isinstance(t, dict) and t.get("uri")]
        if not queue:
            return False
        idx = max(0, min(int(data.get("index", 0)), len(queue) - 1))
        track = queue[idx]
        self._queue = queue
        self._queue_index = idx
        unshuffled = data.get("unshuffled")
        self._unshuffled = [t for t in unshuffled if isinstance(t, dict) and t.get("uri")] if isinstance(unshuffled, list) and unshuffled else None
        self.cache_tracks(queue)

        vol = max(0, min(100, int(data.get("volume", self._state.get("volume", 80)))))
        repeat = data.get("repeat", "off")
        if repeat not in ("off", "context", "track"):
            repeat = "off"
        shuffle = bool(data.get("shuffle", False))
        context_uri = data.get("contextUri") or ""
        liked = self.store.is_liked(track.get("uri", "")) if self.store is not None else False

        self._state = {
            **self._state,
            **track,
            "hasTrack": True,
            "isPlaying": False,
            "liked": liked,
            "shuffle": shuffle,
            "repeat": repeat,
            "contextUri": context_uri,
            "volume": vol,
        }
        self._devices[0]["volume"] = vol
        self.engine.set_volume(vol)

        pos = max(0, int(data.get("positionMs", 0)))
        dur = int(track.get("durationMs") or 0)
        if dur > 0:
            pos = min(pos, dur)
        self._position = pos
        self._restored_pending = True

        self.stateChanged.emit()
        self.positionChanged.emit()
        self.trackChanged.emit()
        self.queueChanged.emit()

        art = track.get("imageSmall")
        if art:
            self._on_cover(art)
        return True
