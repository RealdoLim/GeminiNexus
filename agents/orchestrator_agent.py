from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from agents.state import MissionState
from agents.event_log import EventLog
from agents.guard_agent import run_guard_checks
from agents.routing_agent import build_route_plan
from agents.volunteer_agent import assign_volunteers, enrich_assignments_with_route_matrix
from agents.comms_agent import queue_notification

_RUNTIME: dict[str, object] = {
    "state": None,
    "event_log": None,
}

SESSION_SERVICE = InMemorySessionService()
APP_NAME = "rahmahops_adk"
USER_ID = "rahmahops_demo_user"


def bind_runtime(state: MissionState, event_log: EventLog) -> None:
    _RUNTIME["state"] = state
    _RUNTIME["event_log"] = event_log


def _state() -> MissionState:
    state = _RUNTIME["state"]
    if not isinstance(state, MissionState):
        raise RuntimeError("Mission state is not bound.")
    return state


def _event_log() -> EventLog:
    event_log = _RUNTIME["event_log"]
    if not isinstance(event_log, EventLog):
        raise RuntimeError("Event log is not bound.")
    return event_log


def normalize_mission_tool() -> dict:
    state = _state()
    event_log = _event_log()

    batch_ids = [batch.batch_id for batch in state.package_batches]
    point_ids = [point.point_id for point in state.distribution_points]
    volunteer_ids = [volunteer.volunteer_id for volunteer in state.volunteers]
    cluster_ids = [cluster.cluster_id for cluster in state.recipient_clusters]

    if len(batch_ids) != len(set(batch_ids)):
        raise ValueError("Duplicate package batch IDs detected.")
    if len(point_ids) != len(set(point_ids)):
        raise ValueError("Duplicate distribution point IDs detected.")
    if len(volunteer_ids) != len(set(volunteer_ids)):
        raise ValueError("Duplicate volunteer IDs detected.")
    if len(cluster_ids) != len(set(cluster_ids)):
        raise ValueError("Duplicate recipient cluster IDs detected.")

    total_packages = sum(batch.quantity for batch in state.package_batches)
    total_households = sum(cluster.households for cluster in state.recipient_clusters)

    event_log.add(
        "orchestrator_agent",
        (
            f"Normalized mission payload: {len(state.package_batches)} package batches, "
            f"{len(state.distribution_points)} distribution points, "
            f"{len(state.volunteers)} volunteers, "
            f"{total_packages} packages across {total_households} households"
        ),
    )
    return {"status": "ok", "step": "mission_normalized"}


def guard_tool() -> dict:
    run_guard_checks(_state(), _event_log())
    return {"status": "ok", "step": "guard_completed"}


def routing_tool() -> dict:
    build_route_plan(_state(), _event_log())
    return {"status": "ok", "step": "routing_completed"}


def volunteer_assignment_tool() -> dict:
    assign_volunteers(_state(), _event_log())
    return {"status": "ok", "step": "volunteer_assignment_completed"}


async def route_matrix_tool() -> dict:
    state = _state()
    event_log = _event_log()

    try:
        await enrich_assignments_with_route_matrix(state, event_log)
        return {"status": "ok", "step": "route_matrix_completed"}
    except Exception as exc:
        event_log.add(
            "routing_agent",
            f"Google Routes MCP unavailable, continuing with heuristic assignments: {exc}",
            level="WARNING",
        )
        return {"status": "fallback", "step": "route_matrix_failed"}


def notify_launch_tool() -> dict:
    state = _state()
    event_log = _event_log()

    queue_notification(
        state,
        event_log,
        "coordinator",
        "main",
        (
            f"Mission launched successfully. "
            f"{len(state.volunteer_assignments)} assignments created across "
            f"{len(state.route_plans)} distribution points."
        ),
    )
    return {"status": "ok", "step": "launch_notification_completed"}


root_agent = Agent(
    name="orchestrator_agent",
    model="gemini-2.5-flash",
    description="Launches RahmahOps missions by normalizing the mission brief, checking safety, routing packages, assigning volunteers, enriching routes with MCP, and notifying the coordinator.",
    instruction="""
You are RahmahOps' central orchestrator.

Use the tools in exactly this order:
1. normalize_mission_tool
2. guard_tool
3. routing_tool
4. volunteer_assignment_tool
5. route_matrix_tool
6. notify_launch_tool

Rules:
- Never skip the guard step
- Do not invent mission data
- After all tools succeed, return a short operational summary
- If the route matrix tool fails, continue safely and mention that heuristic assignments were used
""",
    tools=[
        normalize_mission_tool,
        guard_tool,
        routing_tool,
        volunteer_assignment_tool,
        route_matrix_tool,
        notify_launch_tool,
    ],
)


async def run_launch_orchestrator(user_prompt: str) -> str:
    runner = Runner(
        agent=root_agent,
        session_service=SESSION_SERVICE,
        app_name=APP_NAME,
    )

    session = await SESSION_SERVICE.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
    )

    final_text = ""

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=Content(parts=[Part(text=user_prompt)], role="user"),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            texts = []
            for part in event.content.parts:
                text = getattr(part, "text", None)
                if text:
                    texts.append(text)
            final_text = "\n".join(texts).strip()

    return final_text