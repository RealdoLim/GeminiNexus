from __future__ import annotations

from agents.state import MissionState
from agents.event_log import EventLog
from agents.comms_agent import queue_notification


def _distance_priority(address: str) -> int:
    address = address.lower()

    if "city centre" in address or "central" in address:
        return 0
    if "taman universiti" in address or "utm" in address:
        return 1
    if "skudai" in address:
        return 2

    return 1


def apply_maghrib_triage(state: MissionState, event_log: EventLog) -> MissionState:
    old_minutes = state.config.minutes_to_maghrib
    state.config.minutes_to_maghrib = min(state.config.minutes_to_maghrib, 20)

    candidates = []
    for route in state.route_plans:
        if route.allocated_packages <= 0:
            continue

        point = state.get_point(route.point_id)
        if point is None:
            continue

        active_clusters = [
            cluster for cluster in state.recipient_clusters
            if cluster.point_id == route.point_id and cluster.status != "rescheduled"
        ]
        if not active_clusters:
            continue

        score = _distance_priority(point.address)
        households = sum(cluster.households for cluster in active_clusters)
        candidates.append((score, households, point, route, active_clusters))

    if not candidates:
        raise ValueError("No active route is available for triage.")

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, households, point, route, affected_clusters = candidates[0]

    freed_packages = route.allocated_packages
    rescheduled_households = 0

    for cluster in affected_clusters:
        cluster.status = "rescheduled"
        rescheduled_households += cluster.households

        queue_notification(
            state,
            event_log,
            "recipient",
            cluster.cluster_id,
            (
                f"Your collection at {point.name} has been rescheduled due to time-critical "
                f"Ramadan operations. A follow-up distribution will be arranged."
            ),
        )

    route.allocated_packages = 0
    route.status = "triaged_rescheduled"
    point.assigned_packages = max(0, point.assigned_packages - freed_packages)

    released_volunteers: list[str] = []

    for assignment in state.volunteer_assignments:
        if assignment.point_id == point.point_id and assignment.status in {"assigned", "recovery_assigned"}:
            assignment.status = "triaged"

            volunteer = next(
                (v for v in state.volunteers if v.volunteer_id == assignment.volunteer_id),
                None,
            )
            if volunteer is not None and volunteer.status != "cancelled":
                volunteer.status = "available"
                volunteer.available = True
                volunteer.assigned_point_id = None
                released_volunteers.append(volunteer.name)

    state.incidents.append(
        {
            "type": "maghrib_critical",
            "point_id": point.point_id,
            "point_name": point.name,
            "households_affected": rescheduled_households,
            "packages_deprioritized": freed_packages,
            "status": "resolved",
        }
    )

    event_log.add(
        "orchestrator_agent",
        (
            f"Maghrib threshold breached: {old_minutes} -> {state.config.minutes_to_maghrib} minutes remaining. "
            f"Triage mode activated."
        ),
        level="WARNING",
    )
    event_log.add(
        "recipient_agent",
        (
            f"Deprioritized {point.name}. Rescheduled {rescheduled_households} households "
            f"and released {freed_packages} packages from today's plan"
        ),
        level="WARNING",
    )

    if released_volunteers:
        event_log.add(
            "recipient_agent",
            f"Released volunteers from triaged point: {', '.join(released_volunteers)}",
        )

    queue_notification(
        state,
        event_log,
        "coordinator",
        "main",
        (
            f"Triage mode activated. {point.name} was deprioritized, "
            f"{rescheduled_households} households were moved to next-day follow-up."
        ),
    )

    return state