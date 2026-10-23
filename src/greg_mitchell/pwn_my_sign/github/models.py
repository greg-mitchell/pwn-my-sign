from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


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
    """Require provider data independently of any configured classification policy."""

    model_config = ConfigDict(frozen=True)

    status: Status
    components: tuple[Component, ...] = Field(min_length=1)
    incidents: tuple[Incident, ...]
    scheduled_maintenances: tuple[Maintenance, ...]

    @model_validator(mode="after")
    def validate_component_ids(self) -> Self:
        """Reject ambiguous service identities."""
        ids = tuple(component.id for component in self.components)
        if len(ids) != len(frozenset(ids)):
            raise ValueError("Component IDs must be unique.")
        return self
