from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

BASE_DIR = Path(__file__).resolve().parent
ROUTES_MCP_PATH = BASE_DIR / "google_routes_mcp.py"


async def main():
    tools = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[str(ROUTES_MCP_PATH)],
            ),
            timeout=60,
        ),
        tool_filter=["ping_routes_tool", "compute_route_matrix_by_addresses"],
    )

    loaded_tools = await tools.get_tools()
    print("Loaded tools:", [t.name for t in loaded_tools])

    ping_tool = next(t for t in loaded_tools if t.name == "ping_routes_tool")
    route_tool = next(t for t in loaded_tools if t.name == "compute_route_matrix_by_addresses")

    ping_result = await ping_tool.run_async(args={}, tool_context=None)
    print("Ping result:", ping_result)

    route_result = await route_tool.run_async(
        args={
            "origins": [
                "UTM Skudai, Johor Bahru, Malaysia",
                "Skudai, Johor Bahru, Malaysia"
            ],
            "destinations": [
                "Masjid Al-Falah, Johor Bahru, Malaysia",
                "Taman Universiti, Johor Bahru, Malaysia"
            ]
        },
        tool_context=None,
    )
    print("Route result:", route_result)


if __name__ == "__main__":
    asyncio.run(main())