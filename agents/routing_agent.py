from __future__ import annotations

from agents.state import MissionState, RoutePlan
from agents.event_log import EventLog


def build_route_plan(state: MissionState, event_log: EventLog) -> MissionState:
    state.route_plans.clear()

    for point in state.distribution_points:
        point.assigned_packages = 0
        point.status = "open"

    safe_packages = sum(
        batch.quantity for batch in state.package_batches
        if batch.safe and batch.batch_id not in state.blocked_batch_ids
    )

    households_by_point: dict[str, int] = {}
    for cluster in state.recipient_clusters:
        households_by_point.setdefault(cluster.point_id, 0)
        households_by_point[cluster.point_id] += cluster.households

    remaining_packages = safe_packages

    points_sorted = sorted(
        state.distribution_points,
        key=lambda point: households_by_point.get(point.point_id, 0),
        reverse=True,
    )

    for point in points_sorted:
        households = households_by_point.get(point.point_id, 0)
        allocation = min(point.capacity, households, remaining_packages)

        point.assigned_packages = allocation
        if allocation >= point.capacity and households > point.capacity:
            point.status = "full"

        state.route_plans.append(
            RoutePlan(
                point_id=point.point_id,
                point_name=point.name,
                households=households,
                allocated_packages=allocation,
                status="planned" if allocation > 0 else "unserved",
            )
        )

        remaining_packages -= allocation

    total_allocated = sum(plan.allocated_packages for plan in state.route_plans)
    total_households = sum(cluster.households for cluster in state.recipient_clusters)

    event_log.add(
        "routing_agent",
        (
            f"Built route plan for {len(state.route_plans)} points. "
            f"Allocated {total_allocated} packages against {total_households} households"
        ),
    )

    if remaining_packages > 0:
        event_log.add(
            "routing_agent",
            f"{remaining_packages} safe packages remain in reserve after primary allocation",
        )

    return state