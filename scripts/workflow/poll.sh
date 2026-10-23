#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

map=''
policy=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --state) require_value "$@"; state="$2"; shift 2 ;;
        --map) require_value "$@"; map="$2"; shift 2 ;;
        --policy) require_value "$@"; policy="$2"; shift 2 ;;
        --mysign) require_value "$@"; mysign="$2"; shift 2 ;;
        --help)
            printf '%s\n' 'Usage: poll.sh --state DIR --map FILE [--policy FILE] [--mysign EXECUTABLE]'
            exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done
[ -n "$state" ] && [ -n "$map" ] || fail 'Provide --state DIR and --map FILE.'
mkdir -p "$state"
state="$(cd "$state" && pwd -P)"
acquire_lock poll
temporary="$(mktemp "$state/.pending.XXXXXX")"

source_args=(github status)
if [ -n "$policy" ]; then
    source_args+=(--policy "$policy")
fi
# Foreground pipelines finish before Bash handles a signal trap, so the lock covers both commands.
"$mysign" "${source_args[@]}" | "$mysign" image match --map "$map" > "$temporary"
if images_equal "$temporary" "$state/pending.png"; then
    printf '%s\n' 'The desired image is unchanged.' >&2
else
    mv -f "$temporary" "$state/pending.png"
    temporary=''
    printf '%s\n' 'Published pending image.' >&2
fi
