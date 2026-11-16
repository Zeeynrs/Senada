"""Today's listening state stays distinct from a still-connected streak."""

import datetime
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from senada import stats
from senada.plays import PlayTracker
from tests.test_stats import FakePlayer

APP = QCoreApplication.instance() or QCoreApplication([])


class MusicalStreak(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'plays.db'
        self.log = stats.PlayLog(self.path)
        self.addCleanup(self.log.close)
        self.player = FakePlayer()
        self.tracker = PlayTracker(self.player)
        self.controller = stats.Stats(self.tracker, self.player, self.log)
        self.addCleanup(self.controller.close)

    def hear(self, seconds):
        start = self.player.position
        self.player.move(*(start + n * 1000 for n in range(1, seconds + 1)))

    def test_yesterdays_streak_is_dormant_until_today_qualifies(self):
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        self.log.add({'uri': 'old', 'durationMs': 200_000}, 60_000, yesterday.timestamp())
        data = self.controller.summary('month')
        self.assertEqual(data['streakDays'], 1)
        self.assertFalse(data['streakActiveToday'])
        self.player.start(1)
        self.hear(29)
        self.assertFalse(self.controller.summary('month')['streakActiveToday'])
        self.hear(1)
        for period in ('week', 'month', 'year', 'all'):
            data = self.controller.summary(period)
            self.assertTrue(data['streakActiveToday'])
            self.assertEqual(data['streakDays'], 2)

    def test_live_activation_survives_restart_without_double_counting_completed_plays(self):
        self.player.start(1)
        self.hear(30)
        self.assertTrue(self.controller.summary('week')['streakActiveToday'])
        self.assertEqual(self.controller.summary('week')['plays'], 0)
        again = stats.PlayLog(self.path)
        try:
            self.assertEqual(again.streak_status(), (1, 1, True))
        finally:
            again.close()
        self.hear(15)
        self.tracker.flush()
        data = self.controller.summary('week')
        self.assertEqual(data['plays'], 1)
        self.assertEqual(data['streakDays'], 1)

    def test_seeks_pauses_and_multiple_short_skips_do_not_activate_a_day(self):
        self.player.start(1)
        self.player.move(60_000)
        self.player.state['isPlaying'] = False
        self.player.move(61_000, 62_000)
        self.assertFalse(self.controller.summary('month')['streakActiveToday'])
        for n in range(2, 5):
            self.player.start(n)
            self.hear(10)
        self.assertFalse(self.controller.summary('month')['streakActiveToday'])

    def test_half_of_a_short_song_qualifies_during_playback(self):
        self.player.start(1, duration=20_000)
        self.hear(9)
        self.assertFalse(self.controller.summary('month')['streakActiveToday'])
        self.hear(1)
        self.assertTrue(self.controller.summary('month')['streakActiveToday'])

    def test_a_song_crossing_midnight_must_qualify_again_for_the_new_day(self):
        day = datetime.date(2026, 11, 16)
        before = datetime.datetime.combine(day, datetime.time(23, 59, 30)).timestamp()
        with patch('senada.plays.time.time', return_value=before):
            self.player.start(1)
            self.hear(30)
        next_day = day + datetime.timedelta(days=1)
        after = datetime.datetime.combine(next_day, datetime.time(0, 0, 1)).timestamp()
        with patch('senada.plays.time.time', return_value=after):
            self.hear(1)
        self.assertEqual(self.log.streak_status(next_day), (1, 1, False))
        with patch('senada.plays.time.time', return_value=after + 29):
            self.hear(29)
        self.assertEqual(self.log.streak_status(next_day), (2, 2, True))

    def test_completed_play_does_not_credit_a_day_without_its_own_qualifying_listen(self):
        day = datetime.date(2026, 11, 16)
        before = datetime.datetime.combine(day, datetime.time(23, 59, 50)).timestamp()
        with patch('senada.plays.time.time', return_value=before):
            self.player.start(1)
            self.hear(10)
        after = datetime.datetime(2026, 11, 17, 0, 0, 1).timestamp()
        with patch('senada.plays.time.time', return_value=after):
            self.hear(1)
        with patch('senada.plays.time.time', return_value=after + 19):
            self.hear(19)
        self.tracker.flush()
        next_day = day + datetime.timedelta(days=1)
        self.assertEqual(self.log.streak_status(next_day), (0, 0, False))
        again = stats.PlayLog(self.path)
        try:
            self.assertEqual(again.streak_status(next_day), (0, 0, False))
        finally:
            again.close()

    def test_midnight_tick_credits_the_qualifying_previous_day_slice(self):
        day = datetime.date(2026, 11, 16)
        start = datetime.datetime(2026, 11, 16, 23, 59, 29, 500000).timestamp()
        with patch('senada.plays.time.time', return_value=start):
            self.player.start(1)
        for second in range(1, 30):
            with patch('senada.plays.time.time', return_value=start + second):
                self.hear(1)
        with patch('senada.plays.time.time', return_value=start + 32):
            self.player.move(32_000)
        self.assertEqual(self.log.streak_status(day + datetime.timedelta(days=1)), (1, 1, False))

    def test_legacy_play_dates_are_imported_when_the_daily_table_is_created(self):
        path = Path(self.tmp.name) / 'legacy.db'
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE plays (at REAL, uri TEXT, name TEXT, artists TEXT, artist TEXT, '
                       'album TEXT, image TEXT, listened_ms INTEGER, duration_ms INTEGER)')
            for day in (14, 15):
                db.execute('INSERT INTO plays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                           (datetime.datetime(2026, 11, day, 12).timestamp(), str(day), 'Old song',
                            'Artist', 'Artist', '', '', 60_000, 200_000))
            db.commit()
        migrated = stats.PlayLog(path)
        try:
            self.assertEqual(migrated.streak_status(datetime.date(2026, 11, 16)), (2, 2, False))
        finally:
            migrated.close()

    def test_existing_play_history_and_a_broken_streak_are_preserved(self):
        for day in (12, 13, 14):
            at = datetime.datetime(2026, 11, day, 12).timestamp()
            self.log.add({'uri': str(day)}, 60_000, at)
        self.assertEqual(self.log.streak_status(datetime.date(2026, 11, 15)), (3, 3, False))
        self.assertEqual(self.log.streak_status(datetime.date(2026, 11, 16)), (0, 3, False))

    def test_unavailable_statistics_use_a_dormant_default(self):
        self.controller.log = None
        self.assertFalse(self.controller.summary('month')['streakActiveToday'])


class StreakRendering(unittest.TestCase):
    def test_milestones_dormant_and_lit_artwork_and_compact_layout(self):
        fixture = Path(__file__).parent / 'qml' / 'streak_smoke.qml'
        script = r'''
import sys
from PySide6.QtCore import QObject, QPointF, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest
from PySide6.QtQuickControls2 import QQuickStyle

app = QGuiApplication([])
QQuickStyle.setStyle('Basic')
engine = QQmlApplicationEngine()
engine.load(sys.argv[1])
assert engine.rootObjects(), 'Streak QML did not load'
window = engine.rootObjects()[0]

def verify():
    try:
        card = window.findChild(QObject, 'streakCard')
        emblem = next(item for item in card.findChildren(QObject) if item.metaObject().className().startswith('StreakEmblem_'))
        emblem.setProperty('animate', False)
        for days, expected in ((0,0),(1,0),(6,0),(7,1),(29,1),(30,2),(99,2),(100,3),(199,3),(200,4),(499,4),(500,5),(900,5)):
            window.setProperty('currentStreak', days)
            assert emblem.property('stage') == expected, (days, emblem.property('stage'))

        def artwork():
            origin = emblem.mapToScene(QPointF(0,0)).toPoint()
            return window.grabWindow().copy(origin.x(), origin.y(), int(emblem.width()), int(emblem.height()))

        def colorful(image):
            count = 0
            for y in range(0, image.height(), 2):
                for x in range(0, image.width(), 2):
                    color = image.pixelColor(x,y)
                    count += max(color.red(),color.green(),color.blue()) - min(color.red(),color.green(),color.blue()) > 40
            return count

        window.setProperty('currentStreak', 100)
        QTest.qWait(150)
        dormant = colorful(artwork())
        window.setProperty('activeToday', True)
        QTest.qWait(150)
        assert emblem.property('lit') is True
        assert colorful(artwork()) > dormant + 15, 'Active artwork did not light up'
        origin = emblem.mapToScene(QPointF(0,0)).toPoint()
        edge = window.grabWindow().pixelColor(origin.x() + int(emblem.width()) + 2,
                                             origin.y() + int(emblem.height() / 2))
        assert edge == card.property('color'), 'Artwork spills outside its allocated space'
        window.setProperty('colorMode', 'light')
        window.resize(320,650)
        QTest.qWait(150)
        assert card.x() >= 0 and card.x() + card.width() <= window.width()
        assert card.height() > 0
        for item in card.findChildren(QObject):
            if 'Label' in item.metaObject().className() and item.isVisible():
                at = item.mapToScene(QPointF(0,0))
                assert at.x() >= card.x() - 1
                assert at.x() + item.width() <= card.x() + card.width() + 1
        print('STREAK_RENDER_OK')
        app.quit()
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(1)

QTimer.singleShot(250, verify)
sys.exit(app.exec())
'''
        result = subprocess.run(
            [sys.executable, '-c', script, str(fixture)],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
                 'QT_SCALE_FACTOR': '1'},
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('STREAK_RENDER_OK', result.stdout)
        for error in ('TypeError', 'ReferenceError', 'Unable to assign', 'not a function'):
            self.assertNotIn(error, result.stderr)
