from collections.abc import Callable

from bleak.exc import BleakError

from greg_mitchell.pwn_my_sign.workflow.models import WatchSettings, WorkflowKind
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.terminal import InputResult, TerminalInput


class Watcher:
    """Run foreground polling with terminal reminders and explicit uploads."""

    def __init__(
        self,
        workflow: WorkflowOperations,
        terminal: TerminalInput,
        sleep: Callable[[float], None],
        report: Callable[[str], None],
    ) -> None:
        self._workflow = workflow
        self._terminal = terminal
        self._sleep = sleep
        self._report = report

    def run(self, settings: WatchSettings) -> None:
        """Poll until EOF or interruption; failed polls never offer retained images."""
        with self._workflow.state.lock(WorkflowKind.WATCH):
            while True:
                try:
                    self._workflow.poll(settings.poll)
                except (OSError, ValueError) as error:
                    self._report(f"Polling failed: {error}; retrying in {settings.interval} seconds.")
                    self._sleep(settings.interval)
                    continue
                if self._workflow.state.is_sent(self._workflow.state.pending()):
                    self._sleep(settings.interval)
                    continue
                self._report("\aPending image differs from last sent.")
                self._report("Press Enter to upload; press the sign button when the sender prompts.")
                self._report(f"Polling again in {settings.interval} seconds if no input arrives.")
                result = self._terminal.wait(settings.interval)
                if result == InputResult.EOF:
                    return
                if result == InputResult.TIMEOUT:
                    continue
                try:
                    self._workflow.upload(settings.upload)
                except (OSError, ValueError, BleakError) as error:
                    self._report(f"Upload failed: {error}; retrying after {settings.interval} seconds.")
                self._sleep(settings.interval)
