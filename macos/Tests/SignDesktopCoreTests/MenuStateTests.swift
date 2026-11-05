import SignDesktopCore
import Testing

@Test(arguments: [MenuAction.upload, .check])
func test_take_when_notification_ack_pending_returns_no_action(_ action: MenuAction) {
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .updateAvailable, message: "Update ready", uploadAvailable: true))
    menu.beginNotification("update-7")

    let record = menu.take(action)

    #expect(record == nil)
}

@Test
func test_finishNotification_when_ack_sent_returns_actions_enabled() {
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .updateAvailable, message: "Update ready", uploadAvailable: true))
    menu.beginNotification("update-7")

    menu.finishNotification("update-7")

    #expect(menu.canUpload)
}

@Test
func test_finishNotification_when_different_request_pending_returns_actions_disabled() {
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .updateAvailable, message: "Update ready", uploadAvailable: true))
    menu.beginNotification("update-8")

    menu.finishNotification("update-7")

    #expect(!menu.canUpload)
}

@Test
func test_receive_when_notification_pending_returns_actions_still_disabled() {
    var menu = MenuState()
    menu.beginNotification("update-7")

    menu.receive(WorkflowView(revision: 4, phase: .updateAvailable, message: "Update ready", uploadAvailable: true))

    #expect(!menu.canUpload)
}

@Test
func test_take_when_update_available_returns_upload_with_current_revision() {
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .updateAvailable, message: "Update ready", uploadAvailable: true))

    let action = menu.take(.upload)

    #expect(action == ActionRecord(action: .upload, revision: 3))
}

@Test
func test_take_when_action_already_sent_returns_no_duplicate() {
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .updateAvailable, message: "Update ready", uploadAvailable: true))
    _ = menu.take(.upload)

    let action = menu.take(.upload)

    #expect(action == nil)
}

@Test
func test_receive_when_revision_older_returns_current_view() {
    var menu = MenuState()
    let current = WorkflowView(revision: 3, phase: .sending, message: "Sending")
    menu.receive(current)

    menu.receive(WorkflowView(revision: 2, phase: .updateAvailable, message: "Old update", uploadAvailable: true))

    #expect(menu.view == current)
}

@Test
func test_receive_when_revision_repeated_returns_actions_still_disabled() {
    var menu = MenuState()
    let view = WorkflowView(revision: 3, phase: .updateAvailable, message: "Update ready", uploadAvailable: true)
    menu.receive(view)
    _ = menu.take(.upload)

    menu.receive(view)

    #expect(!menu.canUpload)
}

@Test
func test_receive_when_new_idle_view_arrives_returns_actions_enabled() {
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .upToDate, message: "Sent"))
    _ = menu.take(.check)

    menu.receive(WorkflowView(revision: 4, phase: .updateAvailable, message: "New image", uploadAvailable: true))

    #expect(menu.canUpload)
}

@Test(arguments: [WorkflowPhase.checking, .preparingUpload, .waitingForButton, .sending])
func test_take_when_workflow_busy_returns_no_check_action(_ phase: WorkflowPhase) {
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: phase, message: "Busy"))

    let action = menu.take(.check)

    #expect(action == nil)
}

@Test
func test_take_when_pending_is_retained_returns_explicit_upload() {
    var menu = MenuState()
    menu.receive(WorkflowView(
        revision: 3, phase: .pollFailed, message: "Check failed; retained image available",
        uploadAvailable: true, retained: true, error: "Producer exited unsuccessfully"
    ))

    let action = menu.take(.upload)

    #expect(action == ActionRecord(action: .upload, revision: 3))
}

@Test
func test_take_when_no_view_arrived_returns_no_action() {
    var menu = MenuState()

    let action = menu.take(.check)

    #expect(action == nil)
}
