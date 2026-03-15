from __future__ import annotations

from agents.state import MissionState, Notification
from agents.event_log import EventLog


def queue_notification(
    state: MissionState,
    event_log: EventLog,
    target_type: str,
    target_id: str,
    message: str,
) -> MissionState:
    state.notifications.append(
        Notification(
            target_type=target_type,
            target_id=target_id,
            message=message,
        )
    )
    event_log.add(
        "comms_agent",
        f"Drafted notification for {target_type}:{target_id}",
    )
    return state