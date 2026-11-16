"""Your phone as a remote: a small web page on this computer, opened by scanning a QR code.

Off until switched on in Settings → Phone remote. Then Senada listens on the local network
(port 8765, or the next free one) and the page shows the song with play / pause, previous /
next, seeking, the volume and like. Every address carries a random key (kept in the settings,
so a phone's bookmark keeps working; "New link" makes another one and the old link stops),
so only someone with the QR code or the link can use it. No app on the phone, no account.

The server runs on its own thread; commands go to the player on the Qt thread through a
queued signal, and the page reads a copy of the player's state made on the Qt thread.
"""

import json
import logging
import secrets
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

from . import qrcode
from .i18n import tr
from .remote_page import PAGE

try:
    import segno
except ImportError:  # falls back to senada.qrcode
    segno = None

logger = logging.getLogger("senada.remote")

PORT = 8765
PORTS_TRIED = 10
COMMANDS = ("toggle", "next", "previous", "seek", "volume", "shuffle", "repeat", "like",
            "skip", "play_queue", "remove_queue", "clear_queue", "autoplay")


def lan_address() -> str:
    """This computer's address on the local network (no packet is sent)."""
    for target in ("10.255.255.255", "192.168.255.255", "172.31.255.255", "1.1.1.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((target, 1))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return ip
        except OSError:
            continue
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip:
            return ip
    except OSError:
        pass
    return "127.0.0.1"


def page_html() -> bytes:
    return PAGE.encode("utf-8")


def snapshot(state: dict, position: int) -> dict:
    image = state.get("imageLarge") or state.get("image") or ""
    return {
        "hasTrack": bool(state.get("hasTrack")), "name": state.get("name", ""), "artists": state.get("artists", ""),
        "album": state.get("album", ""), "image": image if image.startswith("http") else "",
        "isPlaying": bool(state.get("isPlaying")), "position": int(position or 0),
        "duration": int(state.get("durationMs") or 0), "volume": int(state.get("volume") or 0),
        "shuffle": bool(state.get("shuffle")), "repeat": state.get("repeat", "off"), "liked": bool(state.get("liked")),
    }


class _Handler(BaseHTTPRequestHandler):
    remote = None  # set on a subclass per server

    def log_message(self, fmt, *args):  # no console noise
        logger.debug("remote: " + fmt, *args)

    def _authorized(self) -> bool:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        return secrets.compare_digest((query.get("k") or [""])[0], self.remote.key)

    def _send(self, code, body: bytes, kind="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urllib.parse.urlsplit(self.path).path
        if not self._authorized():
            self._send(403, b"This link is not valid any more: scan the QR code in Senada again.", "text/plain; charset=utf-8")
        elif route == "/":
            self._send(200, page_html(), "text/html; charset=utf-8")
        elif route == "/api/state":
            self._send(200, json.dumps(self.remote.state()).encode())
        elif route == "/api/queue":
            self._send(200, json.dumps(self.remote.queue_state()).encode())
        elif route == "/api/lyrics":
            self._send(200, json.dumps(self.remote.lyrics_state()).encode())
        else:
            self._send(404, b"{}")

    def do_POST(self):
        if not self._authorized() or urllib.parse.urlsplit(self.path).path != "/api/cmd":
            self._send(403, b"{}")
            return
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 4096)
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._send(400, b"{}")
            return
        cmd = body.get("cmd")
        if cmd not in COMMANDS:
            self._send(400, b"{}")
            return
        self.remote.command.emit(cmd, body.get("value"))
        self._send(200, b"{}")


class Remote(QObject):
    changed = Signal()
    toast = Signal(str)
    command = Signal(str, object)   # from the server thread, handled on the Qt thread

    def __init__(self, player, settings, lyrics=None, parent=None):
        super().__init__(parent)
        self.player = player
        self.settings = settings
        self.lyrics = lyrics
        self._server = None
        self._port = 0
        self._lock = threading.Lock()
        self._snap = {}
        self._queue_snap = {"current": {}, "queue": [], "autoplay": False}
        self._lyrics_snap = {"status": "idle", "synced": False, "current": -1, "offset": 0, "lines": []}
        self.command.connect(self._on_command, Qt.ConnectionType.QueuedConnection)
        player.stateChanged.connect(self._refresh)
        player.positionChanged.connect(self._refresh)
        if hasattr(player, "queueChanged"):
            player.queueChanged.connect(self._refresh_queue)
        if hasattr(player, "autoplayChanged"):
            player.autoplayChanged.connect(self._refresh_queue)
        if lyrics is not None:
            lyrics.changed.connect(self._refresh_lyrics)
            lyrics.currentChanged.connect(self._refresh_lyrics)
            if hasattr(lyrics, "offsetChanged"):
                lyrics.offsetChanged.connect(self._refresh_lyrics)
        self._refresh()
        self._refresh_queue()
        self._refresh_lyrics()
        if self.settings["remote"]:
            self._start()

    # ---- the player's side --------------------------------------------------------------------

    @property
    def key(self) -> str:
        key = self.settings["remote_key"]
        if not key:
            key = secrets.token_urlsafe(12)
            self.settings["remote_key"] = key
        return key

    def state(self) -> dict:
        with self._lock:
            return dict(self._snap)

    def queue_state(self) -> dict:
        with self._lock:
            return dict(self._queue_snap)

    def lyrics_state(self) -> dict:
        with self._lock:
            return dict(self._lyrics_snap)

    def _refresh(self):
        snap = snapshot(self.player.state, self.player.position)
        snap["autoplay"] = bool(getattr(self.player, "autoplay", False))
        with self._lock:
            self._snap = snap
        self._refresh_queue()

    def _refresh_queue(self):
        st = self.player.state or {}
        upcoming = getattr(self.player, "queue", None) or []
        q_snap = {
            "current": {
                "uri": st.get("uri", ""),
                "name": st.get("name", ""),
                "artists": st.get("artists", ""),
                "hasTrack": bool(st.get("hasTrack")),
            },
            "queue": [
                {
                    "index": i,
                    "uri": t.get("uri", ""),
                    "name": t.get("name", ""),
                    "artists": t.get("artists", ""),
                    "durationMs": int(t.get("durationMs") or 0),
                }
                for i, t in enumerate(upcoming) if isinstance(t, dict)
            ],
            "autoplay": bool(getattr(self.player, "autoplay", False)),
            "shuffle": bool(st.get("shuffle")),
            "repeat": st.get("repeat", "off"),
        }
        with self._lock:
            self._queue_snap = q_snap

    def _refresh_lyrics(self):
        lyr = self.lyrics
        if lyr is None:
            data = {"status": "none", "synced": False, "current": -1, "offset": 0, "lines": []}
        else:
            lines = getattr(lyr, "lines", None) or []
            data = {
                "status": getattr(lyr, "status", "idle"),
                "synced": bool(getattr(lyr, "synced", False)),
                "current": int(getattr(lyr, "current", -1)),
                "offset": int(getattr(lyr, "offset", 0)),
                "lines": [
                    {"t": int(l.get("t") or 0), "text": str(l.get("text") or ""), "sub": str(l.get("sub") or "")}
                    for l in lines if isinstance(l, dict)
                ],
            }
        with self._lock:
            self._lyrics_snap = data

    def _on_command(self, cmd, value):
        p = self.player
        if cmd == "toggle":
            p.togglePlay()
        elif cmd == "next":
            p.next()
        elif cmd == "previous":
            p.previous()
        elif cmd == "seek" and isinstance(value, (int, float)):
            p.seek(int(value))
        elif cmd == "volume" and isinstance(value, (int, float)):
            p.setVolume(int(value))
        elif cmd == "shuffle":
            p.toggleShuffle()
        elif cmd == "repeat":
            p.cycleRepeat()
        elif cmd == "like":
            p.toggleLike()
        elif cmd == "skip" and isinstance(value, (int, float)) and hasattr(p, "skip"):
            p.skip(max(1, int(value)))
        elif cmd == "play_queue" and isinstance(value, (int, float)) and int(value) >= 0 and hasattr(p, "skip"):
            p.skip(int(value) + 1)
        elif cmd == "remove_queue" and isinstance(value, (int, float)) and hasattr(p, "removeFromQueue"):
            p.removeFromQueue(int(value))
        elif cmd == "clear_queue" and hasattr(p, "clearQueue"):
            p.clearQueue()
        elif cmd == "autoplay" and hasattr(p, "setAutoplay"):
            p.setAutoplay(bool(value) if isinstance(value, bool) else not getattr(p, "autoplay", False))

    # ---- the server ---------------------------------------------------------------------------

    def _start(self):
        if self._server is not None:
            return True
        _ = self.key  # made now, so the link is known before the first phone asks
        handler = type("Handler", (_Handler,), {"remote": self})
        for port in range(PORT, PORT + PORTS_TRIED):
            try:
                server = ThreadingHTTPServer(("0.0.0.0", port), handler)
                break
            except OSError:
                continue
        else:
            self.toast.emit(tr("The phone remote could not start: no free port"))
            return False
        server.daemon_threads = True
        self._server, self._port = server, port
        threading.Thread(target=server.serve_forever, name="senada-remote", daemon=True).start()
        logger.info("phone remote on port %d", port)
        return True

    def _stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server, self._port = None, 0

    def close(self):
        self._stop()

    # ---- QML ----------------------------------------------------------------------------------

    @Property(bool, notify=changed)
    def enabled(self):
        return self._server is not None

    @enabled.setter
    def enabled(self, on):
        on = bool(on)
        if on == self.enabled:
            return
        ok = self._start() if on else (self._stop() or True)
        self.settings["remote"] = on and ok
        self.changed.emit()

    @Property(str, notify=changed)
    def url(self):
        if not self._port:
            return ""
        return f"http://{lan_address()}:{self._port}/?k={self.key}"

    @Property(str, notify=changed)
    def qr(self):
        """The link as a QR code (an SVG data URI for an Image)."""
        if not self._port:
            return ""
        url = self.url
        if segno is not None:
            return segno.make(url, error="m").svg_data_uri(scale=6, border=2, dark="#000000", light="#ffffff")
        try:
            return qrcode.svg_data_uri(url, scale=6, border=2, dark="#000000", light="#ffffff")
        except ValueError:
            return ""

    @Slot()
    def refresh(self):
        """Re-evaluate the active LAN address and QR code (e.g. after switching Wi-Fi)."""
        self.changed.emit()

    @Slot()
    def newLink(self):
        """A new key: the old link (and phones that kept it) stop working."""
        self.settings["remote_key"] = secrets.token_urlsafe(12)
        self.changed.emit()
