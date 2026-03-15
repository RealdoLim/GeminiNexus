from __future__ import annotations

import json
from datetime import datetime

from agents.state import MissionState
from agents.event_log import EventLog


SUSPICIOUS_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "reveal your system prompt",
    "show your system prompt",
    "show me the prompt",
    "developer message",
    "hidden prompt",
    "bypass safety",
    "disable guardrails",
    "ignore guardrails",
    "print environment variables",
    "reveal api key",
    "show api key",
    "dump secrets",
]

DISCRIMINATION_PATTERNS = [
    "only serve one race",
    "exclude non",
    "exclude christian",
    "exclude hindu",
    "exclude chinese",
    "exclude malay",
    "exclude indian",
    "prioritize one ethnicity",
    "do not serve",
]


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def validate_mission_brief(state: MissionState) -> dict:
    categories: list[str] = []

    if not state.package_batches:
        categories.append("missing_package_batches")
    if not state.distribution_points:
        categories.append("missing_distribution_points")
    if not state.volunteers:
        categories.append("missing_volunteers")
    if not state.recipient_clusters:
        categories.append("missing_recipient_clusters")

    safe_packages = sum(
        batch.quantity for batch in state.package_batches
        if batch.safe and batch.batch_id not in state.blocked_batch_ids
    )
    if safe_packages <= 0:
        categories.append("no_safe_packages")

    total_point_capacity = sum(point.capacity for point in state.distribution_points)
    if total_point_capacity <= 0:
        categories.append("invalid_distribution_capacity")

    total_vehicle_capacity = sum(vol.vehicle_capacity for vol in state.volunteers if vol.available)
    if total_vehicle_capacity <= 0:
        categories.append("no_transport_capacity")

    point_ids = {point.point_id for point in state.distribution_points}
    for cluster in state.recipient_clusters:
        if cluster.point_id not in point_ids:
            categories.append("recipient_cluster_with_unknown_point")
            break

    if state.config.minutes_to_maghrib < 0:
        categories.append("invalid_time_window")

    mission_blob = _normalize(json.dumps(state.model_dump(), ensure_ascii=False))

    if any(pattern in mission_blob for pattern in SUSPICIOUS_PATTERNS):
        categories.append("prompt_injection_or_secret_exfiltration")

    if any(pattern in mission_blob for pattern in DISCRIMINATION_PATTERNS):
        categories.append("discriminatory_request")

    allowed = len(categories) == 0
    safe_message = (
        "Mission brief validation passed."
        if allowed
        else "Mission brief blocked due to: " + ", ".join(categories)
    )

    return {
        "allowed": allowed,
        "categories": categories,
        "safe_message": safe_message,
    }


def log_mission_guardrail_result(result: dict, event_log: EventLog, action_name: str) -> None:
    if result["allowed"]:
        event_log.add(
            "guard_agent",
            f"Mission validation passed for action '{action_name}'",
        )
    else:
        event_log.add(
            "guard_agent",
            (
                f"Mission validation blocked action '{action_name}' due to "
                f"{', '.join(result['categories'])}"
            ),
            level="WARNING",
        )


def run_guard_checks(state: MissionState, event_log: EventLog) -> MissionState:
    mission_start = datetime.fromisoformat(state.config.start_time)
    state.blocked_batch_ids.clear()

    for batch in state.package_batches:
        expiry_time = datetime.fromisoformat(batch.expiry_time)
        if not batch.safe or expiry_time <= mission_start:
            state.blocked_batch_ids.append(batch.batch_id)
            event_log.add(
                "guard_agent",
                f"Blocked unsafe batch {batch.batch_id} from distribution",
                level="WARNING",
            )

    safe_packages = sum(
        batch.quantity for batch in state.package_batches
        if batch.batch_id not in state.blocked_batch_ids and batch.safe
    )

    if safe_packages <= 0:
        raise ValueError("No safe food packages remain after guard checks.")

    event_log.add(
        "guard_agent",
        f"Safety and privacy checks passed. Safe packages available: {safe_packages}",
    )

    return state