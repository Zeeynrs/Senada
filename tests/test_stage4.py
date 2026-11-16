"""Stage 4 tests: playlist reorder/dedupe/sync, M3U import/export, and local files grouping."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from PySide6.QtCore import QCoreApplication
    from senada import library as lib, localfiles
    from senada.store import LocalStore
    APP = QCoreApplication.instance() or QCoreApplication([])
except ImportError:  # PySide6 not installed
    lib = None


class SyncWorker:
    def run(self, fn, ok, fail):
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001
            fail(e)
        else:
            ok(res)


def make_track(uri, name, artists="Artist", album="Album", duration=180_000, **extra):
    out = {
        "uri": uri,
        "id": uri.split(":")[-1],
        "name": name,
        "artists": artists,
        "album": album,
        "durationMs": duration,
        "explicit": False,
        "imageSmall": "",
        "image": "",
        "imageLarge": "",
    }
    out.update(extra)
    return out


@unittest.skipIf(lib is None, "PySide6 is not installed")
class LocalStoreStage4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = LocalStore(self.tmp / "library.json")
        self.pid = self.store.create_playlist("Mix", [
            make_track("yt:track:a", "Alpha"),
            make_track("yt:track:b", "Beta"),
            make_track("yt:track:c", "Gamma"),
        ])

    def test_move_in_playlist(self):
        self.assertTrue(self.store.move_in_playlist(self.pid, 0, 2))
        names = [t["name"] for t in self.store.playlist(self.pid)["tracks"]]
        self.assertEqual(names, ["Beta", "Gamma", "Alpha"])
        self.assertFalse(self.store.move_in_playlist(self.pid, 1, 1))
        self.assertFalse(self.store.move_in_playlist(self.pid, -1, 0))
        self.assertFalse(self.store.move_in_playlist("missing", 0, 1))

    def test_remove_playlist_duplicates_by_uri_and_title_artist(self):
        pid = self.store.create_playlist("Dupes", [
            make_track("yt:track:1", "Song One", "Band A"),
            make_track("yt:track:1", "Song One", "Band A"),                 # exact URI dupe
            make_track("yt:track:99", "  song one ", "band a "),           # normalized title+artist dupe
            make_track("yt:track:2", "Song Two", "Band B"),
        ])
        removed = self.store.remove_playlist_duplicates(pid)
        self.assertEqual(removed, 2)
        kept = [t["uri"] for t in self.store.playlist(pid)["tracks"]]
        self.assertEqual(kept, ["yt:track:1", "yt:track:2"])
        self.assertEqual(self.store.remove_playlist_duplicates(pid), 0)

    def test_replace_playlist_tracks_preserves_id_and_updates_meta(self):
        new_tracks = [make_track("yt:track:z", "Zulu")]
        self.assertTrue(self.store.replace_playlist_tracks(self.pid, new_tracks, name="Renamed"))
        pl = self.store.playlist(self.pid)
        self.assertEqual(pl["name"], "Renamed")
        self.assertEqual([t["uri"] for t in pl["tracks"]], ["yt:track:z"])


@unittest.skipIf(lib is None, "PySide6 is not installed")
class M3uTests(unittest.TestCase):
    def test_format_and_parse_m3u_roundtrip(self):
        tracks = [
            make_track("yt:track:abc12345678", "First Song", "Singer A", duration=205_000),
            make_track("local:file:deadbeef", "Local Song", "Singer B", duration=90_000),
        ]
        m3u = lib.format_m3u("Road Trip", tracks, path_lookup=lambda u: "/music/local.mp3" if u.startswith("local:") else None)
        self.assertIn("#EXTM3U", m3u)
        self.assertIn("#PLAYLIST:Road Trip", m3u)
        self.assertIn("#EXTINF:205,Singer A - First Song", m3u)
        self.assertIn("https://music.youtube.com/watch?v=abc12345678", m3u)
        self.assertIn("/music/local.mp3", m3u)

        name, parsed = lib.parse_m3u(m3u)
        self.assertEqual(name, "Road Trip")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["type"], "yt")
        self.assertEqual(parsed[0]["id"], "abc12345678")
        self.assertEqual(parsed[0]["artists"], "Singer A")
        self.assertEqual(parsed[0]["name"], "First Song")
        self.assertEqual(parsed[0]["durationMs"], 205_000)
        self.assertEqual(parsed[1]["type"], "path")
        self.assertEqual(parsed[1]["path"], "/music/local.mp3")

    def test_parse_m3u_short_youtu_be_and_search_fallback_line(self):
        text = "#EXTM3U\nhttps://youtu.be/xyz98765432\n"
        name, entries = lib.parse_m3u(text)
        self.assertEqual(name, "")
        self.assertEqual(entries[0]["type"], "yt")
        self.assertEqual(entries[0]["id"], "xyz98765432")


@unittest.skipIf(lib is None, "PySide6 is not installed")
class LibraryStage4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = LocalStore(self.tmp / "library.json")
        self.catalog = mock.Mock()
        self.catalog.downloads = mock.Mock()
        self.catalog.downloads.path_for.return_value = None
        self.library = lib.Library(self.store, self.catalog, SyncWorker(), mock.Mock())
        self.toasts = []
        self.created = []
        self.library.toast.connect(self.toasts.append)
        self.library.playlistCreated.connect(self.created.append)

    def test_export_and_import_m3u_with_local_and_yt_entries(self):
        local_mp3 = self.tmp / "track.mp3"
        local_mp3.write_bytes(b"")
        local_uri = localfiles.PREFIX + str(local_mp3)
        tracks = [
            make_track(local_uri, "Locally", "Band", duration=120_000),
            make_track("yt:track:ytid0000001", "Cloudly", "Artist", duration=150_000),
        ]
        out_m3u = self.tmp / "exported"  # extensionless -> should become .m3u8
        with mock.patch.object(lib.localfiles, "path_of", side_effect=lambda u: str(local_mp3) if u == local_uri else None):
            self.library.exportTracksM3u("Weekend", tracks, str(out_m3u))

        exported_file = self.tmp / "exported.m3u8"
        self.assertTrue(exported_file.is_file())
        content = exported_file.read_text(encoding="utf-8")
        self.assertIn("#PLAYLIST:Weekend", content)
        self.assertIn(str(local_mp3), content)

        yt_hit = make_track("yt:track:ytid0000001", "Cloudly", "Artist")
        with mock.patch.object(lib.ytmusic, "track", return_value=yt_hit), \
             mock.patch.object(lib.localfiles, "read_track", return_value=make_track(local_uri, "Locally", "Band")):
            self.library.importM3u(exported_file.as_uri())

        self.assertEqual(len(self.created), 1)
        pl = self.store.playlist(self.created[0])
        self.assertEqual(pl["name"], "Weekend")
        self.assertEqual([t["uri"] for t in pl["tracks"]], [local_uri, "yt:track:ytid0000001"])

    def test_sync_imported_playlist_preserves_existing_artwork_and_match_score(self):
        pid = self.store.create_playlist(
            "Spotify Sync",
            [make_track("sp:track:1", "KeepCover", "Art", imageSmall="http://cover/small", matchScore=91)],
            source="https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        )
        fresh = {
            "tracks": [
                make_track("sp:track:1", "KeepCover", "Art", imageSmall=""),
                make_track("sp:track:2", "Brand New", "Art2"),
            ]
        }
        with mock.patch.object(lib.spotify_import, "parse_link", return_value=("playlist", "37i9dQZF1DXcBWIGoYBM5M")), \
             mock.patch.object(lib.spotify_import, "fetch", return_value=fresh), \
             mock.patch.object(self.library, "matchTracks"):
            self.library.syncImportedPlaylist(pid)

        pl = self.store.playlist(pid)
        self.assertEqual(len(pl["tracks"]), 2)
        self.assertEqual(pl["tracks"][0]["imageSmall"], "http://cover/small")
        self.assertEqual(pl["tracks"][0]["matchScore"], 91)
        self.assertEqual(pl["tracks"][1]["name"], "Brand New")

    def test_move_and_dedupe_via_library_slots(self):
        pid = self.store.create_playlist("List", [
            make_track("yt:track:1", "One", "A"),
            make_track("yt:track:2", "Two", "B"),
            make_track("yt:track:2", "Two", "B"),
        ])
        self.library.moveInPlaylist(pid, 0, 2)
        self.assertEqual(self.store.playlist(pid)["tracks"][2]["uri"], "yt:track:1")
        self.library.dedupePlaylist(pid)
        self.assertEqual([t["uri"] for t in self.store.playlist(pid)["tracks"]], ["yt:track:2", "yt:track:1"])
        self.assertTrue(any("duplicate" in t.lower() or "duplikat" in t.lower() for t in self.toasts))


@unittest.skipIf(lib is None, "PySide6 is not installed")
class LocalFilesGroupingTests(unittest.TestCase):
    def test_tag_int_and_sort_key_numeric_disc_and_track(self):
        tags = {"tracknumber": ["2/12"], "discnumber": ["01/02"]}
        self.assertEqual(localfiles._tag_int(tags, "tracknumber"), 2)
        self.assertEqual(localfiles._tag_int(tags, "discnumber"), 1)
        self.assertEqual(localfiles._tag_int({"tracknumber": ["bad"]}, "tracknumber"), 0)

        t10 = make_track("local:file:10", "Zed", "Same", "Album", discNo=1, trackNo=10)
        t2 = make_track("local:file:2", "Alpha", "Same", "Album", discNo=1, trackNo=2)
        d2 = make_track("local:file:3", "Encore", "Same", "Album", discNo=2, trackNo=1)
        ordered = sorted([t10, d2, t2], key=localfiles.sort_key)
        self.assertEqual([t["trackNo"] for t in ordered], [2, 10, 1])
        self.assertEqual([t["discNo"] for t in ordered], [1, 1, 2])

    def test_local_files_groups_albums_artists_and_folders(self):
        tmp = Path(tempfile.mkdtemp())
        album_a = tmp / "ArtistOne" / "FirstRecord"
        album_b = tmp / "ArtistTwo" / "SecondRecord"
        album_a.mkdir(parents=True)
        album_b.mkdir(parents=True)
        f1 = album_a / "02.mp3"
        f2 = album_a / "01.mp3"
        f3 = album_b / "01.mp3"
        for f in (f1, f2, f3):
            f.write_bytes(b"")

        p1, p2, p3 = localfiles.PREFIX + str(f1), localfiles.PREFIX + str(f2), localfiles.PREFIX + str(f3)
        with mock.patch.object(localfiles, "INDEX_FILE", tmp / "idx.json"):
            lf = localfiles.LocalFiles({"local_folders": []})
            lf._index = {
                str(f1): {"track": make_track(p1, "Second", "ArtistOne", "FirstRecord", discNo=1, trackNo=2)},
                str(f2): {"track": make_track(p2, "First", "ArtistOne", "FirstRecord", discNo=1, trackNo=1, imageSmall="img1")},
                str(f3): {"track": make_track(p3, "Solo", "ArtistTwo", "SecondRecord", discNo=1, trackNo=1)},
            }

            albums = lf.groups("albums")
            self.assertEqual([g["name"] for g in albums], ["FirstRecord", "SecondRecord"])
            self.assertEqual(albums[0]["imageSmall"], "img1")
            self.assertEqual([t["name"] for t in albums[0]["tracks"]], ["First", "Second"])

            artists = lf.groups("artists")
            self.assertEqual([g["name"] for g in artists], ["ArtistOne", "ArtistTwo"])
            self.assertEqual(artists[0]["count"], 2)

            folders = lf.groups("folders")
            self.assertEqual([g["name"] for g in folders], ["FirstRecord", "SecondRecord"])
            self.assertEqual(lf.groups("unknown"), [])
