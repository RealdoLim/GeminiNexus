from __future__ import annotations

from typing import Any
import os
import sys

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("rahmahops-google-routes")
ROUTES_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"


def log(msg: str) -> None:
    print(f"[google_routes_mcp] {msg}", file=sys.stderr, flush=True)


def _parse_duration_seconds(duration_str: str | None) -> int:
    if not duration_str:
        return 0
    # examples: "160s", "712s"
    return int(duration_str.rstrip("s"))


@mcp.tool()
async def ping_routes_tool() -> dict[str, Any]:
    """Health check for the RahmahOps Google Routes MCP server."""
    log("Ping tool called")
    return {"ok": True, "server": "rahmahops-google-routes"}


@mcp.tool()
async def compute_route_matrix_by_addresses(
    origins: list[str],
    destinations: list[str],
    travel_mode: str = "DRIVE",
    routing_preference: str = "TRAFFIC_AWARE",
) -> dict[str, Any]:
    """
    Compute a Google Routes route matrix using address strings.

    Args:
        origins: list of origin addresses
        destinations: list of destination addresses
        travel_mode: usually DRIVE
        routing_preference: usually TRAFFIC_AWARE
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY is missing from environment.")

    if not origins or not destinations:
        raise ValueError("origins and destinations must both be non-empty.")

    body = {
        "origins": [
            {"waypoint": {"address": origin}}
            for origin in origins
        ],
        "destinations": [
            {"waypoint": {"address": destination}}
            for destination in destinations
        ],
        "travelMode": travel_mode,
        "routingPreference": routing_preference,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,distanceMeters,duration,status,condition",
    }

    log(
        f"Calling Routes API with {len(origins)} origin(s) x {len(destinations)} destination(s)"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(ROUTES_URL, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

    matrix: list[dict[str, Any]] = []
    for item in data:
        matrix.append(
            {
                "originIndex": item.get("originIndex"),
                "destinationIndex": item.get("destinationIndex"),
                "distanceMeters": item.get("distanceMeters", 0),
                "durationSeconds": _parse_duration_seconds(item.get("duration")),
                "condition": item.get("condition", "UNKNOWN"),
                "status": item.get("status", {}),
            }
        )

    log(f"Received {len(matrix)} matrix element(s)")

    return {
        "origins": origins,
        "destinations": destinations,
        "matrix": matrix,
    }


if __name__ == "__main__":
    log("Starting google_routes_mcp stdio server")
    mcp.run()