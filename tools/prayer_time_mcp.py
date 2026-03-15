from __future__ import annotations

from typing import Any
from datetime import datetime
import sys

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("rahmahops-prayer-time")

ALADHAN_BASE = "https://api.aladhan.com/v1"
DEFAULT_METHOD = 17  # JAKIM / Malaysia


def log(msg: str) -> None:
    print(f"[prayer_time_mcp] {msg}", file=sys.stderr, flush=True)


async def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def ping_prayer_tool() -> dict[str, Any]:
    """Health check for the RahmahOps prayer MCP server."""
    log("Ping tool called")
    return {"ok": True, "server": "rahmahops-prayer-time"}


@mcp.tool()
async def get_maghrib_time_by_city(
    city: str,
    country: str,
    method: int = DEFAULT_METHOD,
) -> dict[str, Any]:
    """
    Fetch today's prayer timings for a city/country and return Maghrib-focused urgency data.
    """
    log(f"Request received: city={city}, country={country}, method={method}")

    url = f"{ALADHAN_BASE}/timingsByCity"
    params = {
        "city": city,
        "country": country,
        "method": method,
    }

    data = await _get_json(url, params)
    payload = data.get("data", {})
    timings = payload.get("timings", {})
    meta = payload.get("meta", {})

    maghrib_raw = timings.get("Maghrib")
    timezone = meta.get("timezone", "Asia/Kuala_Lumpur")

    if not maghrib_raw:
        raise ValueError("Maghrib time not found in prayer API response.")

    now = datetime.now()
    maghrib_dt = datetime.strptime(maghrib_raw, "%H:%M").replace(
        year=now.year,
        month=now.month,
        day=now.day,
    )

    minutes_remaining = int((maghrib_dt - now).total_seconds() // 60)

    log(
        f"Resolved Maghrib={maghrib_raw}, timezone={timezone}, "
        f"minutes_remaining={minutes_remaining}"
    )

    return {
        "city": city,
        "country": country,
        "timezone": timezone,
        "method": method,
        "maghrib_time": maghrib_raw,
        "minutes_until_maghrib": minutes_remaining,
        "is_critical": minutes_remaining <= 30,
    }


if __name__ == "__main__":
    log("Starting prayer_time_mcp stdio server")
    mcp.run()