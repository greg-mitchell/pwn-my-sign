#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd -P)"
real_sleep="$(command -v sleep)"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/mysign-workflow.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

expect_failure() {
    if "$@"; then
        fail 'Expected command to fail.'
    fi
}

await_file() {
    local attempt=0
    while [ ! -e "$1" ]; do
        attempt=$((attempt + 1))
        [ "$attempt" -lt 500 ] || fail "Timed out awaiting $1"
        "$real_sleep" 0.01
    done
}

setup_case() {
    export FAKE_HOME="$workspace/$1"
    export FAKE_STATE="$FAKE_HOME/state with spaces"
    export FAKE_IMAGE="$repo/tests/fixtures/cards/title-only.png"
    mkdir -p "$FAKE_STATE"
    cp "$repo/tests/workflow/fake-mysign.sh" "$FAKE_HOME/fake mysign"
    chmod +x "$FAKE_HOME/fake mysign"
}

setup_utilities() {
    export REAL_CMP="$(command -v cmp)"
    export REAL_MV="$(command -v mv)"
    mkdir "$FAKE_HOME/tools"
    cp "$repo/tests/workflow/fake-utility.sh" "$FAKE_HOME/tools/cmp"
    cp "$repo/tests/workflow/fake-utility.sh" "$FAKE_HOME/tools/mv"
    chmod +x "$FAKE_HOME/tools/cmp" "$FAKE_HOME/tools/mv"
    export PATH="$FAKE_HOME/tools:$PATH"
}

poll() {
    bash "$repo/scripts/workflow/poll.sh" --state "$FAKE_STATE" --map 'map with spaces.toml' \
        --mysign "$FAKE_HOME/fake mysign" "$@" > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr"
}

upload() {
    bash "$repo/scripts/workflow/upload.sh" --state "$FAKE_STATE" --device 'test sign' \
        --mysign "$FAKE_HOME/fake mysign" "$@" > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr"
}

test_poll_when_selected_publishes_complete_image() {
    setup_case "$FUNCNAME"
    poll
    cmp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
}

test_poll_when_policy_supplied_passes_exact_arguments() {
    setup_case "$FUNCNAME"
    printf '%s\n' github status --policy 'policy with spaces.toml' > "$FAKE_HOME/expected"
    poll --policy 'policy with spaces.toml'
    cmp "$FAKE_HOME/expected" "$FAKE_HOME/source-args"
}

test_poll_when_map_supplied_passes_exact_arguments() {
    setup_case "$FUNCNAME"
    printf '%s\n' image match --map 'map with spaces.toml' > "$FAKE_HOME/expected"
    poll
    cmp "$FAKE_HOME/expected" "$FAKE_HOME/match-args"
}

test_poll_when_unchanged_preserves_existing_file() {
    setup_case "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    ln "$FAKE_STATE/pending.png" "$FAKE_HOME/original"
    poll
    [ "$FAKE_HOME/original" -ef "$FAKE_STATE/pending.png" ]
}

test_poll_when_source_writes_token_then_fails_preserves_pending() {
    setup_case "$FUNCNAME"
    printf 'previous' > "$FAKE_STATE/pending.png"
    cp "$FAKE_STATE/pending.png" "$FAKE_HOME/expected"
    export FAKE_SOURCE_RESULT=7
    expect_failure poll
    cmp "$FAKE_HOME/expected" "$FAKE_STATE/pending.png"
}

test_poll_when_selector_writes_partial_then_fails_preserves_pending() {
    setup_case "$FUNCNAME"
    printf 'previous' > "$FAKE_STATE/pending.png"
    cp "$FAKE_STATE/pending.png" "$FAKE_HOME/expected"
    export FAKE_PARTIAL_RESULT=8
    expect_failure poll
    cmp "$FAKE_HOME/expected" "$FAKE_STATE/pending.png"
}

test_poll_when_comparison_target_invalid_raises_error() {
    setup_case "$FUNCNAME"
    mkdir "$FAKE_STATE/pending.png"
    expect_failure poll
    [ -d "$FAKE_STATE/pending.png" ]
}

test_poll_when_comparison_fails_preserves_pending() {
    setup_case "$FUNCNAME"
    setup_utilities
    printf 'previous' > "$FAKE_STATE/pending.png"
    cp "$FAKE_STATE/pending.png" "$FAKE_HOME/expected"
    export FAKE_CMP_ERROR=1
    expect_failure poll
    unset FAKE_CMP_ERROR
    cmp "$FAKE_HOME/expected" "$FAKE_STATE/pending.png"
}

test_poll_when_publication_fails_preserves_pending() {
    setup_case "$FUNCNAME"
    setup_utilities
    printf 'previous' > "$FAKE_STATE/pending.png"
    cp "$FAKE_STATE/pending.png" "$FAKE_HOME/expected"
    export FAKE_MV_ERROR=1
    expect_failure poll
    cmp "$FAKE_HOME/expected" "$FAKE_STATE/pending.png"
}

test_poll_when_failed_removes_temporary_image() {
    setup_case "$FUNCNAME"
    export FAKE_PARTIAL_RESULT=8
    expect_failure poll
    set -- "$FAKE_STATE"/.pending.*
    [ ! -e "$1" ]
}

test_poll_when_locked_does_not_start_source() {
    setup_case "$FUNCNAME"
    mkdir "$FAKE_STATE/poll.lock"
    expect_failure poll
    [ ! -e "$FAKE_HOME/source-args" ]
}

test_poll_when_finished_releases_lock() {
    setup_case "$FUNCNAME"
    poll
    [ ! -e "$FAKE_STATE/poll.lock" ]
}

test_poll_when_interrupted_holds_lock_until_pipeline_finishes() {
    setup_case "$FUNCNAME"
    mkfifo "$FAKE_HOME/release"
    export FAKE_BLOCK_SOURCE=1
    bash "$repo/scripts/workflow/poll.sh" --state "$FAKE_STATE" --map unused \
        --mysign "$FAKE_HOME/fake mysign" > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr" &
    local pid=$!
    await_file "$FAKE_HOME/entered"
    kill -TERM "$pid"
    [ -d "$FAKE_STATE/poll.lock" ] || fail 'Poll lock released while its pipeline is active.'
    printf '%s\n' release > "$FAKE_HOME/release"
    expect_failure wait "$pid"
    [ ! -e "$FAKE_STATE/poll.lock" ]
}

test_upload_when_new_snapshot_records_transferred_image() {
    setup_case "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    upload
    cmp "$FAKE_HOME/transferred.png" "$FAKE_STATE/last-sent.png"
}

test_upload_when_device_supplied_passes_exact_name() {
    setup_case "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    upload
    [ "$(sed -n '4p' "$FAKE_HOME/send-args")" = 'test sign' ]
}

test_upload_when_already_sent_skips_transfer() {
    setup_case "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    cp "$FAKE_IMAGE" "$FAKE_STATE/last-sent.png"
    upload
    [ ! -e "$FAKE_HOME/transferred.png" ]
}

test_upload_when_transfer_fails_preserves_last_sent() {
    setup_case "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    printf 'previous' > "$FAKE_STATE/last-sent.png"
    cp "$FAKE_STATE/last-sent.png" "$FAKE_HOME/expected"
    export FAKE_SEND_RESULT=9
    expect_failure upload
    cmp "$FAKE_HOME/expected" "$FAKE_STATE/last-sent.png"
}

test_upload_when_pending_missing_skips_transfer() {
    setup_case "$FUNCNAME"
    expect_failure upload
    [ ! -e "$FAKE_HOME/transferred.png" ]
}

test_upload_when_last_sent_invalid_skips_transfer() {
    setup_case "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    mkdir "$FAKE_STATE/last-sent.png"
    expect_failure upload
    [ ! -e "$FAKE_HOME/transferred.png" ]
}

test_upload_when_comparison_fails_skips_transfer() {
    setup_case "$FUNCNAME"
    setup_utilities
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    cp "$FAKE_IMAGE" "$FAKE_STATE/last-sent.png"
    export FAKE_CMP_ERROR=1
    expect_failure upload
    [ ! -e "$FAKE_HOME/transferred.png" ]
}

test_upload_when_recording_fails_preserves_last_sent() {
    setup_case "$FUNCNAME"
    setup_utilities
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    printf 'previous' > "$FAKE_STATE/last-sent.png"
    cp "$FAKE_STATE/last-sent.png" "$FAKE_HOME/expected"
    export FAKE_MV_ERROR=1
    expect_failure upload
    cmp "$FAKE_HOME/expected" "$FAKE_STATE/last-sent.png"
}

test_upload_when_locked_skips_transfer() {
    setup_case "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    mkdir "$FAKE_STATE/upload.lock"
    expect_failure upload
    [ ! -e "$FAKE_HOME/transferred.png" ]
}

start_blocked_upload() {
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    mkfifo "$FAKE_HOME/release"
    export FAKE_BLOCK_SEND=1
    bash "$repo/scripts/workflow/upload.sh" --state "$FAKE_STATE" --device 'test sign' \
        --mysign "$FAKE_HOME/fake mysign" > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr" &
    upload_pid=$!
    await_file "$FAKE_HOME/entered"
}

test_upload_when_new_pending_arrives_records_original_snapshot() {
    setup_case "$FUNCNAME"
    start_blocked_upload
    cp "$repo/tests/fixtures/cards/artwork-only.png" "$FAKE_STATE/.next"
    mv "$FAKE_STATE/.next" "$FAKE_STATE/pending.png"
    printf '%s\n' release > "$FAKE_HOME/release"
    wait "$upload_pid"
    cmp "$FAKE_IMAGE" "$FAKE_STATE/last-sent.png"
}

test_upload_when_new_pending_arrives_preserves_new_pending() {
    setup_case "$FUNCNAME"
    start_blocked_upload
    local newer="$repo/tests/fixtures/cards/artwork-only.png"
    cp "$newer" "$FAKE_STATE/.next"
    mv "$FAKE_STATE/.next" "$FAKE_STATE/pending.png"
    printf '%s\n' release > "$FAKE_HOME/release"
    wait "$upload_pid"
    cmp "$newer" "$FAKE_STATE/pending.png"
}

test_upload_when_interrupted_stops_sender_before_unlocking() {
    setup_case "$FUNCNAME"
    start_blocked_upload
    kill -TERM "$upload_pid"
    expect_failure wait "$upload_pid"
    [ -e "$FAKE_HOME/locked-at-stop" ]
}

test_upload_when_interrupted_releases_lock() {
    setup_case "$FUNCNAME"
    start_blocked_upload
    kill -TERM "$upload_pid"
    expect_failure wait "$upload_pid"
    [ ! -e "$FAKE_STATE/upload.lock" ]
}

test_upload_when_interrupted_does_not_record_success() {
    setup_case "$FUNCNAME"
    start_blocked_upload
    kill -TERM "$upload_pid"
    expect_failure wait "$upload_pid"
    [ ! -e "$FAKE_STATE/last-sent.png" ]
}

source "$repo/tests/workflow/watch-tests.sh"

count=0
for test in $(declare -F | awk '$3 ~ /^test_/ {print $3}'); do
    ( "$test" )
    count=$((count + 1))
    printf 'PASS %s\n' "$test"
done
printf '%s workflow integration checks passed.\n' "$count"
