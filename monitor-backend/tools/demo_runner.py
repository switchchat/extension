"""Tiny harness to inspect tool schemas and optionally run a smoke flow."""

from __future__ import annotations

import argparse
import json
from tools import BackendApiTools, AGENT_BACKEND_CONTEXT


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend tool harness")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--smoke", action="store_true", help="Run a small smoke flow")
    args = parser.parse_args()

    tools = BackendApiTools(base_url=args.base_url)

    print("=== AGENT CONTEXT ===")
    print(AGENT_BACKEND_CONTEXT)
    print("\n=== TOOL SCHEMAS ===")
    print(json.dumps(tools.tool_schemas(), indent=2))

    if args.smoke:
        print("\n=== SMOKE FLOW ===")
        print("cache_list:", tools.cache_list(limit=5))
        print("cache_stats:", tools.cache_stats())
        print("cache_filter(agent):", tools.cache_filter(actor_type="agent", limit=5))


if __name__ == "__main__":
    main()
