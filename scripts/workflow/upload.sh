#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

device=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --state) require_value "$@"; state="$2"; shift 2 ;;
        --device) require_value "$@"; device="$2"; shift 2 ;;
        --mysign) require_value "$@"; mysign="$2"; shift 2 ;;
        --help)
            printf '%s\n' 'Usage: upload.sh --state DIR --device NAME [--mysign EXECUTABLE]'
            exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done
[ -n "$state" ] && [ -n "$device" ] || fail 'Provide --state DIR and --device NAME.'
mkdir -p "$state"
state="$(cd "$state" && pwd -P)"
acquire_lock upload
temporary="$(mktemp "$state/.upload.XXXXXX")"
[ -f "$state/pending.png" ] || fail 'No pending image; run poll.sh first.'
cp "$state/pending.png" "$temporary"

if images_equal "$temporary" "$state/last-sent.png"; then
    printf '%s\n' 'The latest desired image has already been sent.' >&2
    exit 0
fi

# A tracked child lets interruption stop and reap the sender before releasing its device lock.
"$mysign" device send --device "$device" --image "$temporary" &
child=$!
if wait "$child"; then
    child=''
else
    result=$?
    child=''
    exit "$result"
fi
mv -f "$temporary" "$state/last-sent.png"
temporary=''
printf '%s\n' 'Transfer calls completed; recorded the uploaded snapshot.' >&2
