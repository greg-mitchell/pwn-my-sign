from enum import StrEnum


class UploadEvent(StrEnum):
    """Validated discovery and connected transfer boundaries."""

    WAITING_FOR_BUTTON = "waiting_for_button"
    SENDING = "sending"
