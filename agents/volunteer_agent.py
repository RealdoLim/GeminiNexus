from __future__ import annotations

from agents.state import MissionState, VolunteerAssignment
from agents.event_log import EventLog
from agents.mcp_clients import get_route_matrix


def _proximity_score(volunteer_location: str, point_name: str, point_address: str) -> int:
    volunteer_location = volunteer_location.lower()
    haystack = f"{point_name} {point_address}".lower()

    if volunteer_location in haystack:
        return 0

    keyword_groups = {
        "jb": ["johor", "city centre", "central"],
        "skudai": ["skudai"],
        "taman universiti": ["taman universiti", "utm"],
    }

    for _, keywords in keyword_groups.items():
        if any(keyword in volunteer_location for keyword in keywords) and any(
            keyword in haystack for keyword in keywords
        ):
            return 1

    return 2


def assign_volunteers(state: MissionState, event_log: EventLog) -> MissionState:
    state.volunteer_assignments.clear()

    for volunteer in state.volunteers:
        volunteer.status = "available"
        volunteer.assigned_point_id = None

    minutes_to_maghrib = state.config.minutes_to_maghrib
    assignment_counter = 1

    available_volunteers = [
        volunteer for volunteer in state.volunteers
        if volunteer.available and volunteer.status != "cancelled"
    ]

    for route_plan in sorted(state.route_plans, key=lambda route: route.allocated_packages, reverse=True):
        point = state.get_point(route_plan.point_id)
        if point is None or route_plan.allocated_packages <= 0:
            continue

        packages_remaining = route_plan.allocated_packages

        sorted_candidates = sorted(
            available_volunteers,
            key=lambda volunteer: _proximity_score(volunteer.location, point.name, point.address),
        )

        for volunteer in sorted_candidates:
            if packages_remaining <= 0:
                continue

            effective_capacity = volunteer.vehicle_capacity * 2 if minutes_to_maghrib >= 90 else volunteer.vehicle_capacity
            if effective_capacity <= 0:
                continue

            packages_assigned = min(packages_remaining, effective_capacity)
            trips_required = 1 if packages_assigned <= volunteer.vehicle_capacity else 2

            volunteer.status = "assigned"
            volunteer.assigned_point_id = point.point_id

            state.volunteer_assignments.append(
                VolunteerAssignment(
                    assignment_id=f"a{assignment_counter}",
                    volunteer_id=volunteer.volunteer_id,
                    volunteer_name=volunteer.name,
                    point_id=point.point_id,
                    point_name=point.name,
                    packages_assigned=packages_assigned,
                    trips_required=trips_required,
                    status="assigned",
                )
            )
            assignment_counter += 1
            packages_remaining -= packages_assigned

        available_volunteers = [
            volunteer for volunteer in available_volunteers
            if volunteer.status == "available"
        ]

        if packages_remaining > 0:
            event_log.add(
                "volunteer_agent",
                f"Point {point.name} still needs support for {packages_remaining} packages",
                level="WARNING",
            )

    event_log.add(
        "volunteer_agent",
        f"Created {len(state.volunteer_assignments)} volunteer assignment records",
    )

    for assignment in state.volunteer_assignments:
        event_log.add(
            "volunteer_agent",
            (
                f"Assigned {assignment.volunteer_name} to {assignment.point_name} "
                f"for {assignment.packages_assigned} packages "
                f"({assignment.trips_required} trip(s))"
            ),
        )

    return state


async def enrich_assignments_with_route_matrix(state: MissionState, event_log: EventLog) -> MissionState:
    if not state.volunteer_assignments:
        event_log.add(
            "routing_agent",
            "Skipped route enrichment because there are no volunteer assignments yet",
            level="WARNING",
        )
        return state

    volunteer_by_id = {volunteer.volunteer_id: volunteer for volunteer in state.volunteers}
    point_by_id = {point.point_id: point for point in state.distribution_points}

    origin_index_by_volunteer: dict[str, int] = {}
    origins: list[str] = []

    destination_index_by_point: dict[str, int] = {}
    destinations: list[str] = []

    for assignment in state.volunteer_assignments:
        volunteer = volunteer_by_id.get(assignment.volunteer_id)
        point = point_by_id.get(assignment.point_id)
        if volunteer is None or point is None:
            continue

        if assignment.volunteer_id not in origin_index_by_volunteer:
            origin_index_by_volunteer[assignment.volunteer_id] = len(origins)
            origins.append(f"{volunteer.location}, {state.config.city}, {state.config.country}")

        if assignment.point_id not in destination_index_by_point:
            destination_index_by_point[assignment.point_id] = len(destinations)
            destinations.append(f"{point.name}, {point.address}, {state.config.city}, {state.config.country}")

    matrix_payload = await get_route_matrix(origins=origins, destinations=destinations)
    matrix_items = matrix_payload.get("matrix", [])

    lookup: dict[tuple[int, int], dict] = {}
    for item in matrix_items:
        key = (item.get("originIndex"), item.get("destinationIndex"))
        lookup[key] = item

    enriched_count = 0

    for assignment in state.volunteer_assignments:
        origin_index = origin_index_by_volunteer.get(assignment.volunteer_id)
        destination_index = destination_index_by_point.get(assignment.point_id)
        if origin_index is None or destination_index is None:
            continue

        item = lookup.get((origin_index, destination_index))
        if not item:
            continue

        assignment.distance_meters = item.get("distanceMeters")
        assignment.duration_seconds = item.get("durationSeconds")
        enriched_count += 1

    event_log.add(
        "routing_agent",
        (
            f"Google Routes MCP enriched {enriched_count} assignment(s) "
            f"with live distance/time data"
        ),
    )

    return state