from __future__ import annotations

from pathlib import Path
from typing import Literal
import json

from pydantic import BaseModel, Field


PackageType = Literal["dry_goods", "cooked_meals", "drinks", "mixed"]
VolunteerStatus = Literal["available", "assigned", "cancelled", "offline"]
PointStatus = Literal["open", "closed", "full"]
RecipientStatus = Literal["pending", "confirmed", "collected", "uncontactable", "rescheduled"]


class PackageBatch(BaseModel):
    batch_id: str
    package_type: PackageType
    quantity: int = Field(ge=0)
    expiry_time: str
    safe: bool = True


class DistributionPoint(BaseModel):
    point_id: str
    name: str
    address: str
    capacity: int = Field(ge=0)
    assigned_packages: int = Field(default=0, ge=0)
    status: PointStatus = "open"


class Volunteer(BaseModel):
    volunteer_id: str
    name: str
    location: str
    vehicle_capacity: int = Field(ge=0)
    available: bool = True
    status: VolunteerStatus = "available"
    assigned_point_id: str | None = None


class RecipientCluster(BaseModel):
    cluster_id: str
    area_name: str
    point_id: str
    households: int = Field(ge=0)
    status: RecipientStatus = "pending"


class Notification(BaseModel):
    target_type: Literal["coordinator", "volunteer", "recipient"]
    target_id: str
    message: str


class RoutePlan(BaseModel):
    point_id: str
    point_name: str
    households: int = Field(ge=0)
    allocated_packages: int = Field(ge=0)
    status: str = "planned"


class VolunteerAssignment(BaseModel):
    assignment_id: str
    volunteer_id: str
    volunteer_name: str
    point_id: str
    point_name: str
    packages_assigned: int = Field(ge=0)
    trips_required: int = Field(ge=1)
    status: str = "assigned"
    distance_meters: int | None = None
    duration_seconds: int | None = None


class MissionConfig(BaseModel):
    city: str
    country: str
    start_time: str
    estimated_maghrib_time: str
    minutes_to_maghrib: int = Field(ge=0)


class MissionState(BaseModel):
    mission_id: str
    coordinator_name: str
    config: MissionConfig
    package_batches: list[PackageBatch]
    distribution_points: list[DistributionPoint]
    volunteers: list[Volunteer]
    recipient_clusters: list[RecipientCluster]
    notifications: list[Notification] = Field(default_factory=list)
    blocked_batch_ids: list[str] = Field(default_factory=list)
    incidents: list[dict] = Field(default_factory=list)
    route_plans: list[RoutePlan] = Field(default_factory=list)
    volunteer_assignments: list[VolunteerAssignment] = Field(default_factory=list)

    def get_point(self, point_id: str) -> DistributionPoint | None:
        return next((point for point in self.distribution_points if point.point_id == point_id), None)

    def summary(self) -> dict:
        total_packages = sum(
            batch.quantity for batch in self.package_batches
            if batch.safe and batch.batch_id not in self.blocked_batch_ids
        )
        blocked_packages = sum(
            batch.quantity for batch in self.package_batches
            if batch.batch_id in self.blocked_batch_ids
        )
        total_points = len(self.distribution_points)
        total_volunteers = len(self.volunteers)
        available_volunteers = sum(1 for volunteer in self.volunteers if volunteer.available)
        total_households = sum(cluster.households for cluster in self.recipient_clusters)
        assigned_packages = sum(point.assigned_packages for point in self.distribution_points)

        return {
            "mission_id": self.mission_id,
            "coordinator_name": self.coordinator_name,
            "city": self.config.city,
            "country": self.config.country,
            "minutes_to_maghrib": self.config.minutes_to_maghrib,
            "total_packages_safe": total_packages,
            "blocked_packages": blocked_packages,
            "total_distribution_points": total_points,
            "total_volunteers": total_volunteers,
            "available_volunteers": available_volunteers,
            "total_households": total_households,
            "assigned_packages": assigned_packages,
            "assignment_count": len(self.volunteer_assignments),
            "incident_count": len(self.incidents),
            "notification_count": len(self.notifications),
        }


def load_mission_from_json(path: str | Path) -> MissionState:
    path = Path(path)
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    return MissionState.model_validate(raw)