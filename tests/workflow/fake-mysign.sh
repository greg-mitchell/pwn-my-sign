#!/usr/bin/env bash
set -euo pipefail

block_until_released() {
    exec 3<> "$FAKE_HOME/release"
    touch "$FAKE_HOME/entered"
    read -r ignored <&3
    exec 3>&-
}

case "$1 $2" in
    'github status')
        printf '%s\n' "$@" > "$FAKE_HOME/source-args"
        if [ "${FAKE_BLOCK_SOURCE:-0}" = 1 ]; then
            block_until_released
        fi
        printf '%s\n' ok
        exit "${FAKE_SOURCE_RESULT:-0}" ;;
    'image match')
        printf '%s\n' "$@" > "$FAKE_HOME/match-args"
        cat > "$FAKE_HOME/token"
        if [ "${FAKE_PARTIAL_RESULT:-0}" != 0 ]; then
            printf 'partial PNG'
            exit "$FAKE_PARTIAL_RESULT"
        fi
        cat "$FAKE_IMAGE" ;;
    'device send')
        printf '%s\n' "$@" > "$FAKE_HOME/send-args"
        shift 2
        [ "$1" = --device ] && [ "$3" = --image ]
        cp "$4" "$FAKE_HOME/transferred.png"
        if [ "${FAKE_BLOCK_SEND:-0}" = 1 ]; then
            trap '[ -d "$FAKE_STATE/upload.lock" ] && touch "$FAKE_HOME/locked-at-stop"; exit 143' TERM
            block_until_released
        fi
        exit "${FAKE_SEND_RESULT:-0}" ;;
    *) exit 2 ;;
esac
