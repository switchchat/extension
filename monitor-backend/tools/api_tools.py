"""Agent-facing tool wrappers for backend API endpoints."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class BackendApiTools:
    """Tool registry + dispatcher for calling backend API endpoints."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public tool contract
    # ------------------------------------------------------------------

    def tool_schemas(self) -> list[dict[str, Any]]:
        """Return JSON-schema tool definitions for function-calling agents."""
        return [
            self._schema(
                "cache_list",
                "List cached endpoint calls.",
                {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                    },
                },
            ),
            self._schema("cache_stats", "Get cache statistics.", {}),
            self._schema(
                "cache_get",
                "Get one cached entry by id.",
                {
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "string"},
                    },
                    "required": ["entry_id"],
                },
            ),
            self._schema(
                "cache_filter",
                "Filter cache entries by method/path/status/session/actor.",
                {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string"},
                        "path_prefix": {"type": "string"},
                        "status_code": {"type": "integer"},
                        "session_id": {"type": "string"},
                        "actor_type": {"type": "string", "enum": ["agent", "user"]},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                    },
                },
            ),
            self._schema("cache_clear", "Clear cached endpoint calls.", {}),
        ]

    def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Dispatch a tool call by name with validated default arguments."""
        args = arguments or {}

        dispatch = {
            "cache_list": lambda a: self.cache_list(a.get("limit", 100)),
            "cache_stats": lambda a: self.cache_stats(),
            "cache_get": lambda a: self.cache_get(a.get("entry_id", "")),
            "cache_filter": lambda a: self.cache_filter(
                method=a.get("method"),
                path_prefix=a.get("path_prefix"),
                status_code=a.get("status_code"),
                session_id=a.get("session_id"),
                actor_type=a.get("actor_type"),
                limit=a.get("limit", 100),
            ),
            "cache_clear": lambda a: self.cache_clear(),
        }

        fn = dispatch.get(name)
        if fn is None:
            return {
                "ok": False,
                "status_code": 400,
                "error": f"Unknown tool: {name}",
            }
        return fn(args)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def cache_list(self, limit: int = 100) -> dict[str, Any]:
        return self._request("GET", "/api/cache", query={"limit": limit})

    def cache_stats(self) -> dict[str, Any]:
        return self._request("GET", "/api/cache/stats")

    def cache_get(self, entry_id: str) -> dict[str, Any]:
        if not entry_id:
            return {"ok": False, "status_code": 400, "error": "entry_id is required"}
        safe_id = urllib.parse.quote(entry_id, safe="")
        return self._request("GET", f"/api/cache/{safe_id}")

    def cache_filter(
        self,
        *,
        method: Optional[str] = None,
        path_prefix: Optional[str] = None,
        status_code: Optional[int] = None,
        session_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"limit": limit}
        if method is not None:
            query["method"] = method
        if path_prefix is not None:
            query["path_prefix"] = path_prefix
        if status_code is not None:
            query["status_code"] = status_code
        if session_id is not None:
            query["session_id"] = session_id
        if actor_type is not None:
            query["actor_type"] = actor_type
        return self._request("GET", "/api/cache/filter", query=query)

    def cache_clear(self) -> dict[str, Any]:
        return self._request("DELETE", "/api/cache")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _schema(self, name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters or {"type": "object", "properties": {}},
            },
        }

    def _request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if query:
            encoded = urllib.parse.urlencode(query, doseq=True)
            url = f"{self.base_url}{path}?{encoded}"
        else:
            url = f"{self.base_url}{path}"

        data: Optional[bytes] = None
        headers = {
            "Accept": "application/json",
            "X-Actor-Type": "agent",
        }

        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url=url, data=data, method=method.upper(), headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                parsed = _safe_json(raw)
                return {
                    "ok": True,
                    "status_code": response.status,
                    "data": parsed,
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8") if exc.fp else ""
            return {
                "ok": False,
                "status_code": exc.code,
                "error": _safe_json(raw),
            }
        except urllib.error.URLError as exc:
            return {
                "ok": False,
                "status_code": 0,
                "error": f"Network error: {exc.reason}",
            }


def _safe_json(text: str) -> Any:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
