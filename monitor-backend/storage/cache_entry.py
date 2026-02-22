"""
storage/cache_entry.py
Defines the CacheEntry dataclass.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Literal

@dataclass
class CacheEntry:
    """Immutable record of a single HTTP request/response cycle."""

    entry_id: str
    timestamp: str          # ISO-8601 UTC, set when the request arrives
    method: str             # HTTP method (GET, POST, …)
    path: str               # URL path, e.g. /api/session/start
    query: str              # raw query string, may be empty
    status_code: int        # HTTP response status code
    duration_ms: float      # wall-clock time to process the request
    client_ip: str          # remote client address
    session_id: Optional[str] = None   # active session at request time, if any
    actor_type: Literal['agent', 'user'] = "user"  # New field to specify actor type

    def to_dict(self) -> dict:
        return asdict(self)
