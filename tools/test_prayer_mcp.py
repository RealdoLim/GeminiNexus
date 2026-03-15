from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

BASE_DIR = Path(__file__).resolve().parent
PRAYER_MCP_PATH = BASE_DIR / "prayer_time_mcp.py"


async def main():
    tools = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[str(PRAYER_MCP_PATH)],
            ),
            timeout=60,
        ),
        tool_filter=["ping_prayer_tool", "get_maghrib_time_by_city"],
    )

    loaded_tools = await tools.get_tools()
    print("Loaded tools:", [t.name for t in loaded_tools])

    ping_tool = next(t for t in loaded_tools if t.name == "ping_prayer_tool")
    prayer_tool = next(t for t in loaded_tools if t.name == "get_maghrib_time_by_city")

    ping_result = await ping_tool.run_async(args={}, tool_context=None)
    print("Ping result:", ping_result)

    prayer_result = await prayer_tool.run_async(
        args={"city": "Johor Bahru", "country": "Malaysia", "method": 17},
        tool_context=None,
    )
    print("Prayer result:", prayer_result)


if __name__ == "__main__":
    asyncio.run(main())