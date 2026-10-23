from io import BytesIO
from pathlib import Path

import pytest

from greg_mitchell.pwn_my_sign.github.policy import ServicePolicy, read_policy


@pytest.fixture
def service_policy_document() -> bytes:
    return Path("data/github-actions.toml").read_bytes()


@pytest.fixture
def service_policy(service_policy_document: bytes) -> ServicePolicy:
    policy = read_policy(BytesIO(service_policy_document))
    if not isinstance(policy, ServicePolicy):
        raise ValueError("The shipped Actions policy must select services mode.")
    return policy


@pytest.fixture(
    params=(
        "mode",
        "priority_service_ids",
        "outage_threshold",
        "codes",
        "healthy",
        "degraded",
        "priority_outage",
        "widespread_outage",
    )
)
def incomplete_service_policy_document(request: pytest.FixtureRequest, service_policy_document: bytes) -> bytes:
    missing = str(request.param)
    if missing == "codes":
        return service_policy_document.split(b"[codes]")[0]
    return b"\n".join(
        line for line in service_policy_document.splitlines() if not line.startswith(f"{missing} =".encode())
    )
