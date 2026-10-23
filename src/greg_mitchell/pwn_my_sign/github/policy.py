import tomllib
from enum import StrEnum
from typing import Annotated, BinaryIO, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_POLICY_BYTES = 64 * 1024
Token = Annotated[str, Field(min_length=1, pattern=r"^\S+$")]


class PolicyMode(StrEnum):
    INDICATOR = "indicator"
    SERVICES = "services"


class OutputCodes(BaseModel):
    """Distinct single-token outputs for a service policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    healthy: Token = "ok"
    degraded: Token = "degraded"
    priority_outage: Token = "actions-outage"
    widespread_outage: Token = "widespread-outage"

    @model_validator(mode="after")
    def validate_distinct_codes(self) -> Self:
        codes = (self.healthy, self.degraded, self.priority_outage, self.widespread_outage)
        if len(frozenset(codes)) != len(codes):
            raise ValueError("Output codes must be distinct.")
        return self


class StatusPolicy(BaseModel):
    """Default to GitHub's indicator; opt into configurable service classification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: PolicyMode = PolicyMode.INDICATOR
    priority_service_ids: tuple[Token, ...] = ("br0l2tvcx85d",)
    outage_threshold: Annotated[int, Field(gt=0, strict=True)] = 2
    codes: OutputCodes = Field(default_factory=OutputCodes)

    @model_validator(mode="after")
    def validate_unique_priority_ids(self) -> Self:
        if len(frozenset(self.priority_service_ids)) != len(self.priority_service_ids):
            raise ValueError("Priority service IDs must be unique.")
        return self


def read_policy(stream: BinaryIO) -> StatusPolicy:
    """Read bounded explicit TOML settings without discovering any implicit configuration."""
    chunks: list[bytes] = []
    size = 0
    while chunk := stream.read(MAX_POLICY_BYTES + 1 - size):
        size += len(chunk)
        if size > MAX_POLICY_BYTES:
            raise ValueError(f"Policy exceeds {MAX_POLICY_BYTES} bytes.")
        chunks.append(chunk)
    return StatusPolicy.model_validate(tomllib.loads(b"".join(chunks).decode("utf-8")))
