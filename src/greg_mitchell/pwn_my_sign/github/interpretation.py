from enum import StrEnum

from greg_mitchell.pwn_my_sign.github.models import (
    ACTIONS_ID,
    ComponentStatus,
    IncidentStatus,
    MaintenanceStatus,
    Rollup,
    Summary,
)


class TeamStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ACTIONS_OUTAGE = "actions-outage"
    WIDESPREAD_OUTAGE = "widespread-outage"


def team_status(summary: Summary) -> TeamStatus:
    """Classify visible leaf services, retaining incident and maintenance signals."""
    services = tuple(component for component in summary.components if component.showcase and not component.group)
    outages = tuple(
        component
        for component in services
        if component.status in (ComponentStatus.PARTIAL_OUTAGE, ComponentStatus.MAJOR_OUTAGE)
    )
    if len(outages) >= 2:
        return TeamStatus.WIDESPREAD_OUTAGE
    if any(component.id == ACTIONS_ID for component in outages):
        return TeamStatus.ACTIONS_OUTAGE
    if (
        summary.status.indicator != Rollup.NONE
        or any(component.status != ComponentStatus.OPERATIONAL for component in services)
        or any(
            incident.status not in (IncidentStatus.RESOLVED, IncidentStatus.POSTMORTEM)
            for incident in summary.incidents
        )
        or any(
            maintenance.status in (MaintenanceStatus.IN_PROGRESS, MaintenanceStatus.VERIFYING)
            for maintenance in summary.scheduled_maintenances
        )
    ):
        return TeamStatus.DEGRADED
    return TeamStatus.OK
