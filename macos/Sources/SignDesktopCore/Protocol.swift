import Foundation

public enum DesktopProtocolError: Error, Equatable, LocalizedError {
    case invalidRecord
    case unsupportedVersion
    case recordTooLarge
    case incompleteRecord

    public var errorDescription: String? {
        switch self {
        case .invalidRecord: "The workflow sent an invalid status record."
        case .unsupportedVersion: "The app and workflow use different protocol versions. Rebuild the app."
        case .recordTooLarge: "A workflow status record exceeded the size limit."
        case .incompleteRecord: "The workflow closed its status stream in the middle of a record."
        }
    }
}

public enum WorkflowPhase: String, Decodable, Sendable {
    case starting, checking, completed, skipped, sending
    case upToDate = "up_to_date"
    case updateAvailable = "update_available"
    case preparingUpload = "preparing_upload"
    case waitingForButton = "waiting_for_button"
    case pollFailed = "poll_failed"
    case uploadFailed = "upload_failed"

    public var isBusy: Bool {
        switch self {
        case .starting, .checking, .preparingUpload, .waitingForButton, .sending: true
        default: false
        }
    }
}

public struct WorkflowView: Decodable, Equatable, Sendable {
    public let revision: Int
    public let phase: WorkflowPhase
    public let message: String
    public let uploadAvailable: Bool
    public let retained: Bool
    public let lastCheck: String?
    public let lastResult: String?
    public let error: String?

    enum CodingKeys: String, CodingKey {
        case revision, phase, message, retained, error
        case uploadAvailable = "upload_available"
        case lastCheck = "last_check"
        case lastResult = "last_result"
    }

    public init(
        revision: Int, phase: WorkflowPhase, message: String,
        uploadAvailable: Bool = false, retained: Bool = false,
        lastCheck: String? = nil, lastResult: String? = nil, error: String? = nil
    ) {
        self.revision = revision
        self.phase = phase
        self.message = message
        self.uploadAvailable = uploadAvailable
        self.retained = retained
        self.lastCheck = lastCheck
        self.lastResult = lastResult
        self.error = error
    }

    fileprivate var isValid: Bool {
        revision >= 0 && message.count <= 1000 && (lastCheck?.count ?? 0) <= 1000
            && (lastResult?.count ?? 0) <= 1000 && (error?.count ?? 0) <= 1000
    }
}

public enum NotificationKind: String, Decodable, Sendable {
    case updateAvailable = "update_available"
    case button, completed, failed
}

public struct DesktopNotification: Decodable, Equatable, Sendable {
    public let id: String
    public let kind: NotificationKind
    public let title: String
    public let body: String

    public init(id: String, kind: NotificationKind, title: String, body: String) {
        self.id = id
        self.kind = kind
        self.title = title
        self.body = body
    }

    fileprivate var isValid: Bool {
        !id.isEmpty && id.count <= 128 && title.count <= 100 && body.count <= 1000
    }
}

public enum DesktopMessage: Equatable, Sendable {
    case view(WorkflowView)
    case notification(DesktopNotification)

    public static func decode(_ data: Data) throws -> DesktopMessage {
        struct Header: Decodable { let version: Int; let type: String }
        let decoder = JSONDecoder()
        do {
            let header = try decoder.decode(Header.self, from: data)
            guard header.version == 1 else { throw DesktopProtocolError.unsupportedVersion }
            switch header.type {
            case "view":
                let view = try decoder.decode(WorkflowView.self, from: data)
                guard view.isValid else { throw DesktopProtocolError.invalidRecord }
                return .view(view)
            case "notification":
                let notification = try decoder.decode(DesktopNotification.self, from: data)
                guard notification.isValid else { throw DesktopProtocolError.invalidRecord }
                return .notification(notification)
            default:
                throw DesktopProtocolError.invalidRecord
            }
        } catch let error as DesktopProtocolError {
            throw error
        } catch {
            throw DesktopProtocolError.invalidRecord
        }
    }
}

public enum MenuAction: String, Encodable, Sendable { case upload, check }

public struct ActionRecord: Encodable, Equatable, Sendable {
    public let version = 1
    public let type = "action"
    public let action: MenuAction
    public let revision: Int

    public init(action: MenuAction, revision: Int) {
        self.action = action
        self.revision = revision
    }
}

public struct NotificationAcknowledgment: Encodable, Equatable, Sendable {
    public let version = 1
    public let type = "ack"
    public let id: String
    public let submitted: Bool
    public let error: String?

    public init(id: String, submitted: Bool, error: String? = nil) {
        self.id = id
        self.submitted = submitted
        self.error = error.map { String($0.prefix(1000)) }
    }

    public func encode(to encoder: any Encoder) throws {
        enum CodingKeys: String, CodingKey { case version, type, id, submitted, error }
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(version, forKey: .version)
        try container.encode(type, forKey: .type)
        try container.encode(id, forKey: .id)
        try container.encode(submitted, forKey: .submitted)
        if let error { try container.encode(error, forKey: .error) }
        else { try container.encodeNil(forKey: .error) }
    }
}

public func encodeRecord<T: Encodable>(_ record: T) throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    var data = try encoder.encode(record)
    data.append(10)
    guard data.count <= 16 * 1024 else { throw DesktopProtocolError.recordTooLarge }
    return data
}
