import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QObject, Signal

from senada import lyrics as lyr_mod
from senada import remote as remote_mod
from senada.localfiles import LocalFiles, _embedded_lyrics, _sylt_lines
from senada.lyrics import Lyrics
from tests.test_playback_extras import SyncWorker

APP = QCoreApplication.instance() or QCoreApplication([])


class FakeLyricsPlayer(QObject):
    trackChanged = Signal()
    positionChanged = Signal()

    def __init__(self):
        super().__init__()
        self.state = {"uri": "yt:track:a", "name": "Song A", "artists": "Artist", "durationMs": 60000}
        self.position = 0
        self.resolver = type("R", (), {"cached": lambda _self, _u: None})()


class LyricsOffsetTests(unittest.TestCase):
    def test_offset_shifts_position_and_persists_per_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            off_file = Path(tmp) / "offsets.json"
            with patch.object(lyr_mod, "OFFSET_FILE", off_file):
                player = FakeLyricsPlayer()
                settings = {"lyrics_source": "auto", "lyrics_extra": "off", "lyrics_translate_to": "id"}
                lyr = Lyrics(player, SyncWorker(), settings)
                # Load cached synced lyrics directly for two tracks
                sample = {
                    "synced": True,
                    "source": "lrclib",
                    "lines": [
                        {"t": 1000, "text": "Line 1"},
                        {"t": 3000, "text": "Line 2"},
                    ],
                }
                lyr._cache[("yt:track:a", "auto")] = sample
                lyr._cache[("yt:track:b", "auto")] = sample

                player.trackChanged.emit()
                player.position = 2200  # 2200 + 250 = 2450 -> Line 1 (idx 0)
                player.positionChanged.emit()
                self.assertEqual(lyr.current, 0)

                # Advance lyrics by +600ms -> 2200 + 600 + 250 = 3050 -> Line 2 (idx 1)
                lyr.adjustOffset(600)
                self.assertEqual(lyr.offset, 600)
                self.assertEqual(lyr.current, 1)

                # Switch to track B -> offset is 0 for track B
                player.state = {"uri": "yt:track:b", "name": "Song B", "artists": "Artist", "durationMs": 60000}
                player.trackChanged.emit()
                self.assertEqual(lyr.offset, 0)

                # Reload Lyrics from disk -> track A keeps +600ms
                lyr2 = Lyrics(player, SyncWorker(), settings)
                lyr2._cache[("yt:track:a", "auto")] = sample
                player.state = {"uri": "yt:track:a", "name": "Song A", "artists": "Artist", "durationMs": 60000}
                player.trackChanged.emit()
                self.assertEqual(lyr2.offset, 600)

                lyr2.resetOffset()
                self.assertEqual(lyr2.offset, 0)


class FakeSylt:
    def __init__(self, entries):
        self.text = entries


class FakeUslt:
    def __init__(self, text):
        self.text = text


class FakeId3Tags:
    def __init__(self, sylt=None, uslt=None):
        self._sylt = sylt or []
        self._uslt = uslt or []

    def getall(self, key):
        return self._sylt if key == "SYLT" else self._uslt if key == "USLT" else []


class EmbeddedLyricsTests(unittest.TestCase):
    def test_sylt_lines_handles_both_syllables_and_whole_lines(self):
        whole = _sylt_lines([("First", 500), ("Second", 2000)])
        self.assertEqual(whole, [{"t": 500, "text": "First"}, {"t": 2000, "text": "Second"}])

        syl = _sylt_lines([("Hel", 500), ("lo\n", 800), ("World\n", 1500)])
        self.assertEqual(syl, [{"t": 500, "text": "Hello"}, {"t": 1500, "text": "World"}])

    def test_embedded_lyrics_supports_id3_mp4_and_vorbis(self):
        fake_mutagen = lambda tags: type("M", (), {"File": staticmethod(lambda _p: type("F", (), {"tags": tags})())})
        # ID3 SYLT
        with patch("senada.localfiles.mutagen", fake_mutagen(FakeId3Tags(sylt=[FakeSylt([("Alpha", 1000)])]))):
            res = _embedded_lyrics("/tmp/song.mp3")
        self.assertEqual(res, {"synced": True, "lines": [{"t": 1000, "text": "Alpha"}], "source": "file"})

        # ID3 USLT with LRC timestamps
        lrc_txt = "[00:01.00]One\n[00:02.50]Two"
        with patch("senada.localfiles.mutagen", fake_mutagen(FakeId3Tags(uslt=[FakeUslt(lrc_txt)]))):
            res = _embedded_lyrics("/tmp/song.mp3")
        self.assertTrue(res["synced"])
        self.assertEqual([l["text"] for l in res["lines"]], ["One", "Two"])

        # MP4 ©lyr plain lyrics
        with patch("senada.localfiles.mutagen", fake_mutagen({"\xa9lyr": ["Line A\nLine B"]})):
            res = _embedded_lyrics("/tmp/song.m4a")
        self.assertFalse(res["synced"])
        self.assertEqual([l["text"] for l in res["lines"]], ["Line A", "Line B"])

        # FLAC/Vorbis LYRICS
        with patch("senada.localfiles.mutagen", fake_mutagen({"LYRICS": ["[00:05.00]Synced"]})):
            res = _embedded_lyrics("/tmp/song.flac")
        self.assertTrue(res["synced"])
        self.assertEqual(res["lines"], [{"t": 5000, "text": "Synced"}])

    def test_localfiles_prefers_sidecar_lrc_over_embedded(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "track.mp3"
            audio.write_bytes(b"audio")
            lrc = Path(tmp) / "track.lrc"
            lrc.write_text("[00:01.00]Sidecar line", encoding="utf-8")
            uri = f"local:file:{audio}"
            files = LocalFiles({"local_folders": []})
            with patch("senada.localfiles._embedded_lyrics", return_value={"synced": False, "lines": [{"t": 0, "text": "Embedded"}], "source": "file"}):
                got = files.lyrics_for(uri)
                self.assertEqual(got["lines"][0]["text"], "Sidecar line")
                lrc.unlink()
                got2 = files.lyrics_for(uri)
                self.assertEqual(got2["lines"][0]["text"], "Embedded")


class FakeRemotePlayer(QObject):
    stateChanged = Signal()
    positionChanged = Signal()
    queueChanged = Signal()
    autoplayChanged = Signal()

    def __init__(self):
        super().__init__()
        self.state = {"hasTrack": True, "uri": "yt:track:1", "name": "Now", "artists": "Art",
                      "durationMs": 120000, "isPlaying": True, "shuffle": False, "repeat": "off", "volume": 80, "liked": False}
        self.position = 1000
        self.queue = [{"uri": "yt:track:2", "name": "Next", "artists": "Art2", "durationMs": 90000}]
        self.autoplay = False
        self.calls = []

    def togglePlay(self): self.calls.append(("toggle", None))
    def next(self): self.calls.append(("next", None))
    def previous(self): self.calls.append(("prev", None))
    def seek(self, ms): self.calls.append(("seek", ms))
    def setVolume(self, v): self.calls.append(("volume", v))
    def toggleShuffle(self): self.calls.append(("shuffle", None))
    def cycleRepeat(self): self.calls.append(("repeat", None))
    def toggleLike(self): self.calls.append(("like", None))
    def skip(self, n): self.calls.append(("skip", n))
    def removeFromQueue(self, idx): self.calls.append(("remove_queue", idx))
    def clearQueue(self): self.calls.append(("clear_queue", None))
    def setAutoplay(self, on):
        self.autoplay = on
        self.calls.append(("autoplay", on))


class FakeRemoteLyrics(QObject):
    changed = Signal()
    currentChanged = Signal()
    offsetChanged = Signal()

    def __init__(self):
        super().__init__()
        self.status = "ready"
        self.synced = True
        self.current = 0
        self.offset = 500
        self.lines = [{"t": 1000, "text": "Hello phone", "sub": "Halo ponsel"}]


class RemoteQueueAndLyricsTests(unittest.TestCase):
    def setUp(self):
        self.player = FakeRemotePlayer()
        self.lyrics = FakeRemoteLyrics()
        self.settings = {"remote": False, "remote_key": "secret123"}
        self.remote = remote_mod.Remote(self.player, self.settings, self.lyrics)
        self.remote.enabled = True
        self.port = self.remote._port

    def tearDown(self):
        self.remote.close()

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as resp:
            return json.loads(resp.read().decode())

    def test_queue_and_lyrics_endpoints_and_commands(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/queue")
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()

        q = self._get("/api/queue?k=secret123")
        self.assertEqual(q["current"]["name"], "Now")
        self.assertEqual(q["queue"][0]["name"], "Next")

        lyr = self._get("/api/lyrics?k=secret123")
        self.assertTrue(lyr["synced"])
        self.assertEqual(lyr["offset"], 500)
        self.assertEqual(lyr["lines"][0]["sub"], "Halo ponsel")

        for payload in ({"cmd": "play_queue", "value": 0}, {"cmd": "remove_queue", "value": 0},
                        {"cmd": "clear_queue"}, {"cmd": "autoplay", "value": True}):
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/cmd?k=secret123",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status, 200)
        APP.processEvents()
        self.assertEqual(self.player.calls, [
            ("skip", 1), ("remove_queue", 0), ("clear_queue", None), ("autoplay", True),
        ])

    def test_qr_works_without_segno_and_refresh_emits_changed(self):
        import urllib.parse
        from senada import qrcode

        events = []
        self.remote.changed.connect(lambda: events.append(True))
        with patch.object(remote_mod, "segno", None):
            uri = self.remote.qr
            self.assertTrue(uri.startswith("data:image/svg+xml;utf8,"))
            svg = urllib.parse.unquote(uri.split(",", 1)[1])
            self.assertIn("<svg", svg)
            self.assertIn("<path", svg)

        self.remote.refresh()
        self.assertGreaterEqual(len(events), 1)
        # Check matrix sizes across Versions 1-6 (up to 106 bytes)
        self.assertEqual(len(qrcode.encode_matrix("short")), 21)
        self.assertEqual(len(qrcode.encode_matrix("A" * 100)), 41)


if __name__ == "__main__":
    unittest.main()
