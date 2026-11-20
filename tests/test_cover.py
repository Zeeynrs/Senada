"""Cover art is cut into its shape by a shader, from the image's single texture."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CoverShape(unittest.TestCase):
    def test_shader_files_are_shipped_together(self):
        shaders = ROOT / "qml" / "shaders"
        self.assertTrue((shaders / "rounded-cover.frag").is_file())
        self.assertTrue((shaders / "rounded-cover.frag.qsb").is_file())
        cover = (ROOT / "qml" / "Cover.qml").read_text(encoding="utf-8")
        self.assertIn("shaders/rounded-cover.frag.qsb", cover)
        self.assertNotIn("layer.enabled", cover)  # no extra mask texture per cover
        self.assertNotIn("MultiEffect", cover)

    def test_covers_render_cropped_and_shaped(self):
        # offscreen renders in software (the fallback); SENADA_GPU_TESTS=1 opens a real window
        # so the shader itself is checked
        gpu = os.environ.get("SENADA_GPU_TESTS") == "1"
        fixture = Path(__file__).parent / "qml" / "cover_smoke.qml"
        script = r'''
import sys, tempfile
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

def thirds(path, w, h):
    image = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(image)
    for i, color in enumerate(("#0000ff", "#00ff00", "#ff0000")):
        p.fillRect(i * w // 3, 0, w // 3 + 1, h, QColor(color))
    p.end()
    image.save(str(path))
    return QUrl.fromLocalFile(str(path))

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QGuiApplication([])
tmp = Path(tempfile.mkdtemp())
engine = QQmlApplicationEngine()
engine.setInitialProperties({"wide": thirds(tmp / "wide.png", 300, 100),
                             "big": thirds(tmp / "big.png", 3000, 1000)})
engine.load(sys.argv[1])
assert engine.rootObjects(), "Cover QML failed to load"
window = engine.rootObjects()[0]
tries = [0]

def green(c): return c.green() > 200 and c.red() < 60 and c.blue() < 60
def dark(c): return c.red() < 40 and c.green() < 40 and c.blue() < 40

def verify():
    try:
        if not window.property("loaded") and tries[0] < 40:
            tries[0] += 1
            QTimer.singleShot(100, verify)
            return
        assert window.property("loaded"), "Covers did not load"
        QTimer.singleShot(400, check)  # after the fade-in
    except Exception:
        import traceback; traceback.print_exc(); app.exit(1)

def check():
    try:
        image = window.grabWindow()
        px = lambda x, y: image.pixelColor(x, y)
        software = window.rendererInterface().graphicsApi() == QSGRendererInterface.GraphicsApi.Software
        print("API", window.rendererInterface().graphicsApi())
        for name, x0, size in (("rounded", 10, 100), ("round", 130, 100), ("large", 370, 380)):
            y0 = 10
            assert green(px(x0 + size // 2, y0 + size // 2)), f"{name}: centre is {px(x0 + size // 2, y0 + size // 2).name()}"
            assert green(px(x0 + 3, y0 + size // 2)), f"{name}: left edge is not cropped to the middle"
            assert green(px(x0 + size - 4, y0 + size // 2)), f"{name}: right edge is not cropped to the middle"
            if software:  # no shaders: the plain square image, never an empty cover
                assert green(px(x0 + 1, y0 + 1)), f"{name}: software fallback shows nothing"
            else:
                assert dark(px(x0 + 1, y0 + 1)), f"{name}: corner is filled"
        assert green(px(250 + 1, 10 + 1)), "simple cover is not square"
        print("COVER_RENDER_OK")
        app.quit()
    except Exception:
        import traceback; traceback.print_exc(); app.exit(1)

QTimer.singleShot(100, verify)
sys.exit(app.exec())
'''
        result = subprocess.run(
            [sys.executable, "-c", script, str(fixture)],
            env={**os.environ, "QT_SCALE_FACTOR": "1", **({} if gpu else {"QT_QPA_PLATFORM": "offscreen"})},
            capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("COVER_RENDER_OK", result.stdout)
        self.assertNotIn("ShaderEffect", result.stderr)
        if gpu:
            self.assertNotIn("API GraphicsApi.Software", result.stdout)


if __name__ == "__main__":
    unittest.main()
