"""A dict that keeps only the most recently used entries, so caches stop growing over a long session."""

import threading
from collections import OrderedDict


class BoundedCache:
    """Keeps at most `limit` entries; reading or writing one makes it the most recent.

    Safe to use from the worker threads too (lookups run there and store what they find).
    """

    def __init__(self, limit: int):
        self.limit = limit
        self._data = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data

    def __getitem__(self, key):
        with self._lock:
            value = self._data[key]
            self._data.move_to_end(key)
            return value

    def get(self, key, default=None):
        with self._lock:
            if key not in self._data:
                return default
            self._data.move_to_end(key)
            return self._data[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            self._trim(self.limit)

    def put_many(self, items):
        """Store (key, value) pairs together; the whole batch is kept even when it is over the limit
        (a long playlist must not push out its own first songs)."""
        with self._lock:
            count = 0
            for key, value in items:
                self._data[key] = value
                self._data.move_to_end(key)
                count += 1
            self._trim(max(self.limit, count))

    def pop(self, key, default=None):
        with self._lock:
            return self._data.pop(key, default)

    def clear(self):
        with self._lock:
            self._data.clear()

    def _trim(self, keep: int):
        while len(self._data) > keep:
            self._data.popitem(last=False)
