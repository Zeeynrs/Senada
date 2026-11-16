"""Glass preferences survive restarts and preserve native-backdrop switching."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal

from senada.config import Settings
from senada.session import Session


class Worker(QObject):
    error = Signal(str)


class GlassPreferences(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "settings.json"
        config = patch("senada.config.SETTINGS_FILE", self.path)
        config.start()
        self.addCleanup(config.stop)
        theme = patch.object(Session, "_apply_theme")
        theme.start()
        self.addCleanup(theme.stop)
        self.worker = Worker()

    def test_liquid_preference_survives_restart_with_opacity_and_color_mode(self):
        session = Session(Settings(), self.worker)
        session.glassMode = "liquid"
        session.glassOpacity = 0.48
        session.themeMode = "light"
        again = Session(Settings(), self.worker)
        self.assertEqual(again.glassMode, "liquid")
        self.assertEqual(again.glassOpacity, 0.48)
        self.assertEqual(again.themeMode, "light")

    def test_switching_from_desktop_to_liquid_disables_native_backdrop(self):
        session = Session(Settings(), self.worker)
        window = QObject()
        with patch("senada.window_effects.apply_backdrop") as apply:
            session.set_window(window)
            session.glassMode = "desktop"
            apply.assert_called_with(window, True, "system")
            session.glassMode = "liquid"
            self.assertEqual(session.glassMode, "liquid")
            apply.assert_called_with(window, False, "system")

    def test_old_modes_and_invalid_values_after_liquid(self):
        session = Session(Settings(), self.worker)
        session.glassMode = "liquid"
        session.glassMode = "invalid"
        self.assertEqual(session.glassMode, "liquid")
        for mode in ("off", "cover", "desktop", "liquid", "off"):
            session.glassMode = mode
            self.assertEqual(session.glassMode, mode)

    def test_unknown_saved_mode_falls_back_to_off(self):
        settings = Settings()
        settings["glass"] = "unknown"
        self.assertEqual(Session(settings, self.worker).glassMode, "off")


class GlassRendering(unittest.TestCase):
    def test_software_material_rounding_opacity_and_mode_changes(self):
        # A separate process avoids mixing QGuiApplication with the suite's
        # QCoreApplication. This exercises actual QML bindings and rendering.
        fixture = Path(__file__).parent / "qml" / "glass_smoke.qml"
        script = r'''
import math
import sys
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication, QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

app = QGuiApplication([])
QQuickStyle.setStyle("Basic")
engine = QQmlApplicationEngine()
engine.load(sys.argv[1])
assert engine.rootObjects(), "Glass QML failed to load"
window = engine.rootObjects()[0]

def surfaces(item):
    found = [item] if item.metaObject().className().startswith("GlassSurface_") else []
    for child in item.childItems():
        found.extend(surfaces(child))
    return found

def verify():
    try:
        materials = surfaces(window.contentItem())
        assert len(materials) >= 2, "Toolbar material was not loaded"
        for material in materials:
            radius = material.property("radius")
            assert math.isfinite(radius) and radius > 0, f"Invalid glass radius: {radius}"
        image = window.grabWindow()
        assert not image.isNull(), "No rendered frame"
        assert image.pixelColor(20, 20) == QColor("#203040"), "Rounded toolbar corner is filled"
        assert image.pixelColor(320, 25) != QColor("#203040"), "Toolbar material is missing"
        thin = window.property("materialOpacity")
        window.setProperty("thickness", 0.9)
        assert window.property("materialOpacity") > thin, "Thickness does not affect material"
        window.setProperty("colorMode", "light")
        assert window.property("dark") is False
        for mode in ("off", "cover", "desktop", "liquid"):
            window.setProperty("glassMode", mode)
            app.processEvents()
        assert len(surfaces(window.contentItem())) >= 2, "Material did not return after switching"
        print("GLASS_RENDER_OK")
        app.quit()
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(1)

QTimer.singleShot(250, verify)
sys.exit(app.exec())
'''
        result = subprocess.run(
            [sys.executable, "-c", script, str(fixture)],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                 "QT_SCALE_FACTOR": "1"},
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GLASS_RENDER_OK", result.stdout)
        self.assertNotIn("TypeError", result.stderr)
        self.assertNotIn("ReferenceError", result.stderr)
