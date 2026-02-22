"""
storage/cache_router.py
FastAPI router exposing read/filter/clear endpoints for the RequestCache.

All routes are session-gated via the shared ``require_session`` dependency.

Endpoints:
  GET    /api/cache                      – list cached entries (newest first)
  GET    /api/cache/stats                – aggregate statistics
  GET    /api/cache/{entry_id}           – get a single cached entry
  GET    /api/cache/filter               – filter by method / path / status / session
  DELETE /api/cache                      – clear all cached entries
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .request_cache import RequestCache
from .cache_entry import CacheEntry


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class CacheEntryOut(BaseModel):
    entry_id: str
    timestamp: str
    method: str
    path: str
    query: str
    status_code: int
    duration_ms: float
    client_ip: str
    session_id: Optional[str] = None
    actor_type: Optional[str] = None

    @classmethod
    def from_entry(cls, e: CacheEntry) -> "CacheEntryOut":
        return cls(**e.to_dict())


class CacheListResponse(BaseModel):
    entries: list[CacheEntryOut]
    total: int
    cached: int         # total entries currently in the buffer


class CacheStatsResponse(BaseModel):
    total: int
    avg_duration_ms: Optional[float]
    max_duration_ms: Optional[float]
    by_method: dict[str, int]
    by_status: dict[str, int]


class CacheClearResponse(BaseModel):
    message: str
    cleared: int


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_cache_router(cache: RequestCache, require_session) -> APIRouter:
    """
    Return a fully-wired :class:`~fastapi.APIRouter`.

    Parameters
    ----------
    cache:
        The shared :class:`~storage.cache.RequestCache` instance.
    require_session:
        The session-guard dependency from the parent app.
    """

    router = APIRouter(
        prefix="/api/cache",
        tags=["Cache"],
        dependencies=[Depends(require_session)],
    )

    # ------------------------------------------------------------------
    # LIST – GET /api/cache
    # ------------------------------------------------------------------

    @router.get(
        "",
        response_model=CacheListResponse,
        summary="List cached request entries (newest first)",
    )
    def list_entries(
        limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
    ) -> CacheListResponse:
        """Returns the most recent *limit* request/response records."""
        entries = cache.get_all(limit=limit)
        return CacheListResponse(
            entries=[CacheEntryOut.from_entry(e) for e in entries],
            total=len(entries),
            cached=cache.size,
        )

    # ------------------------------------------------------------------
    # STATS – GET /api/cache/stats
    # ------------------------------------------------------------------

    @router.get(
        "/stats",
        response_model=CacheStatsResponse,
        summary="Aggregate statistics over all cached entries",
    )
    def get_stats() -> CacheStatsResponse:
        """Returns counts, average/max duration, breakdowns by method and status."""
        return CacheStatsResponse(**cache.stats())

    # ------------------------------------------------------------------
    # FILTER – GET /api/cache/filter
    # ------------------------------------------------------------------

    @router.get(
        "/filter",
        response_model=CacheListResponse,
        summary="Filter cached entries by method, path, status, session, or actor",
    )
    def filter_entries(
        method: Optional[str] = Query(None, description="HTTP method, e.g. GET"),
        path_prefix: Optional[str] = Query(None, description="Path prefix, e.g. /api/storage"),
        status_code: Optional[int] = Query(None, description="Exact HTTP status code"),
        session_id: Optional[str] = Query(None, description="Session UUID"),
        actor_type: Optional[str] = Query(None, description="Actor type, e.g. agent or user"),  # New query param
        limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
    ) -> CacheListResponse:
        """Returns entries matching all supplied filters, newest first."""
        entries = cache.filter(
            method=method,
            path_prefix=path_prefix,
            status_code=status_code,
            session_id=session_id,
            actor_type=actor_type,  # Pass actor_type to filter
            limit=limit,
        )
        return CacheListResponse(
            entries=[CacheEntryOut.from_entry(e) for e in entries],
            total=len(entries),
            cached=cache.size,
        )

    # ------------------------------------------------------------------
    # GET ONE – GET /api/cache/{entry_id}
    # ------------------------------------------------------------------

    @router.get(
        "/{entry_id}",
        response_model=CacheEntryOut,
        summary="Get a single cached entry by ID",
    )
    def get_entry(entry_id: str) -> CacheEntryOut:
        """Returns the cache entry with the given *entry_id*."""
        entry = cache.get(entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Cache entry '{entry_id}' not found.")
        return CacheEntryOut.from_entry(entry)

    # ------------------------------------------------------------------
    # CLEAR – DELETE /api/cache
    # ------------------------------------------------------------------

    @router.delete(
        "",
        response_model=CacheClearResponse,
        summary="Clear all cached entries",
    )
    def clear_cache() -> CacheClearResponse:
        """Removes all entries from the in-memory cache."""
        cleared = cache.clear()
        return CacheClearResponse(message=f"Cleared {cleared} cache entry/entries.", cleared=cleared)

    return router
