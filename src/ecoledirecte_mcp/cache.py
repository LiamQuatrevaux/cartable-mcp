# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Small TTL + LRU cache for read-only API snapshots.

Ecole Directe rate-limits and rotates its token, so the MCP server serves
repeated reads (dashboard, notes, timetable, ...) from memory instead of
hitting the API again.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    """Bounded mapping with per-entry expiration (not thread-safe by design)."""

    def __init__(self, max_entries: int = 512, default_ttl: float = 60.0) -> None:
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            del self._entries[key]
            self.misses += 1
            return None
        self._entries.move_to_end(key)
        self.hits += 1
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        lifetime = self.default_ttl if ttl is None else ttl
        self._entries[key] = (time.monotonic() + lifetime, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self, prefix: str | None = None) -> None:
        if prefix is None:
            self._entries.clear()
            return
        for key in [key for key in self._entries if key.startswith(prefix)]:
            del self._entries[key]

    def stats(self) -> dict[str, int]:
        return {
            "entries": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "max_entries": self.max_entries,
        }
