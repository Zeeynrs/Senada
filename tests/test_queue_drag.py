"""Songs in the queue can be dragged up or down to change their order."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = r'''
import sys
from PySide6.QtCore import Property, QObject, QPoint, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: F401
from PySide6.QtTest import QTest

def song(n):
    return {"uri": f"yt:track:s{n}", "name": f"Song {n}", "artists": "Artist", "durationMs": 180000}

class Player(QObject):
    queueChanged = Signal()
    stateChanged = Signal()
    def __init__(self):
        super().__init__()
        self._queue = [song(n) for n in range(1, 21)]
        self.moves, self.skips = [], []
    @Property("QVariantList", notify=queueChanged)
    def queue(self): return list(self._queue)
    @Property("QVariantMap", notify=stateChanged)
    def state(self): return {"uri": "yt:track:now", "isPlaying": True, "hasTrack": True}
    @Property(bool, constant=True)
    def autoplay(self): return False
    @Slot()
    def refreshQueue(self): self.queueChanged.emit()
    @Slot(int, int)
    def moveInQueue(self, a, b):
        self.moves.append((a, b))
        self._queue.insert(b, self._queue.pop(a))
        self.queueChanged.emit()
    @Slot(int)
    def skip(self, n): self.skips.append(n)

class Library(QObject):
    changed = Signal()
    @Property(int, notify=changed)
    def likedRevision(self): return 0
    @Property(int, constant=True)
    def matchThreshold(self): return 60
    @Slot(str, result=bool)
    def isLiked(self, uri): return False

class Downloads(QObject):
    changed = Signal()
    @Property(int, notify=changed)
    def revision(self): return 0
    @Property(int, notify=changed)
    def progressRevision(self): return 0
    @Slot(str, result=int)
    def stateOf(self, uri): return -2

app = QGuiApplication([])
engine = QQmlApplicationEngine()
player, library, downloads = Player(), Library(), Downloads()
for name, obj in (("player", player), ("library", library), ("downloads", downloads), ("session", QObject())):
    engine.rootContext().setContextProperty(name, obj)
engine.load(sys.argv[1])
assert engine.rootObjects(), "the queue failed to load"
window = engine.rootObjects()[0]
view = window.findChild(QQuickItem, "queue")

def rows():
    """(name, y in the window, x) of each song row on screen, top to bottom."""
    def walk(item):
        yield item
        for child in item.childItems():
            yield from walk(child)
    found = []
    for item in walk(view):
        track = item.property("track")
        if isinstance(track, dict) and track.get("name") and item.property("inQueue") and item.isVisible():
            p = item.mapToScene(item.boundingRect().center())
            found.append((item.property("queueOffset"), track["name"], p.y(), p.x()))
    # the list keeps a spare row it does not draw (out of place for its index): skip it
    shown, last = [], -1e9
    for offset, name, y, x in sorted(found):
        if y > last:
            shown.append((name, y, x))
            last = y
    return sorted(shown, key=lambda r: r[1])

def drag(y0, y1, x):
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, QPoint(x, y0))
    steps = 12
    for i in range(1, steps + 1):
        QTest.mouseMove(window, QPoint(x, int(y0 + (y1 - y0) * i / steps)), 15)
    QTest.qWait(60)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(x, y1), 15)
    QTest.qWait(250)

def check():
    try:
        before = rows()
        names = [r[0] for r in before]
        assert names[:4] == ["Song 1", "Song 2", "Song 3", "Song 4"], before
        step = before[1][1] - before[0][1]
        x = int(before[0][2])
        # drag "Song 1" down past two rows: it lands third
        drag(int(before[0][1]), int(before[0][1] + 2 * step), x)
        assert player.moves == [(0, 2)], player.moves
        after = [r[0] for r in rows()]
        assert after[:4] == ["Song 2", "Song 3", "Song 1", "Song 4"], rows()
        # and back up to the top
        now = rows()
        y = next(r[1] for r in now if r[0] == "Song 1")
        drag(int(y), int(y - 2 * step), x)
        assert player.moves[-1] == (2, 0), player.moves
        # a small wobble is not a move
        y = rows()[3][1]
        drag(int(y), int(y + step * 0.3), x)
        assert len(player.moves) == 2, player.moves
        # rows the drag passed are back in their places, none left shifted
        final = rows()
        gaps = {round(final[i + 1][1] - final[i][1]) for i in range(len(final) - 1)}
        assert gaps == {round(step)}, gaps
        # a double click still plays the song
        QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(x + 120, int(final[1][1])))
        QTest.qWait(100)
        assert player.skips == [2], player.skips
        # held at the bottom edge, the list scrolls along: the song goes further than it could see
        top = rows()[0]
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, QPoint(x, int(top[1])))
        for i in range(1, 13):
            QTest.mouseMove(window, QPoint(x, int(top[1] + (window.height() - 8 - top[1]) * i / 12)), 15)
        QTest.qWait(900)
        scrolled = view.property("contentY")
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(x, window.height() - 8), 15)
        QTest.qWait(250)
        landed = player.moves[-1]
        assert len(player.moves) == 3 and landed[0] == 0 and landed[1] >= 8, player.moves
        # and the list stays where it was scrolled to, not back at the top
        assert scrolled > 100 and abs(view.property("contentY") - scrolled) < 2, (scrolled, view.property("contentY"))
        app.exit(0)
    except Exception:
        import traceback; traceback.print_exc(); app.exit(1)

QTimer.singleShot(800, check)
sys.exit(app.exec())
'''


class QueueDrag(unittest.TestCase):
    def test_dragging_a_song_moves_it_in_the_queue(self):
        fixture = Path(__file__).parent / "qml" / "queue_drag_smoke.qml"
        res = subprocess.run([sys.executable, "-c", SCRIPT, str(fixture)], capture_output=True, text=True,
                             timeout=60, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main()
