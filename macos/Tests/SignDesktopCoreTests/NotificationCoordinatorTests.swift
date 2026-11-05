import SignDesktopCore
import Testing

@MainActor
private final class FakeNotifications: NotificationClient {
    var permission = NotificationPermission.authorized
    var submissionFailure: NotificationFailure?
    var deferAuthorization = false
    var deferSubmission = false
    var settingCalls = 0
    var authorizationCalls = 0
    var submissions: [DesktopNotification] = []
    var authorizationCallbacks: [@MainActor (NotificationFailure?) -> Void] = []
    var submissionCallbacks: [@MainActor (NotificationFailure?) -> Void] = []

    func settings(_ completion: @escaping @MainActor (NotificationPermission) -> Void) {
        settingCalls += 1
        completion(permission)
    }

    func requestAuthorization(_ completion: @escaping @MainActor (NotificationFailure?) -> Void) {
        authorizationCalls += 1
        if deferAuthorization { authorizationCallbacks.append(completion) }
        else {
            permission = .authorized
            completion(nil)
        }
    }

    func submit(
        _ notification: DesktopNotification,
        completion: @escaping @MainActor (NotificationFailure?) -> Void
    ) {
        submissions.append(notification)
        if deferSubmission { submissionCallbacks.append(completion) }
        else { completion(submissionFailure) }
    }
}

private let buttonRequest = DesktopNotification(
    id: "button-7", kind: .button, title: "Sign ready to upload", body: "Press the sign's button now."
)

@MainActor
private final class SessionState {
    var current = true
}

@Test @MainActor
func test_send_when_authorized_calls_notification_client_with_request() {
    let client = FakeNotifications()
    let coordinator = NotificationCoordinator(client: client)

    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }

    #expect(client.submissions == [buttonRequest])
}

@Test @MainActor
func test_send_when_submitted_returns_matching_positive_acknowledgment() {
    let coordinator = NotificationCoordinator(client: FakeNotifications())
    var acknowledgments: [NotificationAcknowledgment] = []

    coordinator.send(buttonRequest, isCurrent: { true }, completion: { acknowledgments.append($0) })

    #expect(acknowledgments == [NotificationAcknowledgment(id: "button-7", submitted: true)])
}

@Test @MainActor
func test_send_when_permission_unknown_calls_authorization_request() {
    let client = FakeNotifications()
    client.permission = .notDetermined
    let coordinator = NotificationCoordinator(client: client)

    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }

    #expect(client.authorizationCalls == 1)
}

@Test @MainActor
func test_send_when_permission_unknown_calls_settings_again_after_authorization() {
    let client = FakeNotifications()
    client.permission = .notDetermined
    let coordinator = NotificationCoordinator(client: client)

    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }

    #expect(client.settingCalls == 2)
}

@Test @MainActor
func test_send_when_denied_calls_no_submission() {
    let client = FakeNotifications()
    client.permission = .denied
    let coordinator = NotificationCoordinator(client: client)

    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }

    #expect(client.submissions.isEmpty)
}

@Test @MainActor
func test_send_when_denied_returns_actionable_error() {
    let client = FakeNotifications()
    client.permission = .denied
    let coordinator = NotificationCoordinator(client: client)
    var acknowledgments: [NotificationAcknowledgment] = []

    coordinator.send(buttonRequest, isCurrent: { true }, completion: { acknowledgments.append($0) })

    #expect(acknowledgments == [NotificationAcknowledgment(
        id: "button-7", submitted: false,
        error: "Allow notifications for My Sign in System Settings → Notifications, then try again."
    )])
}

@Test @MainActor
func test_send_when_alerts_disabled_returns_banner_settings_error() {
    let client = FakeNotifications()
    client.permission = .alertsDisabled
    let coordinator = NotificationCoordinator(client: client)

    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }

    #expect(coordinator.lastError ==
        "Enable notification banners for My Sign in System Settings → Notifications, then try again.")
}

@Test @MainActor
func test_send_when_submission_fails_returns_negative_acknowledgment() {
    let client = FakeNotifications()
    client.submissionFailure = NotificationFailure("Submission failed")
    let coordinator = NotificationCoordinator(client: client)
    var acknowledgments: [NotificationAcknowledgment] = []

    coordinator.send(buttonRequest, isCurrent: { true }, completion: { acknowledgments.append($0) })

    #expect(acknowledgments == [NotificationAcknowledgment(
        id: "button-7", submitted: false, error: "Submission failed"
    )])
}

@Test @MainActor
func test_send_when_retry_succeeds_returns_cleared_previous_error() {
    let client = FakeNotifications()
    client.permission = .denied
    let coordinator = NotificationCoordinator(client: client)
    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }
    client.permission = .authorized

    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }

    #expect(coordinator.lastError == nil)
}

@Test @MainActor
func test_authorizationCallback_when_settings_changed_calls_submission_despite_earlier_error() {
    let client = FakeNotifications()
    client.permission = .notDetermined
    client.deferAuthorization = true
    let coordinator = NotificationCoordinator(client: client)
    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }
    client.permission = .authorized

    client.authorizationCallbacks[0](NotificationFailure("Earlier denial"))

    #expect(client.submissions == [buttonRequest])
}

@Test @MainActor
func test_authorizationCallback_when_older_request_fails_returns_latest_successful_status() {
    let client = FakeNotifications()
    client.permission = .notDetermined
    client.deferAuthorization = true
    let coordinator = NotificationCoordinator(client: client)
    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }
    client.permission = .authorized
    coordinator.send(
        DesktopNotification(id: "test-8", kind: .updateAvailable, title: "Test", body: "Works"),
        isCurrent: { true }
    ) { _ in }
    client.permission = .denied

    client.authorizationCallbacks[0](NotificationFailure("Earlier denial"))

    #expect(coordinator.lastError == nil)
}

@Test @MainActor
func test_submissionCallback_when_child_replaced_calls_no_acknowledgment() {
    let client = FakeNotifications()
    client.deferSubmission = true
    let coordinator = NotificationCoordinator(client: client)
    let session = SessionState()
    var acknowledgments: [NotificationAcknowledgment] = []
    coordinator.send(buttonRequest, isCurrent: { session.current }, completion: { acknowledgments.append($0) })
    session.current = false

    client.submissionCallbacks[0](nil)

    #expect(acknowledgments.isEmpty)
}

@Test @MainActor
func test_send_when_current_session_already_closed_calls_no_submission() {
    let client = FakeNotifications()
    let coordinator = NotificationCoordinator(client: client)

    coordinator.send(buttonRequest, isCurrent: { false }) { _ in }

    #expect(client.submissions.isEmpty)
}

@Test @MainActor
func test_send_when_error_changes_calls_status_listener() {
    let client = FakeNotifications()
    client.permission = .denied
    let coordinator = NotificationCoordinator(client: client)
    var changes = 0
    coordinator.onStatusChange = { changes += 1 }

    coordinator.send(buttonRequest, isCurrent: { true }) { _ in }

    #expect(changes == 1)
}

@Test @MainActor
func test_authorizationCallback_when_workflow_advanced_calls_no_submission() {
    let client = FakeNotifications()
    client.permission = .notDetermined
    client.deferAuthorization = true
    let coordinator = NotificationCoordinator(client: client)
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .waitingForButton, message: "Press the button"))
    menu.beginNotification(buttonRequest.id)
    coordinator.send(buttonRequest, isCurrent: { menu.isNotificationPending(buttonRequest.id) }) { _ in }
    menu.receive(WorkflowView(revision: 4, phase: .uploadFailed, message: "Notification timed out"))
    client.permission = .authorized

    client.authorizationCallbacks[0](nil)

    #expect(client.submissions.isEmpty)
}

@Test @MainActor
func test_authorizationCallback_when_workflow_advanced_calls_no_acknowledgment() {
    let client = FakeNotifications()
    client.permission = .notDetermined
    client.deferAuthorization = true
    let coordinator = NotificationCoordinator(client: client)
    var acknowledgments: [NotificationAcknowledgment] = []
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .waitingForButton, message: "Press the button"))
    menu.beginNotification(buttonRequest.id)
    coordinator.send(
        buttonRequest, isCurrent: { menu.isNotificationPending(buttonRequest.id) },
        completion: { acknowledgments.append($0) }
    )
    menu.receive(WorkflowView(revision: 4, phase: .uploadFailed, message: "Notification timed out"))
    client.permission = .authorized

    client.authorizationCallbacks[0](nil)

    #expect(acknowledgments.isEmpty)
}

@Test @MainActor
func test_submissionCallback_when_workflow_advanced_calls_no_acknowledgment() {
    let client = FakeNotifications()
    client.deferSubmission = true
    let coordinator = NotificationCoordinator(client: client)
    var acknowledgments: [NotificationAcknowledgment] = []
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .waitingForButton, message: "Press the button"))
    menu.beginNotification(buttonRequest.id)
    coordinator.send(
        buttonRequest, isCurrent: { menu.isNotificationPending(buttonRequest.id) },
        completion: { acknowledgments.append($0) }
    )
    menu.receive(WorkflowView(revision: 4, phase: .uploadFailed, message: "Notification timed out"))

    client.submissionCallbacks[0](nil)

    #expect(acknowledgments.isEmpty)
}

@Test @MainActor
func test_authorizationCallback_when_workflow_advanced_calls_independent_test_submission() {
    let client = FakeNotifications()
    client.permission = .notDetermined
    client.deferAuthorization = true
    let coordinator = NotificationCoordinator(client: client)
    let testRequest = DesktopNotification(id: "test-8", kind: .updateAvailable, title: "Test", body: "Works")
    var menu = MenuState()
    menu.receive(WorkflowView(revision: 3, phase: .waitingForButton, message: "Press the button"))
    menu.beginNotification(buttonRequest.id)
    coordinator.send(buttonRequest, isCurrent: { menu.isNotificationPending(buttonRequest.id) }) { _ in }
    coordinator.send(testRequest, isCurrent: { true }) { _ in }
    menu.receive(WorkflowView(revision: 4, phase: .uploadFailed, message: "Notification timed out"))
    client.permission = .authorized

    client.authorizationCallbacks.forEach { $0(nil) }

    #expect(client.submissions == [testRequest])
}
