"""Cover art kept on disk, so a restart shows it at once instead of downloading it again.

Covers from the image hosts below never change behind their address. The first time one is
asked for, it is downloaded here (on the UI thread, without blocking it) and saved; from then
on QML loads the saved file. Qt's own image loading threads never call into Python: PySide
is not safe there (a QQmlNetworkAccessManagerFactory written in Python crashed at random).
"""

import hashlib
import logging
import os
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .config import CACHE_DIR

logger = logging.getLogger("senada.imagecache")

IMAGE_CACHE = CACHE_DIR / "images"
IMAGE_CACHE_BYTES = 100 * 1024 * 1024  # oldest covers are removed past this size
MAX_IMAGE_BYTES = 8 * 1024 * 1024      # larger answers are not covers
TRIM_EVERY = 200                       # saved covers between two size checks
# covers whose address already names one fixed image (YouTube Music, YouTube, Spotify)
IMAGE_HOSTS = ("googleusercontent.com", "ggpht.com", "ytimg.com", "scdn.co")
MAGIC = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF")  # JPEG, PNG, GIF, WebP


def is_image_host(host: str) -> bool:
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) for h in IMAGE_HOSTS)


def looks_like_image(data: bytes) -> bool:
    return data.startswith(MAGIC) and (not data.startswith(b"RIFF") or data[8:12] == b"WEBP")


def trim(folder: Path, limit: int):
    """Remove the least recently used covers until the folder is below `limit` bytes."""
    try:
        files = [(e.stat().st_mtime, e.stat().st_size, e.path) for e in os.scandir(folder) if e.is_file()]
    except OSError:
        return
    total = sum(size for _, size, _ in files)
    if total <= limit:
        return
    target = limit * 0.9  # some room, so this does not run again after every new cover
    for _, size, path in sorted(files):
        try:
            os.remove(path)
        except OSError:
            continue
        total -= size
        if total <= target:
            break


class ImageCache(QObject):
    """`images` in QML: cached(url) gives the saved file, or "" while it is being downloaded
    (stored(url) follows), or the address itself when it cannot be cached."""

    stored = Signal(str)

    def __init__(self, folder: Path | None = None, limit: int = IMAGE_CACHE_BYTES, parent=None):
        super().__init__(parent)
        self.folder = Path(folder or IMAGE_CACHE)
        self.limit = limit
        self._net = QNetworkAccessManager(self)
        self._net.setTransferTimeout(20000)
        self._net.setAutoDeleteReplies(True)  # Qt deletes each reply after `finished`
        self._pending = {}      # url -> reply
        self._failed = set()    # urls loaded directly from the internet instead
        self._touched = set()   # file names already marked as used this session
        self._saved = 0
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._ok = True
        except OSError as e:
            logger.warning("no image cache in %s: %s", self.folder, e)
            self._ok = False
        self._trim_later()

    def _path(self, url: str) -> Path:
        return self.folder / hashlib.sha1(url.encode("utf-8")).hexdigest()

    @Slot(str, result=str)
    def cached(self, url: str) -> str:
        if (not self._ok or not url.startswith(("https://", "http://")) or url in self._failed
                or not is_image_host(QUrl(url).host())):
            return url
        path = self._path(url)
        if path.is_file():
            if path.name not in self._touched:  # oldest-used covers are the ones removed
                self._touched.add(path.name)
                try:
                    os.utime(path)
                except OSError:
                    pass
            return QUrl.fromLocalFile(str(path)).toString()
        self._fetch(url)
        return ""

    @Slot(str)
    def forget(self, url: str):
        """The saved copy could not be shown: remove it and load this cover from the internet."""
        self._failed.add(url)
        try:
            self._path(url).unlink(missing_ok=True)
        except OSError:
            pass

    def _fetch(self, url: str):
        if url in self._pending:
            return
        reply = self._net.get(QNetworkRequest(QUrl(url)))
        self._pending[url] = reply
        reply.finished.connect(lambda: self._done(url, reply))

    def _done(self, url: str, reply: QNetworkReply):
        self._pending.pop(url, None)
        data = b""
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.read(MAX_IMAGE_BYTES + 1).data()
        if not data or len(data) > MAX_IMAGE_BYTES or not looks_like_image(data):
            self._failed.add(url)  # the cover loads straight from the internet, as before
        else:
            path = self._path(url)
            tmp = path.with_name(path.name + ".part")
            try:
                tmp.write_bytes(data)
                os.replace(tmp, path)
                self._touched.add(path.name)
            except OSError as e:
                logger.warning("could not save a cover: %s", e)
                self._failed.add(url)
            else:
                self._saved += 1
                if self._saved % TRIM_EVERY == 0:
                    self._trim_later()
        self.stored.emit(url)

    def _trim_later(self):
        if self._ok:
            threading.Thread(target=trim, args=(self.folder, self.limit), daemon=True,
                             name="senada-image-trim").start()

    def close(self):
        for reply in list(self._pending.values()):
            reply.abort()
        self._pending.clear()
