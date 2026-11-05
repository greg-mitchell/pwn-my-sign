from collections.abc import Callable
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen
from unittest.mock import MagicMock, Mock

import pytest
from click.testing import CliRunner

from greg_mitchell.pwn_my_sign.cli.mysign import main
from greg_mitchell.pwn_my_sign.cli.workflow_desktop import desktop
from greg_mitchell.pwn_my_sign.desktop.config import DesktopSettings, load_settings
from greg_mitchell.pwn_my_sign.desktop.controller import DesktopController
from greg_mitchell.pwn_my_sign.desktop.instance import DesktopInstance
from greg_mitchell.pwn_my_sign.desktop.reminders import ReminderStore
from greg_mitchell.pwn_my_sign.desktop.runtime import DesktopRuntime
from greg_mitchell.pwn_my_sign.workflow.producer import CommandProducer
from greg_mitchell.pwn_my_sign.workflow.state import WorkflowState


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "private/desktop.toml"
    path.parent.mkdir()
    path.write_text(
        'command = ["private/producer", "literal; $(argument)"]\n'
        'working_directory = ".."\n'
        'state_directory = "workflow-state"\n'
        'device = "test sign"\n'
        'interval = 30\n'
        'notification_timeout = 7\n'
    )
    return path


def test_load_settings_when_paths_relative_returns_explicit_resolved_settings(config: Path, tmp_path: Path) -> None:
    result = load_settings(config)

    assert result == DesktopSettings(
        command=(str(tmp_path / "private/producer"), "literal; $(argument)"),
        working_directory=tmp_path,
        state_directory=tmp_path / "private/workflow-state",
        device="test sign",
        interval=30,
        notification_timeout=7,
    )


def test_load_settings_when_file_missing_raises_read_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "missing.toml")


def test_run_when_configured_calls_controller_factory_with_resolved_settings(config: Path, tmp_path: Path) -> None:
    create = Mock(spec=Callable, return_value=Mock(spec=DesktopController))

    DesktopRuntime(create).run(config)

    create.assert_called_once_with(
        DesktopSettings(
            command=(str(tmp_path / "private/producer"), "literal; $(argument)"),
            working_directory=tmp_path,
            state_directory=tmp_path / "private/workflow-state",
            device="test sign",
            interval=30,
            notification_timeout=7,
        )
    )


def test_run_when_configured_calls_controller_with_resolved_settings(config: Path) -> None:
    controller = Mock(spec=DesktopController)

    DesktopRuntime(Mock(spec=Callable, return_value=controller)).run(config)

    controller.run.assert_called_once_with(load_settings(config))


def test_run_when_controller_fails_raises_error(config: Path) -> None:
    controller = Mock(spec=DesktopController, **{"run.side_effect": OSError("Cannot start controller")})

    with pytest.raises(OSError, match="Cannot start controller"):
        DesktopRuntime(Mock(spec=Callable, return_value=controller)).run(config)


def test_command_producer_when_working_directory_configured_calls_spawn_with_explicit_cwd(tmp_path: Path) -> None:
    process = MagicMock(spec=Popen)
    process.__enter__.return_value = process
    process.communicate.return_value = (b"producer image", None)
    process.returncode = 0
    spawn = Mock(spec=Callable, return_value=process)

    CommandProducer(spawn=spawn, cwd=tmp_path).run(("/absolute/producer", "literal arg"))

    spawn.assert_called_once_with(
        ("/absolute/producer", "literal arg"), stdin=DEVNULL, stdout=PIPE, start_new_session=True, cwd=tmp_path
    )


def test_fingerprint_when_no_history_returns_none(tmp_path: Path) -> None:
    result = ReminderStore(tmp_path).fingerprint()

    assert result is None


def test_remember_when_submission_accepted_returns_persisted_fingerprint(tmp_path: Path) -> None:
    store = ReminderStore(tmp_path)

    store.remember("a" * 64)

    assert ReminderStore(tmp_path).fingerprint() == "a" * 64


def test_remember_when_cleared_returns_no_fingerprint(tmp_path: Path) -> None:
    store = ReminderStore(tmp_path)
    store.remember("a" * 64)

    store.remember(None)

    assert store.fingerprint() is None


def test_remember_when_unchanged_calls_no_replacement(tmp_path: Path) -> None:
    ReminderStore(tmp_path).remember("a" * 64)
    replace = Mock(spec=Callable)

    ReminderStore(tmp_path, replace=replace).remember("a" * 64)

    replace.assert_not_called()


def test_remember_when_replacement_fails_returns_previous_history(tmp_path: Path) -> None:
    ReminderStore(tmp_path).remember("a" * 64)
    store = ReminderStore(tmp_path, replace=Mock(spec=Callable, side_effect=OSError("Rename failed")))

    with pytest.raises(OSError, match="Rename failed"):
        store.remember("b" * 64)

    assert ReminderStore(tmp_path).fingerprint() == "a" * 64


def test_remember_when_replacement_fails_returns_directory_without_temporary_file(tmp_path: Path) -> None:
    store = ReminderStore(tmp_path, replace=Mock(spec=Callable, side_effect=OSError("Rename failed")))

    with pytest.raises(OSError, match="Rename failed"):
        store.remember("b" * 64)

    assert list(tmp_path.glob(".desktop-reminder.*")) == []


def test_fingerprint_when_history_unreadable_raises_error(tmp_path: Path) -> None:
    (tmp_path / "desktop-reminder.json").mkdir()

    with pytest.raises(OSError):
        ReminderStore(tmp_path).fingerprint()


def test_hold_when_acquired_returns_held_instance_lock(tmp_path: Path) -> None:
    instance = DesktopInstance(WorkflowState(tmp_path))

    with instance.hold():
        held = (tmp_path / "desktop.lock/pid").is_file()

    assert held


def test_hold_when_context_exits_returns_released_instance_lock(tmp_path: Path) -> None:
    instance = DesktopInstance(WorkflowState(tmp_path))

    with instance.hold():
        pass

    assert not (tmp_path / "desktop.lock").exists()


def test_hold_when_previous_instance_unwinds_calls_pause_before_acquisition(tmp_path: Path) -> None:
    lock = tmp_path / "desktop.lock"
    lock.mkdir()
    pause = Mock(spec=Callable, side_effect=lambda timeout: lock.rmdir())
    instance = DesktopInstance(WorkflowState(tmp_path), clock=lambda: 0, pause=pause)

    with instance.hold():
        pass

    pause.assert_called_once_with(0.1)


def test_hold_when_contention_times_out_returns_original_lock(tmp_path: Path) -> None:
    lock = tmp_path / "desktop.lock"
    lock.mkdir()
    (lock / "pid").write_text("12345\n")
    instance = DesktopInstance(
        WorkflowState(tmp_path), clock=Mock(spec=Callable, side_effect=[0, 3]), pause=Mock(spec=Callable)
    )

    with pytest.raises(OSError, match="Cannot acquire"):
        with instance.hold():
            pass

    assert (lock / "pid").read_text() == "12345\n"


def test_hold_when_running_work_fails_calls_no_acquisition_retry(tmp_path: Path) -> None:
    pause = Mock(spec=Callable)
    instance = DesktopInstance(WorkflowState(tmp_path), pause=pause)

    with pytest.raises(OSError, match="Work failed"):
        with instance.hold():
            raise OSError("Work failed")

    pause.assert_not_called()


def test_desktop_when_config_selected_calls_injected_runtime() -> None:
    runtime = Mock(spec=DesktopRuntime)

    CliRunner().invoke(desktop, ["--config", "private/desktop.toml"], obj=runtime, catch_exceptions=False)

    runtime.run.assert_called_once_with(Path("private/desktop.toml"))


def test_mysign_when_desktop_requested_calls_registered_command() -> None:
    runtime = Mock(spec=DesktopRuntime)

    CliRunner().invoke(main, ["workflow", "desktop", "--config", "private/desktop.toml"], obj=runtime)

    runtime.run.assert_called_once_with(Path("private/desktop.toml"))


def test_desktop_when_runtime_fails_returns_error_on_stderr() -> None:
    runtime = Mock(spec=DesktopRuntime, **{"run.side_effect": OSError("Desktop state is unavailable")})

    result = CliRunner().invoke(desktop, ["--config", "private/desktop.toml"], obj=runtime)

    assert result.stderr == "Error: Desktop state is unavailable\n"


def test_desktop_when_config_missing_returns_usage_error() -> None:
    result = CliRunner().invoke(desktop, [])

    assert result.exit_code == 2


def test_desktop_when_help_requested_returns_success() -> None:
    result = CliRunner().invoke(desktop, ["--help"])

    assert result.exit_code == 0
