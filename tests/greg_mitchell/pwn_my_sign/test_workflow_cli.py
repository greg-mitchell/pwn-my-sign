import signal
from contextlib import chdir
from pathlib import Path
from unittest.mock import Mock, call

import click
import pytest
from click.testing import CliRunner

from greg_mitchell.pwn_my_sign.cli.mysign import main as mysign
from greg_mitchell.pwn_my_sign.cli.workflow_poll import poll
from greg_mitchell.pwn_my_sign.cli.workflow_runtime import interruption_handlers, report, workflow
from greg_mitchell.pwn_my_sign.cli.workflow_upload import upload
from greg_mitchell.pwn_my_sign.cli.workflow_watch import watch
from greg_mitchell.pwn_my_sign.workflow.models import PollSettings, UploadSettings, WatchSettings
from greg_mitchell.pwn_my_sign.workflow.operations import WorkflowOperations
from greg_mitchell.pwn_my_sign.workflow.watch import Watcher


def test_poll_when_options_selected_calls_workflow_with_settings() -> None:
    operations = Mock(spec=WorkflowOperations)

    CliRunner().invoke(
        poll,
        ["--state", "state", "--image", "image with spaces.png"],
        obj=operations,
        catch_exceptions=False,
    )

    operations.poll.assert_called_once_with(PollSettings(image_path=Path("image with spaces.png")))


def test_poll_when_state_omitted_calls_workflow_with_settings() -> None:
    operations = Mock(spec=WorkflowOperations)

    CliRunner().invoke(poll, ["--image", "card.png"], obj=operations, catch_exceptions=False)

    operations.poll.assert_called_once_with(PollSettings(image_path=Path("card.png")))


def test_upload_when_state_omitted_calls_workflow_with_settings() -> None:
    operations = Mock(spec=WorkflowOperations)

    CliRunner().invoke(upload, ["--device", "test sign"], obj=operations, catch_exceptions=False)

    operations.upload.assert_called_once_with(UploadSettings(device="test sign"))


def test_watch_when_state_omitted_calls_watcher_with_settings() -> None:
    watcher = Mock(spec=Watcher)

    CliRunner().invoke(watch, ["--device", "test sign", "--", "producer"], obj=watcher, catch_exceptions=False)

    watcher.run.assert_called_once_with(
        WatchSettings(poll=PollSettings(command=("producer",)), upload=UploadSettings(device="test sign"))
    )


def test_poll_when_state_omitted_returns_pending_image_in_xdg_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state-home"))
    image_path = Path("tests/fixtures/cards/title-only.png").resolve()
    runner = CliRunner()

    with chdir(tmp_path):
        runner.invoke(poll, ["--image", str(image_path)], catch_exceptions=False)

    assert (tmp_path / "state-home/pwn-my-sign/display/pending.png").read_bytes() == image_path.read_bytes()


def test_poll_when_state_uses_home_returns_pending_image_in_expanded_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    image_path = Path("tests/fixtures/cards/title-only.png").resolve()
    runner = CliRunner()

    with chdir(tmp_path):
        runner.invoke(poll, ["--state", "~/sign-state", "--image", str(image_path)], catch_exceptions=False)

    assert (tmp_path / "home/sign-state/pending.png").read_bytes() == image_path.read_bytes()


@pytest.mark.parametrize(
    ("command", "arguments", "lock"),
    [
        (poll, ["--image", "unused.png"], "poll.lock"),
        (upload, ["--device", "test sign"], "upload.lock"),
        (watch, ["--device", "test sign", "--", "unused-producer"], "watch.lock"),
    ],
)
@pytest.mark.parametrize("state_option", [None, "~/sign-state", "relative-state"])
def test_command_when_state_directory_locked_returns_selected_directory_diagnostic(
    command: click.Command,
    arguments: list[str],
    lock: str,
    state_option: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state-home"))
    selected = {
        None: tmp_path / "state-home/pwn-my-sign/display",
        "~/sign-state": tmp_path / "home/sign-state",
        "relative-state": Path("relative-state"),
    }[state_option]
    (tmp_path / selected / lock).mkdir(parents=True)
    options = ["--state", state_option] if state_option is not None else []

    with chdir(tmp_path):
        result = CliRunner().invoke(command, [*options, *arguments], catch_exceptions=False)

    assert result.stderr == f"Error: Cannot acquire {selected / lock}; another workflow may be running.\n"


def test_poll_when_producer_selected_calls_workflow_with_literal_arguments() -> None:
    operations = Mock(spec=WorkflowOperations)

    CliRunner().invoke(
        poll,
        ["--state", "state", "--", "producer with spaces", "--title", "a; $(literal)"],
        obj=operations,
        catch_exceptions=False,
    )

    operations.poll.assert_called_once_with(PollSettings(command=("producer with spaces", "--title", "a; $(literal)")))


@pytest.mark.parametrize("arguments", [[], ["--image", "card.png", "--", "producer"]])
def test_poll_when_source_ambiguous_or_missing_returns_usage_error(arguments: list[str]) -> None:
    result = CliRunner().invoke(poll, ["--state", "state", *arguments])

    assert result.exit_code == 2


def test_upload_when_device_selected_calls_workflow_with_settings() -> None:
    operations = Mock(spec=WorkflowOperations)

    CliRunner().invoke(upload, ["--state", "state", "--device", "test sign"], obj=operations, catch_exceptions=False)

    operations.upload.assert_called_once_with(UploadSettings(device="test sign"))


def test_watch_when_options_selected_calls_watcher_with_settings() -> None:
    watcher = Mock(spec=Watcher)

    CliRunner().invoke(
        watch,
        [
            "--state",
            "state",
            "--device",
            "test sign",
            "--interval",
            "7",
            "--",
            "producer with spaces",
            "--caption",
            "example image",
        ],
        obj=watcher,
        catch_exceptions=False,
    )

    watcher.run.assert_called_once_with(
        WatchSettings(
            poll=PollSettings(command=("producer with spaces", "--caption", "example image")),
            upload=UploadSettings(device="test sign"),
            interval=7,
        )
    )


def test_watch_when_interval_omitted_calls_watcher_with_default() -> None:
    watcher = Mock(spec=Watcher)

    CliRunner().invoke(
        watch, ["--state", "state", "--device", "test sign", "--", "producer"], obj=watcher, catch_exceptions=False
    )

    assert watcher.run.call_args.args[0].interval == 300


@pytest.mark.parametrize("interval", ["0", "-1", "1.5", "junk", ""])
def test_watch_when_interval_invalid_calls_no_watcher(interval: str) -> None:
    watcher = Mock(spec=Watcher)

    CliRunner().invoke(
        watch, ["--state", "state", "--device", "test sign", "--interval", interval, "--", "producer"], obj=watcher
    )

    watcher.run.assert_not_called()


@pytest.mark.parametrize("command", [poll, upload, watch])
def test_command_when_arguments_missing_returns_usage_error(command: click.Command) -> None:
    result = CliRunner().invoke(command, [])

    assert result.exit_code == 2


@pytest.mark.parametrize("command", [poll, upload, watch])
def test_command_when_help_requested_returns_success_without_io(command: click.Command) -> None:
    result = CliRunner().invoke(command, ["--help"])

    assert result.exit_code == 0


@pytest.mark.parametrize("command", [poll, upload, watch])
def test_command_when_operation_fails_returns_diagnostic_on_stderr(command: click.Command) -> None:
    operations = Mock(spec=WorkflowOperations)
    operations.poll.side_effect = OSError("operation failed")
    operations.upload.side_effect = OSError("operation failed")
    watcher = Mock(spec=Watcher, **{"run.side_effect": OSError("operation failed")})
    args = ["--state", "state"]
    if command in (upload, watch):
        args += ["--device", "test sign"]
    if command in (poll, watch):
        args += ["--", "producer"]

    result = CliRunner().invoke(command, args, obj=watcher if command is watch else operations)

    assert result.stderr == "Error: operation failed\n"


def test_report_when_called_returns_message_on_stderr() -> None:
    @click.command()
    def command() -> None:
        report("Published pending image.")

    result = CliRunner().invoke(command)

    assert result.stderr == "Published pending image.\n"


def test_workflow_when_constructed_returns_selected_state_directory(tmp_path: Path) -> None:
    result = workflow(tmp_path)

    assert result.state.directory == tmp_path


def test_mysign_when_workflow_poll_requested_calls_poller() -> None:
    operations = Mock(spec=WorkflowOperations)

    CliRunner().invoke(
        mysign,
        ["workflow", "poll", "--state", "state", "--image", "-"],
        obj=operations,
        catch_exceptions=False,
    )

    operations.poll.assert_called_once_with(PollSettings(image_path=Path("-")))


@pytest.mark.parametrize("error", [None, KeyboardInterrupt(), SystemExit(143)])
def test_interruption_handlers_when_command_exits_calls_registration_to_restore_handlers(
    error: BaseException | None,
) -> None:
    register = Mock(spec=signal.signal, return_value=signal.SIG_DFL)

    try:
        with interruption_handlers(register):
            if error is not None:
                raise error
    except (KeyboardInterrupt, SystemExit):
        pass

    assert register.call_args_list[-2:] == [call(signal.SIGINT, signal.SIG_DFL), call(signal.SIGTERM, signal.SIG_DFL)]


@pytest.mark.parametrize("number", [signal.SIGINT, signal.SIGTERM])
def test_interruption_handlers_when_signal_arrives_raises_interruption(number: signal.Signals) -> None:
    register = Mock(spec=signal.signal, return_value=signal.SIG_DFL)

    with pytest.raises(KeyboardInterrupt if number == signal.SIGINT else SystemExit):
        with interruption_handlers(register):
            register.call_args_list[0].args[1](number, None)


def test_interruption_handlers_when_interrupted_calls_registration_to_protect_cleanup() -> None:
    register = Mock(spec=signal.signal, return_value=signal.SIG_DFL)

    with pytest.raises(SystemExit):
        with interruption_handlers(register):
            register.call_args_list[0].args[1](signal.SIGTERM, None)

    assert register.call_args_list[2:4] == [call(signal.SIGINT, signal.SIG_IGN), call(signal.SIGTERM, signal.SIG_IGN)]
