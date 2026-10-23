#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$1" >> "$FAKE_HOME/sleep-calls"
if [ "${FAKE_RESET_SOURCE:-0}" = 1 ]; then
    printf '0' > "$FAKE_HOME/source-result"
    exit 0
fi
trap '[ -d "$FAKE_STATE/watch.lock" ] && touch "$FAKE_HOME/sleep-locked-at-stop"; exit 143' TERM
exec 3<> "$FAKE_HOME/sleep-release"
touch "$FAKE_HOME/sleep-entered"
read -r ignored <&3
