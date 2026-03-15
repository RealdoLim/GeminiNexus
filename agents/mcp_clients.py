from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

BASE_DIR = Path(__file__).resolve().parent.parent
PRAYER_MCP_PATH = BASE_DIR / "tools" / "prayer_time_mcp.py"
ROUTES_MCP_PATH = BASE_DIR / "tools" / "google_routes_mcp.py"


async def _run_stdio_mcp_tool(
    server_path: Path,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[str(server_path)],
            ),
            timeout=60,
        ),
        tool_filter=[tool_name],
    )

    tools = await toolset.get_tools()
    tool = next(t for t in tools if t.name == tool_name)

    result = await tool.run_async(args=args, tool_context=None)

    if result.get("isError"):
        message = "Unknown MCP tool error"
        content = result.get("content", [])
        if content and isinstance(content, list):
            text = content[0].get("text")
            if text:
                message = text
        raise RuntimeError(message)

    structured = result.get("structuredContent")
    if structured is None:
        raise RuntimeError(f"MCP tool {tool_name} returned no structuredContent.")

    return structured


async def get_maghrib_status(city: str, country: str, method: int = 17) -> dict[str, Any]:
    return await _run_stdio_mcp_tool(
        PRAYER_MCP_PATH,
        "get_maghrib_time_by_city",
        {
            "city": city,
            "country": country,
            "method": method,
        },
    )


async def get_route_matrix(
    origins: list[str],
    destinations: list[str],
    travel_mode: str = "DRIVE",
    routing_preference: str = "TRAFFIC_AWARE",
) -> dict[str, Any]:
    return await _run_stdio_mcp_tool(
        ROUTES_MCP_PATH,
        "compute_route_matrix_by_addresses",
        {
            "origins": origins,
            "destinations": destinations,
            "travel_mode": travel_mode,
            "routing_preference": routing_preference,
        },
    )