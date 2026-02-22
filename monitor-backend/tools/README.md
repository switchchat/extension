# Backend Agent Tools

This folder provides agent-ready wrappers to call the backend API via tool/function calling.

## Files

- `api_tools.py` – `BackendApiTools` class with:
  - `tool_schemas()` JSON-schema function definitions for LLM tool use
  - `call_tool(name, arguments)` dispatcher
  - endpoint wrappers for cache operations only
- `context.py` – `AGENT_BACKEND_CONTEXT` prompt text for agent behavior and constraints
- `demo_runner.py` – tiny harness to print context + schemas and run optional smoke flow

## Scope

Only cache tools are exposed:

- `cache_list`
- `cache_stats`
- `cache_get`
- `cache_filter`
- `cache_clear`

Cache routes are session-gated by the backend. If you receive `403 No active session`,
the session must be started externally (outside this tool package).

## Actor differentiation

All requests from `BackendApiTools` send header:

- `X-Actor-Type: agent`

The backend middleware stores this into cache so `/api/cache/filter?actor_type=agent` can isolate agent actions.

## Quick run

```bash
python3 -m tools.demo_runner --base-url http://localhost:8000
python3 -m tools.demo_runner --base-url http://localhost:8000 --smoke
```
