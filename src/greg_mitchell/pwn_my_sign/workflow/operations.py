from collections.abc import Callable

from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadSettings, WorkflowKind
from greg_mitchell.pwn_my_sign.workflow.sender import SnapshotSender
from greg_mitchell.pwn_my_sign.workflow.source import ImageSource
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState


class WorkflowOperations:
    """One-shot polling and uploading with separate locks and shared image state."""

    def __init__(
        self,
        state: WorkflowState,
        source: ImageSource,
        sender: SnapshotSender,
        report: Callable[[str], None],
    ) -> None:
        self.state = state
        self._source = source
        self._sender = sender
        self._report = report

    def poll(self, settings: PollSettings) -> None:
        """Publish a complete selected image only when its bytes change."""
        with self.state.lock(WorkflowKind.POLL):
            changed = self.state.publish(self._source.image(settings))
            self._report("Published pending image." if changed else "The desired image is unchanged.")

    def upload(self, settings: UploadSettings) -> None:
        """Send one snapshot and record it only after successful transfer calls."""
        with self.state.lock(WorkflowKind.UPLOAD):
            image = self.state.pending()
            if self.state.is_sent(image):
                self._report("The latest desired image has already been sent.")
                return
            self._sender.send(image, settings, self._report)
            self.state.record_sent(image)
            self._report("Transfer calls completed; recorded the uploaded snapshot.")
