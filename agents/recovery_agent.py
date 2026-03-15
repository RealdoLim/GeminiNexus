from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agents.state import MissionState, VolunteerAssignment
from agents.event_log import EventLog
from agents.comms_agent import queue_notification
from agents.recipient_agent import apply_maghrib_triage

_RUNTIME: dict[str, object] = {
    "state": None,
    "event_log": None,
}

SESSION_SERVICE = InMemorySessionService()
APP_NAME = "rahmahops_recovery"
USER_ID = "rahmahops_demo_user"

def bind_recovery_runtime(state: MissionState, event_log: EventLog) -> None:
    _RUNTIME["state"] = state
    _RUNTIME["event_log"] = event_log


def _state() -> MissionState:
    state = _RUNTIME["state"]
    if not isinstance(state, MissionState):
        raise RuntimeError("Recovery mission state is not bound.")
    return state


def _event_log() -> EventLog:
    event_log = _RUNTIME["event_log"]
    if not isinstance(event_log, EventLog):
        raise RuntimeError("Recovery event log is not bound.")
    return event_log


def _effective_capacity(vehicle_capacity: int, minutes_to_maghrib: int) -> int:
    return vehicle_capacity * 2 if minutes_to_maghrib >= 90 else vehicle_capacity


def _current_load(state: MissionState, volunteer_id: str) -> int:
    active_statuses = {"assigned", "recovery_assigned"}
    return sum(
        assignment.packages_assigned
        for assignment in state.volunteer_assignments
        if assignment.volunteer_id == volunteer_id and assignment.status in active_statuses
    )


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


def handle_volunteer_cancellation(
    state: MissionState,
    volunteer_id: str,
    event_log: EventLog,
) -> MissionState:
    volunteer = next((v for v in state.volunteers if v.volunteer_id == volunteer_id), None)
    if volunteer is None:
        raise ValueError(f"Volunteer {volunteer_id} not found.")

    active_assignments = [
        assignment for assignment in state.volunteer_assignments
        if assignment.volunteer_id == volunteer_id and assignment.status in {"assigned", "recovery_assigned"}
    ]
    if not active_assignments:
        raise ValueError(f"Volunteer {volunteer.name} has no active assignment to cancel.")

    affected_point_id = active_assignments[0].point_id
    affected_point_name = active_assignments[0].point_name
    cancelled_packages = sum(assignment.packages_assigned for assignment in active_assignments)

    for assignment in active_assignments:
        assignment.status = "cancelled"

    volunteer.status = "cancelled"
    volunteer.available = False
    volunteer.assigned_point_id = None

    state.incidents.append(
        {
            "type": "volunteer_cancelled",
            "volunteer_id": volunteer.volunteer_id,
            "volunteer_name": volunteer.name,
            "point_id": affected_point_id,
            "point_name": affected_point_name,
            "packages_affected": cancelled_packages,
            "status": "open",
        }
    )

    event_log.add(
        "volunteer_agent",
        (
            f"Incident detected: {volunteer.name} cancelled. "
            f"{cancelled_packages} packages at {affected_point_name} affected"
        ),
        level="WARNING",
    )
    event_log.add(
        "orchestrator_agent",
        "Escalating volunteer cancellation to recovery_agent",
        level="WARNING",
    )

    point = state.get_point(affected_point_id)
    if point is None:
        raise ValueError("Affected distribution point not found.")

    candidates: list[tuple[int, int, object, int]] = []
    for candidate in state.volunteers:
        if candidate.volunteer_id == volunteer_id:
            continue
        if candidate.status == "cancelled":
            continue

        effective_capacity = _effective_capacity(candidate.vehicle_capacity, state.config.minutes_to_maghrib)
        current_load = _current_load(state, candidate.volunteer_id)
        spare_capacity = effective_capacity - current_load

        if spare_capacity <= 0:
            continue

        score = _proximity_score(candidate.location, point.name, point.address)
        candidates.append((score, -spare_capacity, candidate, spare_capacity))

    candidates.sort(key=lambda item: (item[0], item[1]))

    packages_remaining = cancelled_packages
    recovered_packages = 0

    for _, _, candidate, spare_capacity in candidates:
        if packages_remaining <= 0:
            break

        absorbed = min(spare_capacity, packages_remaining)
        if absorbed <= 0:
            continue

        state.volunteer_assignments.append(
            VolunteerAssignment(
                assignment_id=f"r{len(state.volunteer_assignments) + 1}",
                volunteer_id=candidate.volunteer_id,
                volunteer_name=candidate.name,
                point_id=point.point_id,
                point_name=point.name,
                packages_assigned=absorbed,
                trips_required=1 if absorbed <= candidate.vehicle_capacity else 2,
                status="recovery_assigned",
            )
        )

        if candidate.status == "available":
            candidate.status = "assigned"
        candidate.assigned_point_id = point.point_id

        recovered_packages += absorbed
        packages_remaining -= absorbed

        _event_log().add(
            "recovery_agent",
            f"Reassigned {absorbed} packages from {volunteer.name} to {candidate.name} for {point.name}",
        )

        queue_notification(
            state,
            event_log,
            "volunteer",
            candidate.volunteer_id,
            f"Your route has changed. Proceed to {point.name}. Absorb {absorbed} packages from the cancelled route.",
        )

    if packages_remaining > 0:
        event_log.add(
            "recovery_agent",
            f"Partial recovery only. {recovered_packages}/{cancelled_packages} packages recovered; {packages_remaining} still uncovered",
            level="WARNING",
        )
        queue_notification(
            state,
            event_log,
            "coordinator",
            "main",
            f"Partial recovery: volunteer cancellation at {point.name}. {packages_remaining} packages remain uncovered.",
        )
    else:
        event_log.add(
            "recovery_agent",
            f"Recovery successful. {cancelled_packages} packages fully re-covered at {point.name}",
        )
        queue_notification(
            state,
            event_log,
            "coordinator",
            "main",
            f"Recovery successful: volunteer cancellation at {point.name} resolved. All {cancelled_packages} affected packages were reassigned.",
        )

    queue_notification(
        state,
        event_log,
        "coordinator",
        "main",
        f"{volunteer.name} cancelled. Recovery flow completed for {affected_point_name}.",
    )

    if state.incidents:
        state.incidents[-1]["status"] = "resolved" if packages_remaining == 0 else "partial"

    return state


def inspect_volunteer_incident_tool(volunteer_id: str) -> dict:
    state = _state()
    event_log = _event_log()

    volunteer = next((v for v in state.volunteers if v.volunteer_id == volunteer_id), None)
    if volunteer is None:
        raise ValueError(f"Volunteer {volunteer_id} not found.")

    active_assignments = [
        assignment for assignment in state.volunteer_assignments
        if assignment.volunteer_id == volunteer_id and assignment.status in {"assigned", "recovery_assigned"}
    ]
    if not active_assignments:
        raise ValueError(f"Volunteer {volunteer.name} has no active assignment to inspect.")

    point_name = active_assignments[0].point_name
    packages_affected = sum(a.packages_assigned for a in active_assignments)

    event_log.add(
        "recovery_agent",
        f"ADK incident analysis: {volunteer.name} cancellation affects {packages_affected} packages at {point_name}",
    )

    return {
        "volunteer_name": volunteer.name,
        "point_name": point_name,
        "packages_affected": packages_affected,
        "status": "incident_inspected",
    }


def recover_volunteer_cancellation_tool(volunteer_id: str) -> dict:
    state = _state()
    event_log = _event_log()

    handle_volunteer_cancellation(state, volunteer_id, event_log)

    last_incident = state.incidents[-1] if state.incidents else {}
    return {
        "status": "recovery_executed",
        "incident_status": last_incident.get("status", "unknown"),
        "incident_type": last_incident.get("type", "unknown"),
    }


def inspect_time_pressure_tool() -> dict:
    state = _state()
    event_log = _event_log()

    minutes = state.config.minutes_to_maghrib
    active_assignments = sum(
        1 for assignment in state.volunteer_assignments
        if assignment.status in {"assigned", "recovery_assigned"}
    )

    event_log.add(
        "recovery_agent",
        f"Internal urgency analysis: {minutes} minutes to Maghrib, {active_assignments} active assignment(s) still in field",
        level="WARNING",
    )

    return {
        "city": state.config.city,
        "country": state.config.country,
        "minutes_to_maghrib_internal": minutes,
        "active_assignments": active_assignments,
        "status": "internal_urgency_inspected",
    }


def apply_triage_tool() -> dict:
    state = _state()
    event_log = _event_log()

    apply_maghrib_triage(state, event_log)

    last_incident = state.incidents[-1] if state.incidents else {}
    return {
        "status": "triage_executed",
        "incident_type": last_incident.get("type", "unknown"),
        "incident_status": last_incident.get("status", "unknown"),
    }


root_recovery_agent = Agent(
    name="recovery_agent",
    model="gemini-2.5-flash",
    description="Handles RahmahOps recovery scenarios including volunteer cancellations and Maghrib-critical triage.",
    instruction="""
You are RahmahOps' recovery orchestrator.

There are two supported incident types:

1. volunteer_cancel
   - Call inspect_volunteer_incident_tool
   - Call recover_volunteer_cancellation_tool
   - Return a short coordinator-facing recovery summary

2. maghrib_critical
   - Call inspect_time_pressure_tool
   - If the incident is already confirmed as critical, call apply_triage_tool
   - Return a short coordinator-facing triage summary

Rules:
- Never invent mission data
- Always inspect before acting
- For maghrib_critical, triage should be applied when the incident has been confirmed by the backend
""",
    tools=[
        inspect_volunteer_incident_tool,
        recover_volunteer_cancellation_tool,
        inspect_time_pressure_tool,
        apply_triage_tool,
    ],
)


async def run_recovery_orchestrator(incident_type: str, volunteer_id: str | None = None) -> str:
    runner = Runner(
        agent=root_recovery_agent,
        session_service=SESSION_SERVICE,
        app_name=APP_NAME,
    )

    session = await SESSION_SERVICE.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
    )

    if incident_type == "volunteer_cancel":
        if not volunteer_id:
            raise ValueError("volunteer_id is required for volunteer_cancel incident.")
        prompt = (
            f"Handle volunteer_cancel for volunteer_id={volunteer_id}. "
            f"Inspect the incident first, then execute recovery."
        )
    elif incident_type == "maghrib_critical":
        state = _state()
        prompt = (
        "A Maghrib-critical incident has already been confirmed by the backend. "
        "Inspect time pressure, then apply triage and return a concise coordinator-facing summary."
        )
    else:
        raise ValueError(f"Unsupported incident_type: {incident_type}")

    final_text = ""

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=Content(parts=[Part(text=prompt)], role="user"),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            texts = []
            for part in event.content.parts:
                text = getattr(part, "text", None)
                if text:
                    texts.append(text)
            final_text = "\n".join(texts).strip()

    return final_text