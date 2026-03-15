from __future__ import annotations

from pathlib import Path
from agents.mcp_clients import get_maghrib_status
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agents.state import load_mission_from_json
from agents.event_log import EventLog
from agents.orchestrator_agent import bind_runtime, run_launch_orchestrator
from agents.guard_agent import validate_mission_brief, log_mission_guardrail_result
from agents.recovery_agent import bind_recovery_runtime, run_recovery_orchestrator
from agents.recipient_agent import apply_maghrib_triage

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"
MISSION_PATH = BASE_DIR / "mock_mission.json"

app = FastAPI(title="RahmahOps")
event_log = EventLog()


def fresh_state():
    return load_mission_from_json(MISSION_PATH)


mission_state = fresh_state()
event_log.seed_bootstrap_logs()

@app.get("/")
def serve_dashboard() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")


app.mount("/app", StaticFiles(directory=APP_DIR), name="app")

@app.get("/api/bootstrap")
def get_bootstrap_data() -> dict:
    guardrail = validate_mission_brief(mission_state)

    return {
        "summary": mission_state.summary(),
        "guardrail": guardrail,
        "distribution_points": [point.model_dump() for point in mission_state.distribution_points],
        "volunteers": [volunteer.model_dump() for volunteer in mission_state.volunteers],
        "recipient_clusters": [cluster.model_dump() for cluster in mission_state.recipient_clusters],
        "route_plans": [route.model_dump() for route in mission_state.route_plans],
        "volunteer_assignments": [assignment.model_dump() for assignment in mission_state.volunteer_assignments],
        "notifications": [notification.model_dump() for notification in mission_state.notifications],
        "incidents": mission_state.incidents,
        "logs": event_log.list(),
    }


@app.post("/api/launch")
async def launch_mock_mission() -> dict:
    global mission_state
    mission_state = fresh_state()
    event_log.clear()

    guardrail = validate_mission_brief(mission_state)
    log_mission_guardrail_result(guardrail, event_log, "launch_mission")

    if not guardrail["allowed"]:
        return {
            "ok": False,
            "blocked": True,
            "guardrail": guardrail,
            "logs": event_log.list(),
        }

    try:
        bind_runtime(mission_state, event_log)

        event_log.add("orchestrator_agent", "ADK launch workflow started")

        final_summary = await run_launch_orchestrator(
            "Launch the RahmahOps mission using the loaded mission state."
        )

        if final_summary:
            event_log.add(
                "orchestrator_agent",
                f"ADK final summary: {final_summary}",
            )

        event_log.add(
            "orchestrator_agent",
            "ADK mission launch completed successfully",
        )
        ok = True

    except Exception as exc:
        event_log.add(
            "orchestrator_agent",
            f"ADK mission launch failed: {exc}",
            level="ERROR",
        )
        ok = False

    return {"ok": ok, "logs": event_log.list(), "guardrail": guardrail}


@app.post("/api/reset")
def reset_demo() -> dict:
    global mission_state
    mission_state = fresh_state()
    event_log.seed_bootstrap_logs()
    return {"ok": True, "logs": event_log.list()}


@app.post("/api/incidents/volunteer-cancel")
async def trigger_volunteer_cancel() -> dict:
    global mission_state

    guardrail = validate_mission_brief(mission_state)
    log_mission_guardrail_result(guardrail, event_log, "volunteer_cancel_incident")

    if not guardrail["allowed"]:
        return {
            "ok": False,
            "blocked": True,
            "guardrail": guardrail,
            "logs": event_log.list(),
        }

    try:
        if not mission_state.volunteer_assignments:
            raise ValueError("Launch the mission first before triggering incidents.")

        assigned_candidates = [
            volunteer for volunteer in mission_state.volunteers
            if volunteer.status == "assigned"
        ]
        if not assigned_candidates:
            raise ValueError("No assigned volunteer is available to cancel.")

        volunteer_to_cancel = assigned_candidates[0]

        bind_recovery_runtime(mission_state, event_log)

        event_log.add(
            "orchestrator_agent",
            f"ADK recovery workflow started for volunteer {volunteer_to_cancel.name}",
            level="WARNING",
        )

        final_summary = await run_recovery_orchestrator(
            incident_type="volunteer_cancel",
            volunteer_id=volunteer_to_cancel.volunteer_id,
        )

        if final_summary:
            event_log.add(
                "orchestrator_agent",
                f"ADK recovery summary: {final_summary}",
            )

        event_log.add(
            "orchestrator_agent",
            "ADK volunteer cancellation recovery completed",
        )

        ok = True
    except Exception as exc:
        event_log.add(
            "orchestrator_agent",
            f"Volunteer cancellation flow failed: {exc}",
            level="ERROR",
        )
        ok = False

    return {"ok": ok, "logs": event_log.list(), "guardrail": guardrail}


@app.post("/api/incidents/maghrib-critical")
async def trigger_maghrib_critical() -> dict:
    global mission_state

    guardrail = validate_mission_brief(mission_state)
    log_mission_guardrail_result(guardrail, event_log, "maghrib_critical_incident")

    if not guardrail["allowed"]:
        return {
            "ok": False,
            "blocked": True,
            "guardrail": guardrail,
            "logs": event_log.list(),
        }

    try:
        if not mission_state.volunteer_assignments:
            raise ValueError("Launch the mission first before triggering incidents.")

        # External prayer MCP lookup first
        prayer_result = None
        try:
            prayer_result = await get_maghrib_status(
                mission_state.config.city,
                mission_state.config.country,
            )
            event_log.add(
                "recovery_agent",
                (
                    f"Prayer MCP lookup succeeded: Maghrib {prayer_result['maghrib_time']} "
                    f"({prayer_result['minutes_until_maghrib']} min remaining)"
                ),
                level="WARNING",
            )
        except Exception as prayer_exc:
            event_log.add(
                "recovery_agent",
                f"Prayer MCP lookup failed: {prayer_exc}. Continuing with simulated critical incident.",
                level="WARNING",
            )

        bind_recovery_runtime(mission_state, event_log)

        event_log.add(
            "orchestrator_agent",
            "ADK recovery workflow started for Maghrib-critical conditions",
            level="WARNING",
        )

        before_minutes = mission_state.config.minutes_to_maghrib
        before_incident_count = len(mission_state.incidents)

        final_summary = await run_recovery_orchestrator(
            incident_type="maghrib_critical",
        )

        triage_applied = (
            mission_state.config.minutes_to_maghrib <= 20
            and len(mission_state.incidents) > before_incident_count
            and any(
                incident.get("type") == "maghrib_critical"
                for incident in mission_state.incidents
            )
        )

        if not triage_applied:
            event_log.add(
                "orchestrator_agent",
                "ADK triage produced no state mutation; applying deterministic triage fallback",
                level="WARNING",
            )
            apply_maghrib_triage(mission_state, event_log)

        if final_summary:
            event_log.add(
                "orchestrator_agent",
                f"ADK recovery summary: {final_summary}",
            )

        event_log.add(
            "orchestrator_agent",
            f"ADK Maghrib-critical recovery completed ({before_minutes} -> {mission_state.config.minutes_to_maghrib} minutes)",
        )

        ok = True
    except Exception as exc:
        event_log.add(
            "orchestrator_agent",
            f"Maghrib critical flow failed: {exc}",
            level="ERROR",
        )
        ok = False

    return {"ok": ok, "logs": event_log.list(), "guardrail": guardrail}