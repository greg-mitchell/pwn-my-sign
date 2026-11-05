import SignDesktopCore
import Testing

@Test
func test_didExit_when_quitting_with_stderr_open_calls_bounded_drain() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestQuit()
    _ = lifecycle.didClose(.stdout, session: "first")

    let effects = lifecycle.didExit("first")

    #expect(!effects.isEmpty)
}

@Test
func test_drainDeadlineExpired_when_quitting_with_stderr_open_calls_quit() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestQuit()
    _ = lifecycle.didClose(.stdout, session: "first")
    _ = lifecycle.didExit("first")

    let effects = lifecycle.drainDeadlineExpired("first")

    #expect(effects == [.drainTimedOut("first"), .quit])
}

@Test
func test_drainDeadlineExpired_when_wake_waits_for_stderr_calls_restart() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestSleep()
    _ = lifecycle.requestWake()
    _ = lifecycle.didClose(.stdout, session: "first")
    _ = lifecycle.didExit("first")

    let effects = lifecycle.drainDeadlineExpired("first")

    #expect(effects == [.drainTimedOut("first"), .start])
}

@Test
func test_drainDeadlineExpired_when_child_still_alive_calls_no_forced_retirement() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestQuit()

    let effects = lifecycle.drainDeadlineExpired("first")

    #expect(effects.isEmpty)
}

@Test
func test_drainDeadlineExpired_when_old_child_deadline_arrives_returns_current_session() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("replacement")

    _ = lifecycle.drainDeadlineExpired("first")

    #expect(lifecycle.session == "replacement")
}

@Test
func test_didExit_when_streams_are_not_drained_returns_current_session() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")

    _ = lifecycle.didExit("first")

    #expect(lifecycle.session == "first")
}

@Test
func test_requestStart_when_stopped_calls_start() {
    var lifecycle = ProcessLifecycle()

    let effects = lifecycle.requestStart()

    #expect(effects == [.start])
}

@Test
func test_requestStart_when_running_calls_no_start() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")

    let effects = lifecycle.requestStart()

    #expect(effects.isEmpty)
}

@Test
func test_requestSleep_when_child_running_calls_terminate() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")

    let effects = lifecycle.requestSleep()

    #expect(effects == [.terminate("first")])
}

@Test
func test_requestWake_when_sleep_cleanup_pending_calls_no_start() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestSleep()

    let effects = lifecycle.requestWake()

    #expect(effects.isEmpty)
}

@Test
func test_didExit_when_wake_preceded_cleanup_calls_one_start() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestSleep()
    _ = lifecycle.requestWake()
    _ = lifecycle.didClose(.stdout, session: "first")
    _ = lifecycle.didClose(.stderr, session: "first")

    let effects = lifecycle.didExit("first")

    #expect(effects == [.start])
}

@Test
func test_didExit_when_still_sleeping_calls_no_start() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestSleep()
    _ = lifecycle.didClose(.stdout, session: "first")
    _ = lifecycle.didClose(.stderr, session: "first")

    let effects = lifecycle.didExit("first")

    #expect(effects.isEmpty)
}

@Test
func test_requestWake_when_child_finished_calls_start() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestSleep()
    _ = lifecycle.didClose(.stdout, session: "first")
    _ = lifecycle.didClose(.stderr, session: "first")
    _ = lifecycle.didExit("first")

    let effects = lifecycle.requestWake()

    #expect(effects == [.start])
}

@Test
func test_requestQuit_when_child_running_calls_terminate_before_quit() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")

    let effects = lifecycle.requestQuit()

    #expect(effects == [.terminate("first")])
}

@Test
func test_didExit_when_quit_waits_for_cleanup_calls_quit() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestQuit()
    _ = lifecycle.didClose(.stdout, session: "first")
    _ = lifecycle.didClose(.stderr, session: "first")

    let effects = lifecycle.didExit("first")

    #expect(effects == [.quit])
}

@Test
func test_didExit_when_child_stops_unexpectedly_calls_no_restart() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.didClose(.stdout, session: "first")
    _ = lifecycle.didClose(.stderr, session: "first")

    let effects = lifecycle.didExit("first")

    #expect(effects.isEmpty)
}

@Test
func test_didExit_when_old_child_callback_arrives_returns_current_session() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("replacement")

    _ = lifecycle.didExit("previous")

    #expect(lifecycle.session == "replacement")
}

@Test
func test_canInteract_when_stopping_returns_false() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestSleep()

    let current = lifecycle.canInteract(with: "first")

    #expect(!current)
}

@Test
func test_didClose_when_other_stream_still_open_returns_current_session() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.didExit("first")

    _ = lifecycle.didClose(.stdout, session: "first")

    #expect(lifecycle.session == "first")
}

@Test
func test_didClose_when_last_stream_drains_after_exit_calls_quit() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.requestQuit()
    _ = lifecycle.didExit("first")
    _ = lifecycle.didClose(.stdout, session: "first")

    let effects = lifecycle.didClose(.stderr, session: "first")

    #expect(effects == [.quit])
}

@Test
func test_didClose_when_process_has_not_exited_returns_current_session() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.didClose(.stdout, session: "first")

    _ = lifecycle.didClose(.stderr, session: "first")

    #expect(lifecycle.session == "first")
}

@Test
func test_didClose_when_previous_session_reports_eof_returns_current_session() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("replacement")

    _ = lifecycle.didClose(.stdout, session: "previous")

    #expect(lifecycle.session == "replacement")
}

@Test
func test_canInteract_when_process_exited_before_eof_returns_false() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("first")
    _ = lifecycle.didExit("first")

    let current = lifecycle.canInteract(with: "first")

    #expect(!current)
}

@Test
func test_canInteract_when_child_replaced_returns_false_for_previous_session() {
    var lifecycle = ProcessLifecycle()
    lifecycle.didStart("replacement")

    let current = lifecycle.canInteract(with: "previous")

    #expect(!current)
}
