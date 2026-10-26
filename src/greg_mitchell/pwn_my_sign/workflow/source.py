from io import BytesIO

from greg_mitchell.pwn_my_sign.github.interpretation import status_code
from greg_mitchell.pwn_my_sign.github.policy import IndicatorPolicy, StatusPolicy, read_policy
from greg_mitchell.pwn_my_sign.github.source import GitHubSource
from greg_mitchell.pwn_my_sign.images.selection import ImageSelector
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings


class StatusImageSource:
    """Compose the existing status interpreter and image selector in process."""

    def __init__(self, source: GitHubSource, selector: ImageSelector) -> None:
        self._source = source
        self._selector = selector

    def image(self, settings: PollSettings) -> bytes:
        """Validate policy before fetching and select one complete PNG."""
        policy: StatusPolicy = IndicatorPolicy()
        if settings.policy_path is not None:
            with settings.policy_path.open("rb") as stream:
                policy = read_policy(stream)
        code = status_code(self._source.fetch(), policy)
        return self._selector.select(settings.map_path, BytesIO(f"{code}\n".encode()))
