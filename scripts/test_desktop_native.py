"""Run native behavioral tests where the macOS frameworks are available."""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if sys.platform != 'darwin':
        print('Native desktop tests require macOS; skipped on this platform.')
        return 0
    checkout = Path(__file__).resolve().parent.parent
    compiler = Path(
        subprocess.run(
            ('/usr/bin/xcrun', '--find', 'swiftc'), check=True, capture_output=True, text=True
        ).stdout.strip()
    )
    plugin = compiler.parent.parent / 'lib/swift/host/plugins/testing/libTestingMacros.dylib'
    # Swift 6.4 command-line tools omit the built-in test macro plugin on incremental builds.
    macro_options = ('-Xswiftc', '-load-plugin-library', '-Xswiftc', str(plugin)) if plugin.is_file() else ()
    return subprocess.run(
        (
            '/usr/bin/xcrun',
            'swift',
            'test',
            '--package-path',
            str(checkout / 'macos'),
            '--scratch-path',
            str(checkout / 'private/desktop-build'),
            *macro_options,
        ),
        check=False,
    ).returncode


if __name__ == '__main__':
    raise SystemExit(main())
