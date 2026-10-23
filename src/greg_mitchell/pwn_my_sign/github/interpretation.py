from greg_mitchell.pwn_my_sign.github.models import (
    ComponentStatus,
    IncidentStatus,
    MaintenanceStatus,
    Rollup,
    Summary,
)
from greg_mitchell.pwn_my_sign.github.policy import PolicyMode, StatusPolicy


def status_code(summary: Summary, policy: StatusPolicy) -> str:
    """Return the provider indicator or apply the explicitly selected service policy."""
    if policy.mode == PolicyMode.INDICATOR:
        return summary.status.indicator
    services = tuple(component for component in summary.components if component.showcase and not component.group)
    if not services:
        raise ValueError("Service policy requires at least one visible leaf service.")
    service_ids = frozenset(component.id for component in services)
    missing = frozenset(policy.priority_service_ids) - service_ids
    if missing:
        raise ValueError(f"Priority services must exist as visible leaf services: {', '.join(sorted(missing))}.")
    outages = tuple(
        component
        for component in services
        if component.status in (ComponentStatus.PARTIAL_OUTAGE, ComponentStatus.MAJOR_OUTAGE)
    )
    if len(outages) >= policy.outage_threshold:
        return policy.codes.widespread_outage
    if any(component.id in policy.priority_service_ids for component in outages):
        return policy.codes.priority_outage
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
        return policy.codes.degraded
    return policy.codes.healthy
