import Foundation
import SignDesktopCore
import UserNotifications

@MainActor
final class NativeNotifications: NSObject, NotificationClient, UNUserNotificationCenterDelegate {
    private let center: UNUserNotificationCenter

    init(center: UNUserNotificationCenter = .current()) {
        self.center = center
        super.init()
        center.delegate = self
    }

    func settings(_ completion: @escaping @MainActor (NotificationPermission) -> Void) {
        center.getNotificationSettings { settings in
            let permission: NotificationPermission
            switch settings.authorizationStatus {
            case .notDetermined: permission = .notDetermined
            case .denied: permission = .denied
            case .authorized, .provisional, .ephemeral:
                permission = settings.alertSetting == .enabled && settings.alertStyle != .none
                    ? .authorized : .alertsDisabled
            @unknown default: permission = .denied
            }
            Task { @MainActor in completion(permission) }
        }
    }

    func requestAuthorization(_ completion: @escaping @MainActor (NotificationFailure?) -> Void) {
        center.requestAuthorization(options: [.alert, .sound]) { _, error in
            let failure = error.map { NotificationFailure($0.localizedDescription) }
            Task { @MainActor in completion(failure) }
        }
    }

    func submit(
        _ notification: DesktopNotification,
        completion: @escaping @MainActor (NotificationFailure?) -> Void
    ) {
        let content = UNMutableNotificationContent()
        content.title = notification.title
        content.body = notification.body
        content.sound = .default
        let request = UNNotificationRequest(identifier: notification.id, content: content, trigger: nil)
        center.add(request) { error in
            let failure = error.map { NotificationFailure($0.localizedDescription) }
            Task { @MainActor in completion(failure) }
        }
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list, .sound])
    }
}
