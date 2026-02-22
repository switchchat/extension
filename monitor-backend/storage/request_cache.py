"""
storage/request_cache.py
Defines the RequestCache class.
"""

import threading
import uuid
from collections import deque
from typing import Optional
from .cache_entry import CacheEntry
from datetime import datetime, timezone

class RequestCache:
    """
    Records endpoint calls in a bounded in-memory ring buffer.

    Thread-safe: uses a reentrant lock so the cache can safely be written
    from concurrent request handlers.

    Typical usage::

        cache = RequestCache(max_size=500)

        # Record a call (done by middleware)
        cache.record(
            method="POST",
            path="/api/log",
            query="",
            status_code=200,
            duration_ms=14.3,
            client_ip="127.0.0.1",
            session_id="abc-123",
        )

        # Query
        entries = cache.get_all()
        entry   = cache.get(entry_id)
        hits    = cache.filter(method="POST", path_prefix="/api/storage")
        cache.clear()
    """

    def __init__(self, max_size: int = 500) -> None:
        if max_size < 1:
            raise ValueError("max_size must be at least 1")
        self._max_size = max_size
        # deque with maxlen automatically evicts oldest entries when full
        self._buffer: deque[CacheEntry] = deque(maxlen=max_size)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buffer)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        method: str,
        path: str,
        query: str,
        status_code: int,
        duration_ms: float,
        client_ip: str,
        session_id: Optional[str] = None,
        actor_type: str = "user",
    ) -> CacheEntry:
        """Create and store a new :class:`CacheEntry`. Returns the entry."""
        normalized_actor = (actor_type or "user").strip().lower()
        if normalized_actor not in {"agent", "user"}:
            normalized_actor = "user"

        entry = CacheEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=_now_iso(),
            method=method.upper(),
            path=path,
            query=query,
            status_code=status_code,
            duration_ms=round(duration_ms, 3),
            client_ip=client_ip,
            session_id=session_id,
            actor_type=normalized_actor,
        )
        with self._lock:
            self._buffer.appendleft(entry)   # newest at index 0
        return entry

    def clear(self) -> int:
        """Remove all entries. Returns the number of entries removed."""
        with self._lock:
            count = len(self._buffer)
            self._buffer.clear()
        return count

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all(self, limit: Optional[int] = None) -> list[CacheEntry]:
        """Return entries newest-first, optionally capped at *limit*."""
        with self._lock:
            entries = list(self._buffer)
        return entries[:limit] if limit is not None else entries

    def get(self, entry_id: str) -> Optional[CacheEntry]:
        """Return the entry with the given *entry_id*, or ``None``."""
        with self._lock:
            for entry in self._buffer:
                if entry.entry_id == entry_id:
                    return entry
        return None

    def filter(
        self,
        *,
        method: Optional[str] = None,
        path_prefix: Optional[str] = None,
        status_code: Optional[int] = None,
        session_id: Optional[str] = None,
        actor_type: Optional[str] = None,  # New filter for actor type
        limit: Optional[int] = None,
    ) -> list[CacheEntry]:
        """
        Return entries matching all supplied filters, newest-first.

        Parameters
        ----------
        method:
            Exact HTTP method match (case-insensitive), e.g. ``"GET"``.
        path_prefix:
            Entries whose path starts with this string, e.g. ``"/api/storage"``.
        status_code:
            Exact HTTP status code match, e.g. ``200``.
        session_id:
            Exact session-id match.
        actor_type:
            Exact actor type match.
        limit:
            Cap the result set.
        """
        with self._lock:
            results = list(self._buffer)

        if method is not None:
            m = method.upper()
            results = [e for e in results if e.method == m]
        if path_prefix is not None:
            results = [e for e in results if e.path.startswith(path_prefix)]
        if status_code is not None:
            results = [e for e in results if e.status_code == status_code]
        if session_id is not None:
            results = [e for e in results if e.session_id == session_id]
        if actor_type is not None:
            results = [e for e in results if e.actor_type == actor_type]

        return results[:limit] if limit is not None else results

    def stats(self) -> dict:
        """Return summary statistics over all recorded entries."""
        with self._lock:
            entries = list(self._buffer)

        if not entries:
            return {
                "total": 0,
                "avg_duration_ms": None,
                "max_duration_ms": None,
                "by_method": {},
                "by_status": {},
            }

        durations = [e.duration_ms for e in entries]
        by_method: dict[str, int] = {}
        by_status: dict[str, int] = {}

        for e in entries:
            by_method[e.method] = by_method.get(e.method, 0) + 1
            key = str(e.status_code)
            by_status[key] = by_status.get(key, 0) + 1

        return {
            "total": len(entries),
            "avg_duration_ms": round(sum(durations) / len(durations), 3),
            "max_duration_ms": round(max(durations), 3),
            "by_method": by_method,
            "by_status": by_status,
        }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
