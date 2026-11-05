from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from greg_mitchell.pwn_my_sign.cli.workflow_desktop_build import desktop_build
from greg_mitchell.pwn_my_sign.desktop.build import DesktopAppBuilder


@pytest.fixture
def configuration(tmp_path: Path) -> Path:
    path = tmp_path / 'desktop.toml'
    path.write_text(
        'command = ["./producer"]\nworking_directory = "."\nstate_directory = "state"\ndevice = "test sign"\n'
    )
    return path


@pytest.fixture
def builder() -> Mock:
    return Mock(spec=DesktopAppBuilder, **{'build.return_value': Path('/local/My Sign.app')})


def test_desktop_build_when_configured_calls_builder_with_explicit_paths(configuration: Path, builder: Mock) -> None:
    CliRunner().invoke(
        desktop_build,
        ['--config', str(configuration), '--output', 'private/My Sign.app', '--checkout', 'checkout with spaces'],
        obj=builder,
        catch_exceptions=False,
    )

    builder.build.assert_called_once_with(Path('checkout with spaces'), configuration, Path('private/My Sign.app'))


def test_desktop_build_when_checkout_omitted_calls_builder_with_current_directory(
    configuration: Path, builder: Mock
) -> None:
    CliRunner().invoke(
        desktop_build,
        ['--config', str(configuration), '--output', 'private/Sign.app'],
        obj=builder,
        catch_exceptions=False,
    )

    assert builder.build.call_args.args[0] == Path('.')


def test_desktop_build_when_successful_returns_diagnostic_on_stderr(configuration: Path, builder: Mock) -> None:
    result = CliRunner().invoke(
        desktop_build, ['--config', str(configuration), '--output', 'private/Sign.app'], obj=builder
    )

    assert result.stderr == 'Built /local/My Sign.app. Open it to start the desktop workflow.\n'


@pytest.mark.parametrize(
    'error', [OSError('compiler unavailable'), ValueError('invalid output'), CalledProcessError(1, 'swift')]
)
def test_desktop_build_when_builder_fails_returns_diagnostic(
    configuration: Path, builder: Mock, error: Exception
) -> None:
    builder.build.side_effect = error

    result = CliRunner().invoke(
        desktop_build, ['--config', str(configuration), '--output', 'private/Sign.app'], obj=builder
    )

    assert result.stderr == f'Error: {error}\n'


def test_desktop_build_when_config_missing_calls_no_builder(tmp_path: Path, builder: Mock) -> None:
    CliRunner().invoke(desktop_build, ['--config', str(tmp_path / 'missing.toml'), '--output', 'Sign.app'], obj=builder)

    builder.build.assert_not_called()


def test_desktop_build_when_help_requested_returns_success_without_build(builder: Mock) -> None:
    result = CliRunner().invoke(desktop_build, ['--help'], obj=builder)

    assert result.exit_code == 0
