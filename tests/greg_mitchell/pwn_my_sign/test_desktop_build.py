import plistlib
from collections.abc import Callable
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from unittest.mock import Mock, call

import pytest

from greg_mitchell.pwn_my_sign.desktop.build import DesktopAppBuilder


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / '.venv/bin').mkdir(parents=True)
    (tmp_path / '.venv/bin/mysign').write_bytes(b'python entry point')
    (tmp_path / 'macos').mkdir()
    (tmp_path / 'macos/Package.swift').write_text('// local package')
    (tmp_path / 'private/desktop-build/release').mkdir(parents=True)
    (tmp_path / 'private/desktop-build/release/SignDesktop').write_bytes(b'native binary')
    (tmp_path / 'private/desktop.toml').write_text('device = "test sign"\n')
    return tmp_path


@pytest.fixture
def execute() -> Mock:
    return Mock(spec=Callable, return_value=CompletedProcess(args=(), returncode=0))


def test_build_when_inputs_exist_returns_executable_bundle(checkout: Path, execute: Mock) -> None:
    result = DesktopAppBuilder(execute).build(
        checkout, checkout / 'private/desktop.toml', checkout / 'private/Sign.app'
    )

    assert (result / 'Contents/MacOS/SignDesktop').read_bytes() == b'native binary'


@pytest.mark.parametrize(
    ('key', 'value'),
    [
        ('CFBundleIdentifier', 'local.mysign.desktop'),
        ('LSUIElement', True),
        ('NSBluetoothAlwaysUsageDescription', 'Upload your selected image to your e-paper sign over Bluetooth.'),
    ],
)
def test_build_when_inputs_exist_returns_permission_metadata(
    checkout: Path, execute: Mock, key: str, value: object
) -> None:
    result = DesktopAppBuilder(execute).build(
        checkout, checkout / 'private/desktop.toml', checkout / 'private/Sign.app'
    )

    assert plistlib.loads((result / 'Contents/Info.plist').read_bytes())[key] == value


@pytest.mark.parametrize(
    ('key', 'path'), [('MySignExecutable', '.venv/bin/mysign'), ('MySignConfiguration', 'private/desktop.toml')]
)
def test_build_when_inputs_exist_returns_absolute_runtime_paths(
    checkout: Path, execute: Mock, key: str, path: str
) -> None:
    result = DesktopAppBuilder(execute).build(
        checkout, checkout / 'private/desktop.toml', checkout / 'private/Sign.app'
    )

    assert plistlib.loads((result / 'Contents/Info.plist').read_bytes())[key] == str(checkout / path)


def test_build_when_inputs_exist_calls_local_compiler(checkout: Path, execute: Mock) -> None:
    DesktopAppBuilder(execute).build(checkout, checkout / 'private/desktop.toml', checkout / 'private/Sign.app')

    assert execute.call_args_list[0] == call(
        (
            '/usr/bin/xcrun',
            'swift',
            'build',
            '--package-path',
            str(checkout / 'macos'),
            '--scratch-path',
            str(checkout / 'private/desktop-build'),
            '--configuration',
            'release',
        ),
        check=True,
    )


def test_build_when_compilation_finishes_calls_local_signing_and_verification(checkout: Path, execute: Mock) -> None:
    DesktopAppBuilder(execute).build(checkout, checkout / 'private/desktop.toml', checkout / 'private/Sign.app')

    calls = tuple((entry.args[0][0:5], entry.kwargs) for entry in execute.call_args_list[1:])
    assert calls == (
        (('/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none'), {'check': True}),
        (
            (
                '/usr/bin/codesign',
                '--verify',
                '--strict',
                execute.call_args_list[1].args[0][-1],
            ),
            {'check': True},
        ),
    )


@pytest.mark.parametrize('missing', ['.venv/bin/mysign', 'private/desktop.toml', 'macos/Package.swift'])
def test_build_when_input_missing_calls_no_compiler(checkout: Path, execute: Mock, missing: str) -> None:
    (checkout / missing).unlink()

    with pytest.raises(ValueError, match='Required build input'):
        DesktopAppBuilder(execute).build(checkout, checkout / 'private/desktop.toml', checkout / 'private/Sign.app')

    execute.assert_not_called()


def test_build_when_output_is_not_app_calls_no_compiler(checkout: Path, execute: Mock) -> None:
    with pytest.raises(ValueError, match='ending in .app'):
        DesktopAppBuilder(execute).build(checkout, checkout / 'private/desktop.toml', checkout / 'private/output')

    execute.assert_not_called()


@pytest.mark.parametrize('failure_at', [0, 1, 2])
def test_build_when_tool_fails_returns_previous_bundle(checkout: Path, execute: Mock, failure_at: int) -> None:
    output = checkout / 'private/Sign.app'
    output.mkdir()
    (output / 'previous').write_bytes(b'previous application')
    execute.side_effect = [None] * failure_at + [CalledProcessError(1, 'build tool')]

    with pytest.raises(CalledProcessError):
        DesktopAppBuilder(execute).build(checkout, checkout / 'private/desktop.toml', output)

    assert (output / 'previous').read_bytes() == b'previous application'


def test_build_when_rebuilding_returns_replacement_bundle(checkout: Path, execute: Mock) -> None:
    output = checkout / 'private/Sign.app'
    output.mkdir()
    (output / 'previous').write_bytes(b'previous application')

    result = DesktopAppBuilder(execute).build(checkout, checkout / 'private/desktop.toml', output)

    assert tuple(path.name for path in result.iterdir()) == ('Contents',)


def test_build_when_publication_fails_returns_previous_bundle(checkout: Path, execute: Mock) -> None:
    output = checkout / 'private/Sign.app'
    output.mkdir()
    (output / 'previous').write_bytes(b'previous application')
    publish = Mock(spec=Callable, side_effect=OSError('publication failed'))

    with pytest.raises(OSError, match='publication failed'):
        DesktopAppBuilder(execute, publish).build(checkout, checkout / 'private/desktop.toml', output)

    assert (output / 'previous').read_bytes() == b'previous application'


def test_build_when_signed_calls_publisher_with_complete_staged_bundle(checkout: Path, execute: Mock) -> None:
    observed: list[bytes] = []

    def publish(source: Path, destination: Path) -> None:
        observed.append((source / 'Contents/MacOS/SignDesktop').read_bytes())
        source.rename(destination)

    DesktopAppBuilder(execute, publish).build(
        checkout, checkout / 'private/desktop.toml', checkout / 'private/Sign.app'
    )

    assert observed == [b'native binary']


def test_build_when_rebuilding_previous_named_app_returns_replacement_bundle(checkout: Path, execute: Mock) -> None:
    output = checkout / 'private/previous.app'
    output.mkdir()
    (output / 'old').write_bytes(b'previous application')

    result = DesktopAppBuilder(execute).build(checkout, checkout / 'private/desktop.toml', output)

    assert (result / 'Contents/MacOS/SignDesktop').read_bytes() == b'native binary'
