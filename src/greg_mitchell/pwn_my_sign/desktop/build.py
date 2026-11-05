import plistlib
import shutil
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess, run
from tempfile import TemporaryDirectory


def publish_bundle(source: Path, destination: Path) -> None:
    """Publish a completely built bundle by renaming it on the same filesystem."""
    source.rename(destination)


class DesktopAppBuilder:
    """Build a local menu application using the checkout's existing Python environment."""

    def __init__(
        self,
        execute: Callable[..., CompletedProcess[bytes]] = run,
        publish: Callable[[Path, Path], None] = publish_bundle,
    ) -> None:
        self._execute = execute
        self._publish = publish

    def build(self, checkout: Path, configuration: Path, output: Path) -> Path:
        """Stage and sign a complete bundle before replacing an existing local build."""
        checkout, configuration, output = checkout.resolve(), configuration.resolve(), output.resolve()
        executable = checkout / '.venv/bin/mysign'
        package = checkout / 'macos'
        for required in (executable, configuration, package / 'Package.swift'):
            if not required.is_file():
                raise ValueError(f'Required build input does not exist: {required}')
        if output.suffix != '.app':
            raise ValueError('The output must be an application bundle ending in .app.')
        if output.exists() and not output.is_dir():
            raise ValueError(f'The output exists and is not a directory: {output}')
        scratch = checkout / 'private/desktop-build'
        self._execute(
            (
                '/usr/bin/xcrun',
                'swift',
                'build',
                '--package-path',
                str(package),
                '--scratch-path',
                str(scratch),
                '--configuration',
                'release',
            ),
            check=True,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=output.parent, prefix='.mysign-build-') as staging:
            staged = Path(staging) / output.name
            binary_directory = staged / 'Contents/MacOS'
            binary_directory.mkdir(parents=True)
            shutil.copy2(scratch / 'release/SignDesktop', binary_directory / 'SignDesktop')
            info = {
                'CFBundleIdentifier': 'local.mysign.desktop',
                'CFBundleExecutable': 'SignDesktop',
                'CFBundleName': 'My Sign',
                'CFBundleDisplayName': 'My Sign',
                'CFBundlePackageType': 'APPL',
                'CFBundleVersion': '1',
                'CFBundleShortVersionString': '0.1',
                'LSUIElement': True,
                'LSMinimumSystemVersion': '13.0',
                'NSBluetoothAlwaysUsageDescription': 'Upload your selected image to your e-paper sign over Bluetooth.',
                'MySignExecutable': str(executable),
                'MySignConfiguration': str(configuration),
            }
            with (staged / 'Contents/Info.plist').open('wb') as stream:
                plistlib.dump(info, stream)
            self._execute(('/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', str(staged)), check=True)
            self._execute(('/usr/bin/codesign', '--verify', '--strict', str(staged)), check=True)
            backup = Path(staging) / 'previous'
            if output.exists():
                output.rename(backup)
            try:
                self._publish(staged, output)
            except OSError:
                if backup.exists():
                    backup.rename(output)
                raise
        return output
