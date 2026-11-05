import sys
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from greg_mitchell.pwn_my_sign.desktop.channel import MessageReader, MessageWriter
from greg_mitchell.pwn_my_sign.desktop.config import DesktopSettings, load_settings
from greg_mitchell.pwn_my_sign.desktop.controller import DesktopController
from greg_mitchell.pwn_my_sign.desktop.instance import DesktopInstance
from greg_mitchell.pwn_my_sign.desktop.reminders import ReminderStore
from greg_mitchell.pwn_my_sign.desktop.session import DesktopSession
from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.producer import CommandProducer
from greg_mitchell.pwn_my_sign.workflow.sender import SnapshotSender
from greg_mitchell.pwn_my_sign.workflow.source import ImageSource
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState


def report(message: str) -> None:
    """Keep native protocol stdout separate from human diagnostics."""
    print(message, file=sys.stderr, flush=True)


def desktop_controller(settings: DesktopSettings) -> DesktopController:
    """Wire the native pipes and existing producer/snapshot operations."""
    state = WorkflowState(settings.state_directory)
    session = DesktopSession(
        MessageReader(sys.stdin.fileno(), report), MessageWriter(sys.stdout.buffer), settings.notification_timeout
    )
    workflow = WorkflowOperations(
        state,
        ImageSource(CommandProducer(cwd=settings.working_directory), BytesIO()),
        SnapshotSender(DeviceOperations(), on_event=session.on_upload_event),
        report,
    )
    return DesktopController(workflow, session, ReminderStore(settings.state_directory), DesktopInstance(state), report)


class DesktopRuntime:
    """Load explicit desktop configuration before constructing side-effecting adapters."""

    def __init__(self, create: Callable[[DesktopSettings], DesktopController] = desktop_controller) -> None:
        self._create = create

    def run(self, config: Path) -> None:
        """Run the configured native application's Python child."""
        settings = load_settings(config)
        self._create(settings).run(settings)
