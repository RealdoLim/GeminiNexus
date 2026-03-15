from __future__ import annotations

from datetime import datetime
from threading import Lock


class EventLog:
    def __init__(self) -> None:
        self._events: list[dict] = []
        self._lock = Lock()

    def add(
        self,
        agent: str,
        message: str,
        level: str = "INFO",
        details: dict | None = None,
    ) -> dict:
        event = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": agent,
            "level": level,
            "message": message,
            "details": details or {},
        }
        with self._lock:
            self._events.append(event)
        return event

    def list(self) -> list[dict]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def seed_bootstrap_logs(self) -> None:
        self.clear()
        self.add("system", "RahmahOps dashboard initialized")
        self.add("orchestrator_agent", "Mission state loaded and awaiting launch")
        self.add("intake_agent", "Coordinator briefing queued for parsing")
        self.add("guard_agent", "Safety and privacy checks standing by")