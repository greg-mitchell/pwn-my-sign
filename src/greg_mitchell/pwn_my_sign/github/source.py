import math
from contextlib import AbstractContextManager
from typing import BinaryIO, Protocol
from urllib.request import Request, urlopen

from greg_mitchell.pwn_my_sign.github.models import Summary

SUMMARY_URL = "https://www.githubstatus.com/api/v2/summary.json"
MAX_SUMMARY_BYTES = 1024 * 1024


class SummaryOpener(Protocol):
    def __call__(self, request: Request, /, *, timeout: float) -> AbstractContextManager[BinaryIO]: ...


class GitHubSource:
    """Read bounded summary documents from an injected URL opener or binary stream."""

    def __init__(self, opener: SummaryOpener = urlopen) -> None:
        self._opener = opener

    def fetch(self, timeout: float = 15) -> Summary:
        """Fetch once with a positive finite socket timeout; close the response on all paths."""
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be positive and finite.")
        request = Request(SUMMARY_URL, headers={"Accept": "application/json"})
        with self._opener(request, timeout=timeout) as response:
            return self.read(response)

    def read(self, stream: BinaryIO) -> Summary:
        """Read and validate a complete document without consuming more than the limit plus one byte."""
        chunks: list[bytes] = []
        size = 0
        while chunk := stream.read(MAX_SUMMARY_BYTES + 1 - size):
            size += len(chunk)
            if size > MAX_SUMMARY_BYTES:
                raise ValueError(f"Summary exceeds {MAX_SUMMARY_BYTES} bytes.")
            chunks.append(chunk)
        return Summary.model_validate_json(b"".join(chunks))
