#!/bin/bash
set -euo pipefail

if [[ $(uname -s) != Darwin ]]; then
    printf 'Native desktop tests require macOS; skipped on this platform.\n'
    exit 0
fi
if ! compiler=$(xcrun --find swiftc 2>/dev/null); then
    printf 'Install Apple Command Line Tools with xcode-select --install, then retry.\n' >&2
    exit 1
fi
checkout=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
plugin="$(dirname "$(dirname "$compiler")")/lib/swift/host/plugins/testing/libTestingMacros.dylib"
set -- xcrun swift test --package-path "$checkout/macos"
# Some Command Line Tools builds fail to load the Swift Testing macro plugin automatically.
if [[ -f "$plugin" ]]; then
    set -- "$@" -Xswiftc -load-plugin-library -Xswiftc "$plugin"
fi
exec "$@"
