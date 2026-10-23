#!/usr/bin/env bash
set -euo pipefail
workflow="$(cd "$(dirname "$0")" && pwd -P)"
source "$workflow/common.sh"

map=''
policy=''
device=''
interval=300
while [ "$#" -gt 0 ]; do
    case "$1" in
        --state) require_value "$@"; state="$2"; shift 2 ;;
        --map) require_value "$@"; map="$2"; shift 2 ;;
        --policy) require_value "$@"; policy="$2"; shift 2 ;;
        --device) require_value "$@"; device="$2"; shift 2 ;;
        --mysign) require_value "$@"; mysign="$2"; shift 2 ;;
        --interval) require_value "$@"; interval="$2"; shift 2 ;;
        --help)
            printf '%s\n' 'Usage: watch.sh --state DIR --map FILE --device NAME [--policy FILE]'
            printf '%s\n' '                [--mysign EXECUTABLE] [--interval SECONDS (default: 300)]'
            exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done
[ -n "$state" ] && [ -n "$map" ] && [ -n "$device" ] || fail 'Provide --state DIR, --map FILE, and --device NAME.'
case "$interval" in
    ''|*[!0-9]*) fail '--interval must be a positive decimal integer.' ;;
esac
case "$interval" in
    *[1-9]*) ;;
    *) fail '--interval must be a positive decimal integer.' ;;
esac
mkdir -p "$state"
state="$(cd "$state" && pwd -P)"
acquire_lock watch

run_child() {
    local result
    "$@" &
    child=$!
    if wait "$child"; then
        child=''
        return 0
    else
        result=$?
        child=''
        return "$result"
    fi
}

poll_args=(--state "$state" --map "$map" --mysign "$mysign")
if [ -n "$policy" ]; then
    poll_args+=(--policy "$policy")
fi
while :; do
    if ! run_child bash "$workflow/poll.sh" "${poll_args[@]}"; then
        printf 'Polling failed; retrying in %s seconds.\n' "$interval" >&2
        run_child sleep "$interval"
        continue
    fi
    if images_equal "$state/pending.png" "$state/last-sent.png"; then
        run_child sleep "$interval"
        continue
    fi
    printf '\aPending image differs from last sent.\n' >&2
    printf 'Press Enter to upload; press the sign button when the sender prompts.\n' >&2
    printf 'Polling again in %s seconds if no input arrives.\n' "$interval" >&2
    read_started=$SECONDS
    if read -r -t "$interval" reply; then
        if ! run_child bash "$workflow/upload.sh" --state "$state" --device "$device" --mysign "$mysign"; then
            printf 'Upload failed; retrying after %s seconds.\n' "$interval" >&2
        fi
        run_child sleep "$interval"
    else
        result=$?
        # Bash 3.2 reports both EOF and timeout as 1; its elapsed timer distinguishes a full wait.
        if [ "$result" -eq 1 ] && [ "$((SECONDS - read_started))" -lt "$interval" ]; then
            exit 0
        fi
        [ "$result" -eq 1 ] || [ "$result" -gt 128 ] || fail 'Cannot read terminal input.'
    fi
done
