import sys
import os
import json
import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from storage.store import FileStore
from storage.router import create_router as create_storage_router
from storage.request_cache import RequestCache
from storage.cache_router import create_cache_router

# ---------------------------------------------------------------------------
# Cactus import (graceful fallback to mock so the server can run during dev)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cactus", "python", "src"))

try:
    from cactus import cactus_init, cactus_complete, cactus_destroy
    CACTUS_AVAILABLE = True
except ImportError:
    print("Warning: Cactus library not found. Running in mock mode.")
    CACTUS_AVAILABLE = False

    def cactus_init(path):
        return "mock_model"

    def cactus_destroy(model):
        pass

    def cactus_complete(model, messages, **kwargs):
        return json.dumps({
            "function_calls": [{
                "name": "categorize_activity",
                "arguments": {
                    "category": "mock",
                    "summary": "Mock analysis – Cactus not loaded",
                    "risk_level": "low",
                },
            }],
            "total_time_ms": 0,
            "confidence": 1.0,
        })


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------
MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "cactus", "weights", "functiongemma-270m-it"
)

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "storage")

class _AppState:
    session_id: Optional[str] = None
    session_start: Optional[datetime] = None
    model: Any = None
    logs: list[dict] = []

state = _AppState()

# Shared file store – backed by monitor/storage/ on disk
file_store = FileStore(STORAGE_DIR)

# In-memory request/response cache (ring buffer, max 500 entries)
request_cache = RequestCache(max_size=500)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Cactus Monitor API",
    description="Browser-activity monitoring backend powered by FunctionGemma (on-device).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def _cache_request(request: Request, call_next):
    """Record every request/response cycle into request_cache."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    actor_type = (request.headers.get("x-actor-type") or "user").strip().lower()
    if actor_type not in {"agent", "user"}:
        actor_type = "user"

    request_cache.record(
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        status_code=response.status_code,
        duration_ms=duration_ms,
        client_ip=request.client.host if request.client else "unknown",
        session_id=state.session_id,
        actor_type=actor_type,
    )
    return response

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def require_session():
    """Raise 403 when no session is currently active."""
    if state.session_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active session. POST /api/session/start first.",
        )


# ---------------------------------------------------------------------------
# Storage router  (session-gated)
# ---------------------------------------------------------------------------
app.include_router(create_storage_router(file_store, require_session))

# ---------------------------------------------------------------------------
# Cache router  (session-gated)
# ---------------------------------------------------------------------------
app.include_router(create_cache_router(request_cache, require_session))

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class LogEntry(BaseModel):
    timestamp: str
    type: str
    url: str
    details: dict = {}


class SessionStartRequest(BaseModel):
    label: Optional[str] = None  # optional human-readable label for the session


class SessionInfo(BaseModel):
    session_id: str
    started_at: str
    label: Optional[str]


# ---------------------------------------------------------------------------
# Session endpoints  (always available)
# ---------------------------------------------------------------------------

@app.post(
    "/api/session/start",
    response_model=SessionInfo,
    summary="Start a new monitoring session",
    tags=["Session"],
)
def start_session(body: SessionStartRequest = SessionStartRequest()):
    """
    Starts a new session and loads the on-device model.
    If a session is already active it is ended first.
    """
    if state.session_id is not None:
        _end_session_internal()

    state.session_id = str(uuid.uuid4())
    state.session_start = datetime.now(timezone.utc)
    state.logs = []

    # Load model
    if CACTUS_AVAILABLE:
        logger.info("Loading FunctionGemma from %s …", MODEL_PATH)
        try:
            state.model = cactus_init(MODEL_PATH)
            logger.info("Model loaded successfully.")
        except Exception as exc:
            logger.warning("Failed to load model: %s", exc)
            state.model = None
    else:
        state.model = cactus_init(MODEL_PATH)  # returns mock handle

    logger.info("Session started: %s (label=%s)", state.session_id, body.label)
    return SessionInfo(
        session_id=state.session_id,
        started_at=state.session_start.isoformat(),
        label=body.label,
    )


@app.post(
    "/api/session/end",
    summary="End the current monitoring session",
    tags=["Session"],
    dependencies=[Depends(require_session)],
)
def end_session():
    """Ends the active session and unloads the model."""
    info = _end_session_internal()
    return {"message": "Session ended.", "session": info}


def _end_session_internal() -> dict:
    """Internal helper – tears down session state."""
    if state.model is not None and CACTUS_AVAILABLE:
        try:
            cactus_destroy(state.model)
        except Exception as exc:
            logger.warning("Error destroying model: %s", exc)
    ended_at = datetime.now(timezone.utc).isoformat()
    info = {
        "session_id": state.session_id,
        "started_at": state.session_start.isoformat() if state.session_start else None,
        "ended_at": ended_at,
        "log_count": len(state.logs),
    }
    state.session_id = None
    state.session_start = None
    state.model = None
    state.logs = []
    logger.info("Session ended: %s", info["session_id"])
    return info


# ---------------------------------------------------------------------------
# Status endpoint  (inactive without session)
# ---------------------------------------------------------------------------

@app.get(
    "/api/status",
    summary="Current session status",
    tags=["Session"],
    dependencies=[Depends(require_session)],
)
def get_status():
    """Returns information about the current session."""
    return {
        "session_id": state.session_id,
        "started_at": state.session_start.isoformat() if state.session_start else None,
        "log_count": len(state.logs),
        "model_loaded": state.model is not None,
        "cactus_available": CACTUS_AVAILABLE,
    }


# ---------------------------------------------------------------------------
# Log endpoints  (inactive without session)
# ---------------------------------------------------------------------------

@app.post(
    "/api/log",
    summary="Submit a browser interaction event",
    tags=["Logs"],
    dependencies=[Depends(require_session)],
)
def log_interaction(entry: LogEntry):
    """
    Receives a browser interaction event from the Chrome extension,
    runs on-device AI analysis, and stores the result.
    """
    logger.info("Event received: type=%s url=%s", entry.type, entry.url)
    analysis = _analyze_event(entry.model_dump())

    record = {"raw": entry.model_dump(), "analysis": analysis}
    state.logs.insert(0, record)
    if len(state.logs) > 200:
        state.logs.pop()

    return {"status": "ok", "analysis": analysis}


@app.get(
    "/api/logs",
    summary="Retrieve stored interaction logs",
    tags=["Logs"],
    dependencies=[Depends(require_session)],
)
def get_logs(limit: int = 50):
    """Returns the most recent interaction logs (newest first)."""
    return {"logs": state.logs[:limit], "total": len(state.logs)}


@app.delete(
    "/api/logs",
    summary="Clear all stored interaction logs",
    tags=["Logs"],
    dependencies=[Depends(require_session)],
)
def clear_logs():
    """Deletes all logs accumulated in the current session."""
    count = len(state.logs)
    state.logs.clear()
    return {"message": f"Cleared {count} log(s)."}


# ---------------------------------------------------------------------------
# Analysis helper
# ---------------------------------------------------------------------------

ANALYSIS_TOOLS = [
    {
        "name": "categorize_activity",
        "description": "Analyze the user interaction and categorize it.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "Coding",
                        "Social Media",
                        "News",
                        "Shopping",
                        "Productivity",
                        "Entertainment",
                        "Other",
                    ],
                    "description": "Category of the activity based on URL and interaction.",
                },
                "summary": {
                    "type": "string",
                    "description": "One-sentence summary of what the user is doing.",
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Productivity risk assessment.",
                },
            },
            "required": ["category", "summary", "risk_level"],
        },
    }
]


def _analyze_event(event_data: dict) -> Optional[dict]:
    if state.model is None:
        return {"error": "Model not loaded"}

    messages = [
        {
            "role": "system",
            "content": "You are an AI productivity monitor. Analyze the user's browser interaction.",
        },
        {"role": "user", "content": f"Analyze this event: {json.dumps(event_data)}"},
    ]

    cactus_tools = [{"type": "function", "function": t} for t in ANALYSIS_TOOLS]

    try:
        raw_str = cactus_complete(
            state.model,
            messages,
            tools=cactus_tools,
            force_tools=True,
            max_tokens=256,
            stop_sequences=["<|im_end|>", "<end_of_turn>"],
        )
        response = json.loads(raw_str)
        calls = response.get("function_calls", [])
        if calls:
            return calls[0].get("arguments", {})
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse model response: %s", exc)
        return {"error": "Invalid JSON response from model"}
    except Exception as exc:
        logger.warning("Inference error: %s", exc)
        return {"error": str(exc)}

    return None


# ---------------------------------------------------------------------------
# Health check  (always available)
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check", tags=["Meta"])
def health():
    """Always returns OK regardless of session state."""
    return {"status": "ok", "session_active": state.session_id is not None}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
