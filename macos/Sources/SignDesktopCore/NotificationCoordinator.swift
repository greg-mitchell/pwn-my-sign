public enum NotificationPermission: Sendable {
    case notDetermined, denied, authorized, alertsDisabled
}

public struct NotificationFailure: Error, Equatable, Sendable {
    public let message: String

    public init(_ message: String) {
        self.message = String(message.prefix(1000))
    }
}

@MainActor
public protocol NotificationClient: AnyObject {
    func settings(_ completion: @escaping @MainActor (NotificationPermission) -> Void)
    func requestAuthorization(_ completion: @escaping @MainActor (NotificationFailure?) -> Void)
    func submit(
        _ notification: DesktopNotification,
        completion: @escaping @MainActor (NotificationFailure?) -> Void
    )
}

@MainActor
public final class NotificationCoordinator {
    private let client: any NotificationClient
    private var latestRequest = 0
    public private(set) var lastError: String?
    public var onStatusChange: (@MainActor () -> Void)?

    public init(client: any NotificationClient) {
        self.client = client
    }

    public func send(
        _ notification: DesktopNotification,
        isCurrent: @escaping @MainActor () -> Bool,
        completion: @escaping @MainActor (NotificationAcknowledgment) -> Void
    ) {
        latestRequest += 1
        let request = latestRequest
        client.settings { permission in
            self.handle(
                permission, notification: notification, request: request,
                canRequest: true, authorizationError: nil, isCurrent: isCurrent, completion: completion
            )
        }
    }

    private func handle(
        _ permission: NotificationPermission,
        notification: DesktopNotification,
        request: Int,
        canRequest: Bool,
        authorizationError: NotificationFailure?,
        isCurrent: @escaping @MainActor () -> Bool,
        completion: @escaping @MainActor (NotificationAcknowledgment) -> Void
    ) {
        guard isCurrent() else { return }
        switch permission {
        case .notDetermined where canRequest:
            client.requestAuthorization { error in
                guard isCurrent() else { return }
                // The person can change settings while an authorization callback is outstanding.
                self.client.settings { current in
                    self.handle(
                        current, notification: notification, request: request,
                        canRequest: false, authorizationError: error, isCurrent: isCurrent, completion: completion
                    )
                }
            }
        case .notDetermined:
            let error = authorizationError?.message
                ?? "Notification permission has not been granted. Try Test notification."
            finish(
                notification, request: request,
                error: error,
                isCurrent: isCurrent, completion: completion
            )
        case .denied:
            finish(
                notification, request: request,
                error: "Allow notifications for My Sign in System Settings → Notifications, then try again.",
                isCurrent: isCurrent, completion: completion
            )
        case .alertsDisabled:
            finish(
                notification, request: request,
                error: "Enable notification banners for My Sign in System Settings → Notifications, then try again.",
                isCurrent: isCurrent, completion: completion
            )
        case .authorized:
            client.submit(notification) { error in
                self.finish(
                    notification, request: request, error: error?.message,
                    isCurrent: isCurrent, completion: completion
                )
            }
        }
    }

    private func finish(
        _ notification: DesktopNotification,
        request: Int,
        error: String?,
        isCurrent: @MainActor () -> Bool,
        completion: @MainActor (NotificationAcknowledgment) -> Void
    ) {
        guard isCurrent() else { return }
        if request == latestRequest {
            lastError = error
            onStatusChange?()
        }
        completion(NotificationAcknowledgment(id: notification.id, submitted: error == nil, error: error))
    }
}
