#!/bin/bash
set -euo pipefail

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

[[ $(uname -s) == Darwin ]] || fail 'Building My Sign requires macOS.'
command -v uv >/dev/null || fail 'Install uv: https://docs.astral.sh/uv/getting-started/installation/'
if ! command -v xcrun >/dev/null || ! xcrun --find swiftc >/dev/null 2>&1 \
    || ! xcrun --sdk macosx --show-sdk-path >/dev/null 2>&1; then
    fail 'Install Apple Command Line Tools with xcode-select --install, then retry.'
fi
for tool in codesign plutil; do
    command -v "$tool" >/dev/null || fail "Required macOS tool is unavailable: $tool"
done

checkout=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$checkout"
configuration=${MYSIGN_CONFIG:-private/desktop.toml}
output=${MYSIGN_APP:-build/macos/My Sign.app}
[[ -f "$configuration" ]] || fail "Configuration does not exist: $configuration"
configuration=$(cd "$(dirname "$configuration")" && pwd)/$(basename "$configuration")
[[ "$output" == *.app ]] || fail 'APP must end in .app.'
[[ ! -L "$output" ]] || fail 'APP must not be a symbolic link.'
[[ ! -e "$output" || -d "$output" ]] || fail "APP exists and is not a directory: $output"
mkdir -p "$(dirname "$output")"
output=$(cd "$(dirname "$output")" && pwd)/$(basename "$output")

uv sync --locked
xcrun swift build --package-path "$checkout/macos" --configuration release
binaries=$(xcrun swift build --package-path "$checkout/macos" --configuration release --show-bin-path)

staging=$(mktemp -d "$(dirname "$output")/.mysign-build.XXXXXX")
previous="$staging/previous.app"
published=false
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -e "$previous" && "$published" == false ]]; then
        if [[ -e "$output" ]] || ! mv "$previous" "$output"; then
            printf 'Previous app preserved at %s; restore it manually.\n' "$previous" >&2
            exit 1
        fi
    fi
    rm -rf "$staging"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

bundle="$staging/next.app"
mkdir -p "$bundle/Contents/MacOS"
cp "$binaries/SignDesktop" "$bundle/Contents/MacOS/SignDesktop"
cp "$checkout/macos/Info.plist" "$bundle/Contents/Info.plist"
plutil -replace MySignExecutable -string "$checkout/.venv/bin/mysign" "$bundle/Contents/Info.plist"
plutil -replace MySignConfiguration -string "$configuration" "$bundle/Contents/Info.plist"
codesign --force --sign - --timestamp=none "$bundle"
codesign --verify --strict "$bundle"

if [[ -e "$output" ]]; then
    mv "$output" "$previous"
fi
mv "$bundle" "$output"
published=true
printf 'Built %s. Open it to start the desktop workflow.\n' "$output"
