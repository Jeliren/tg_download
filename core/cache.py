import threading
import time
from dataclasses import dataclass


@dataclass
class CacheEntry:
    value: object
    created_at: float


class ExpiringStore:
    """Потокобезопасное in-memory хранилище с TTL."""

    def __init__(self, ttl, *, clock=None):
        if ttl < 0:
            raise ValueError("ttl must be non-negative")

        self.ttl = ttl
        self._clock = clock or time.monotonic
        self._data = {}
        self._lock = threading.RLock()

    def set(self, key, value):
        with self._lock:
            self._cleanup_locked()
            self._data[key] = CacheEntry(value=value, created_at=self._clock())

    def get(self, key, default=None):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return default

            if self._is_expired(entry):
                self._data.pop(key, None)
                return default

            return entry.value

    def pop(self, key, default=None):
        with self._lock:
            entry = self._data.pop(key, None)
            if entry is None or self._is_expired(entry):
                return default
            return entry.value

    def contains(self, key):
        sentinel = object()
        return self.get(key, sentinel) is not sentinel

    def cleanup(self):
        with self._lock:
            self._cleanup_locked()

    def _cleanup_locked(self):
        expired_keys = [
            key for key, entry in self._data.items() if self._is_expired(entry)
        ]
        for key in expired_keys:
            self._data.pop(key, None)

    def _is_expired(self, entry):
        return (self._clock() - entry.created_at) > self.ttl
