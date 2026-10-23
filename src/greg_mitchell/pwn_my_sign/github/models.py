from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

ACTIONS_ID = "br0l2tvcx85d"


class Rollup(StrEnum):
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class ComponentStatus(StrEnum):
    OPERATIONAL = "operational"
    DEGRADED_PERFORMANCE = "degraded_performance"
    PARTIAL_OUTAGE = "partial_outage"
    MAJOR_OUTAGE = "major_outage"
    UNDER_MAINTENANCE = "under_maintenance"


class IncidentStatus(StrEnum):
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    POSTMORTEM = "postmortem"


class MaintenanceStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    COMPLETED = "completed"


class Status(BaseModel):
    model_config = ConfigDict(frozen=True)

    indicator: Rollup


class Component(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    status: ComponentStatus
    showcase: StrictBool
    group: StrictBool


class Incident(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    status: IncidentStatus
    impact: Rollup


class Maintenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    status: MaintenanceStatus


class Summary(BaseModel):
    """Require the metadata needed to safely interpret either status view."""

    model_config = ConfigDict(frozen=True)

    status: Status
    components: tuple[Component, ...]
    incidents: tuple[Incident, ...]
    scheduled_maintenances: tuple[Maintenance, ...]

    @model_validator(mode="after")
    def validate_component_ids(self) -> Self:
        """Reject ambiguous services and summaries missing the known Actions service."""
        ids = tuple(component.id for component in self.components)
        if len(ids) != len(frozenset(ids)):
            raise ValueError("Component IDs must be unique.")
        if ids.count(ACTIONS_ID) != 1:
            raise ValueError("Summary must contain exactly one GitHub Actions component.")
        actions = next(component for component in self.components if component.id == ACTIONS_ID)
        if not actions.showcase or actions.group:
            raise ValueError("GitHub Actions must be a visible leaf service.")
        return self
