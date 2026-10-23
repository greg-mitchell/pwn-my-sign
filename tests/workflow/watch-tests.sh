#!/usr/bin/env bash

setup_watch() {
    setup_case "$1"
    mkdir "$FAKE_HOME/tools"
    cp "$repo/tests/workflow/fake-sleep.sh" "$FAKE_HOME/tools/sleep"
    chmod +x "$FAKE_HOME/tools/sleep"
    export PATH="$FAKE_HOME/tools:$PATH"
    mkfifo "$FAKE_HOME/sleep-release"
}

watch_command() {
    bash "$repo/scripts/workflow/watch.sh" --state "$FAKE_STATE" --map 'map with spaces.toml' \
        --device 'test sign' --mysign "$FAKE_HOME/fake mysign" "$@"
}

start_watch() {
    mkfifo "$FAKE_HOME/input"
    exec 8<> "$FAKE_HOME/input"
    bash "$repo/scripts/workflow/watch.sh" --state "$FAKE_STATE" --map unused \
        --device 'test sign' --mysign "$FAKE_HOME/fake mysign" "$@" \
        < "$FAKE_HOME/input" 8>&- > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr" &
    watch_pid=$!
}

stop_watch() {
    kill -TERM "$watch_pid"
    expect_failure wait "$watch_pid"
    exec 8>&-
}

await_prompt() {
    local attempt=0
    until grep -q 'Press Enter' "$FAKE_HOME/stderr"; do
        attempt=$((attempt + 1))
        [ "$attempt" -lt 500 ] || fail 'Timed out awaiting watcher prompt.'
        "$real_sleep" 0.01
    done
}

has_bell() {
    case "$(cat "$FAKE_HOME/stderr")" in
        *$'\a'*) return 0 ;;
        *) return 1 ;;
    esac
}

test_watch_when_interval_invalid_fails_before_polling() {
    setup_watch "$FUNCNAME"
    local interval
    for interval in 0 000 -1 1.5 junk ''; do
        expect_failure watch_command --interval "$interval" < /dev/null \
            > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr"
    done
    [ ! -e "$FAKE_HOME/source-args" ]
}

test_watch_when_unsent_rings_bell() {
    setup_watch "$FUNCNAME"
    watch_command < /dev/null > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr"
    has_bell
}

test_watch_when_input_eof_exits_without_upload() {
    setup_watch "$FUNCNAME"
    watch_command < /dev/null > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr"
    [ ! -e "$FAKE_HOME/transferred.png" ]
}

test_watch_when_enter_pressed_uploads_pending() {
    setup_watch "$FUNCNAME"
    start_watch
    await_prompt
    printf '\n' >&8
    await_file "$FAKE_HOME/sleep-entered"
    stop_watch
    cmp "$FAKE_IMAGE" "$FAKE_STATE/last-sent.png"
}

test_watch_when_upload_failed_retries_after_interval() {
    setup_watch "$FUNCNAME"
    export FAKE_SEND_RESULT=9
    start_watch --interval 7
    await_prompt
    printf '\n' >&8
    await_file "$FAKE_HOME/sleep-entered"
    stop_watch
    [ "$(cat "$FAKE_HOME/sleep-calls")" = 7 ]
}

test_watch_when_already_sent_does_not_ring() {
    setup_watch "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/last-sent.png"
    start_watch
    await_file "$FAKE_HOME/sleep-entered"
    stop_watch
    expect_failure has_bell
}

test_watch_when_poll_failed_does_not_ring_for_retained_image() {
    setup_watch "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/pending.png"
    export FAKE_SOURCE_RESULT=7
    start_watch
    await_file "$FAKE_HOME/sleep-entered"
    stop_watch
    expect_failure has_bell
}

test_watch_when_poll_failed_retries_polling() {
    setup_watch "$FUNCNAME"
    printf '7' > "$FAKE_HOME/source-result"
    export FAKE_RESET_SOURCE=1
    watch_command < /dev/null > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr"
    [ "$(wc -l < "$FAKE_HOME/poll-calls" | tr -d ' ')" = 2 ]
}

test_watch_when_input_times_out_polls_again_without_extra_sleep() {
    setup_watch "$FUNCNAME"
    start_watch --interval 1
    await_prompt
    local attempt=0
    until [ "$(wc -l < "$FAKE_HOME/poll-calls" | tr -d ' ')" -ge 2 ]; do
        attempt=$((attempt + 1))
        [ "$attempt" -lt 500 ] || fail 'Timed out awaiting second poll.'
        "$real_sleep" 0.01
    done
    stop_watch
    [ ! -e "$FAKE_HOME/sleep-calls" ]
}

test_watch_when_duplicate_does_not_poll() {
    setup_watch "$FUNCNAME"
    mkdir "$FAKE_STATE/watch.lock"
    expect_failure watch_command < /dev/null > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr"
    [ ! -e "$FAKE_HOME/source-args" ]
}

test_watch_when_comparison_fails_exits_without_upload() {
    setup_case "$FUNCNAME"
    setup_utilities
    cp "$FAKE_IMAGE" "$FAKE_STATE/last-sent.png"
    export FAKE_CMP_ERROR=1
    expect_failure watch_command < /dev/null > "$FAKE_HOME/stdout" 2> "$FAKE_HOME/stderr"
    [ ! -e "$FAKE_HOME/transferred.png" ]
}

test_watch_when_interrupted_during_sleep_waits_before_unlocking() {
    setup_watch "$FUNCNAME"
    cp "$FAKE_IMAGE" "$FAKE_STATE/last-sent.png"
    start_watch
    await_file "$FAKE_HOME/sleep-entered"
    stop_watch
    [ -e "$FAKE_HOME/sleep-locked-at-stop" ]
}

test_watch_when_interrupted_during_poll_holds_watch_lock_until_pipeline_stops() {
    setup_watch "$FUNCNAME"
    mkfifo "$FAKE_HOME/release"
    export FAKE_BLOCK_SOURCE=1
    start_watch
    await_file "$FAKE_HOME/entered"
    kill -TERM "$watch_pid"
    [ -d "$FAKE_STATE/watch.lock" ] || fail 'Watcher unlocked before its active poll ended.'
    printf '%s\n' release > "$FAKE_HOME/release"
    expect_failure wait "$watch_pid"
    exec 8>&-
    [ ! -e "$FAKE_STATE/watch.lock" ]
}

test_watch_when_interrupted_during_upload_stops_sender_before_unlocking() {
    setup_watch "$FUNCNAME"
    mkfifo "$FAKE_HOME/release"
    export FAKE_BLOCK_SEND=1
    start_watch
    await_prompt
    printf '\n' >&8
    await_file "$FAKE_HOME/entered"
    stop_watch
    [ -e "$FAKE_HOME/locked-at-stop" ]
}

test_watch_when_interrupted_during_input_releases_watch_lock() {
    setup_watch "$FUNCNAME"
    start_watch
    await_prompt
    stop_watch
    [ ! -e "$FAKE_STATE/watch.lock" ]
}

test_watch_when_ctrl_c_during_input_releases_watch_lock() {
    setup_watch "$FUNCNAME"
    # Monitor mode gives background test jobs the foreground command's SIGINT disposition.
    set -m
    start_watch
    await_prompt
    kill -INT "$watch_pid"
    set +m
    expect_failure wait "$watch_pid"
    exec 8>&-
    [ ! -e "$FAKE_STATE/watch.lock" ]
}

test_watch_when_ctrl_c_during_upload_stops_sender() {
    setup_watch "$FUNCNAME"
    mkfifo "$FAKE_HOME/release"
    export FAKE_BLOCK_SEND=1
    set -m
    start_watch
    await_prompt
    printf '\n' >&8
    await_file "$FAKE_HOME/entered"
    kill -INT "$watch_pid"
    set +m
    expect_failure wait "$watch_pid"
    exec 8>&-
    [ -e "$FAKE_HOME/locked-at-stop" ]
}
