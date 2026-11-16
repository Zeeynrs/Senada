"""Stage 5 tests: search history, autocomplete suggestions, and unified local/offline search."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from PySide6.QtCore import QCoreApplication
    from senada import library as lib, ytmusic
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


def track(uri, name, artists="Artist", album="Album"):
    return {
        "uri": uri,
        "id": uri.split(":")[-1],
        "name": name,
        "artists": artists,
        "album": album,
        "durationMs": 180_000,
        "explicit": False,
        "imageSmall": "",
        "image": "",
        "imageLarge": "",
    }


@unittest.skipIf(lib is None, "PySide6 is not installed")
class SearchHistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "library.json"
        self.store = LocalStore(self.path)

    def test_add_dedup_remove_clear_and_url_ignore(self):
        self.store.add_search_history("Tulus")
        self.store.add_search_history("Hindia")
        self.store.add_search_history("  tulus  ")
        self.store.add_search_history("https://open.spotify.com/track/123")
        self.store.add_search_history("   ")
        self.assertEqual(self.store.search_history(), ["tulus", "Hindia"])

        # Re-read from disk
        reloaded = LocalStore(self.path)
        self.assertEqual(reloaded.search_history(), ["tulus", "Hindia"])

        reloaded.remove_search_history("TULUS")
        self.assertEqual(reloaded.search_history(), ["Hindia"])

        reloaded.clear_search_history()
        self.assertEqual(reloaded.search_history(), [])

    def test_replace_without_search_history_key_remains_safe(self):
        self.store.replace({"liked": [], "playlists": [], "saved": [], "history": []})
        self.assertEqual(self.store.search_history(), [])
        self.store.add_search_history("Pamungkas")
        self.assertEqual(self.store.search_history(), ["Pamungkas"])


@unittest.skipIf(lib is None, "PySide6 is not installed")
class YTMusicSuggestionsTests(unittest.TestCase):
    def test_parses_and_deduplicates_suggestions(self):
        payload = {
            "contents": [{
                "searchSuggestionsSectionRenderer": {
                    "contents": [
                        {
                            "searchSuggestionRenderer": {
                                "suggestion": {"runs": [{"text": "tulus "}, {"text": "monokrom"}]},
                                "navigationEndpoint": {"searchEndpoint": {"query": "tulus monokrom"}},
                            }
                        },
                        {
                            "searchSuggestionRenderer": {
                                "suggestion": {"runs": [{"text": "Tulus Monokrom"}]},
                            }
                        },
                        {
                            "searchSuggestionRenderer": {
                                "suggestion": {"runs": [{"text": "tulus hati hati di jalan"}]},
                            }
                        },
                    ]
                }
            }]
        }
        with mock.patch.object(ytmusic, "_post", return_value=payload) as post:
            got = ytmusic.suggestions("tulus")
        post.assert_called_once()
        self.assertEqual(got, ["tulus monokrom", "tulus hati hati di jalan"])
        self.assertEqual(ytmusic.suggestions("   "), [])


@unittest.skipIf(lib is None, "PySide6 is not installed")
class LibrarySearchStage5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = LocalStore(self.tmp / "library.json")
        self.store.set_liked(track("yt:track:like1", "Monokrom", "Tulus", "Monokrom"), True)
        self.store.set_liked(track("yt:track:like2", "Lagu Lama", "Band X", "Album X"), True)
        self.store.create_playlist("Chill Tulus", [
            track("yt:track:pl1", "Sepatu", "Tulus", "Gajah"),
        ])

        self.catalog = mock.Mock()
        self.catalog.localfiles = mock.Mock()
        self.catalog.localfiles.tracks.return_value = [
            track("local:file:/music/hati.mp3", "Hati-Hati di Jalan", "Tulus", "Manusia"),
        ]
        self.catalog.downloads = mock.Mock()
        self.catalog.downloads.tracks.return_value = [
            track("yt:track:like1", "Monokrom", "Tulus", "Monokrom"),  # same URI as liked -> deduped
            track("yt:track:dl2", "Manusia Kuat", "Tulus", "Monokrom"),
        ]
        self.lib = lib.Library(self.store, self.catalog, SyncWorker(), mock.Mock())
        self.search_events = []
        self.lib.searchFinished.connect(lambda q, res: self.search_events.append((q, res)))

    def test_local_search_multi_token_ranking_and_dedup(self):
        res = self.lib.localSearch("tulus monokrom")
        self.assertEqual([t["uri"] for t in res["tracks"]], ["yt:track:like1", "yt:track:dl2"])

        res2 = self.lib.localSearch("tulus")
        uris = [t["uri"] for t in res2["tracks"]]
        self.assertEqual(len(uris), 4)  # Hati-Hati, Monokrom (deduped), Manusia Kuat, Sepatu
        self.assertEqual(len(res2["playlists"]), 1)
        self.assertEqual(res2["playlists"][0]["name"], "Chill Tulus")

    def test_suggest_combines_history_and_remote_and_handles_offline(self):
        self.lib.addSearchHistory("tulus sepatu")
        with mock.patch.object(ytmusic, "suggestions", return_value=["Tulus Sepatu", "tulus monokrom"]):
            self.lib.suggest("tul")
        self.assertEqual(self.lib.suggestions, ["tulus sepatu", "tulus monokrom"])

        with mock.patch.object(ytmusic, "suggestions", side_effect=ytmusic.YTMusicError("offline")):
            self.lib.suggest("sep")
        self.assertEqual(self.lib.suggestions, ["tulus sepatu"])

        self.lib.suggest("a")
        self.assertEqual(self.lib.suggestions, [])

    def test_search_offline_falls_back_to_local_results(self):
        with mock.patch.object(ytmusic, "search", side_effect=ytmusic.YTMusicError("no network")):
            self.lib.search("hati jalan")
        self.assertEqual(len(self.search_events), 1)
        q, res = self.search_events[0]
        self.assertEqual(q, "hati jalan")
        self.assertTrue(res.get("offline"))
        self.assertNotIn("error", res)
        self.assertEqual([t["uri"] for t in res["localTracks"]], ["local:file:/music/hati.mp3"])
