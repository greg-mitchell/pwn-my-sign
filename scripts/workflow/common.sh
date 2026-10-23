#!/usr/bin/env bash

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

require_value() {
    [ "$#" -ge 2 ] && [ -n "$2" ] || fail "Missing value for $1."
}

cleanup() {
    if [ -n "$child" ]; then
        kill -TERM "$child" 2>/dev/null || :
        wait "$child" 2>/dev/null || :
    fi
    [ -z "$temporary" ] || rm -f "$temporary"
    if [ -n "$lock" ]; then
        rm -f "$lock/pid"
        rmdir "$lock"
    fi
}

interrupted() {
    trap '' INT TERM
    exit "$1"
}

acquire_lock() {
    local candidate="$state/$1.lock"
    mkdir "$candidate" 2>/dev/null || fail "Cannot acquire $candidate; another workflow may be running."
    lock="$candidate"
    printf '%s\n' "$$" > "$lock/pid"
}

# Distinguish a changed image from a comparison failure before allowing publication or transfer.
images_equal() {
    local result
    if [ ! -e "$2" ] && [ ! -L "$2" ]; then
        return 1
    fi
    [ -f "$2" ] && [ -r "$2" ] || fail "Cannot compare image: $2"
    if cmp -s "$1" "$2"; then
        return 0
    else
        result=$?
        [ "$result" -eq 1 ] || fail "Cannot compare image: $2"
        return 1
    fi
}

state=''
mysign='mysign'
lock=''
temporary=''
child=''
trap cleanup EXIT
trap 'interrupted 130' INT
trap 'interrupted 143' TERM
