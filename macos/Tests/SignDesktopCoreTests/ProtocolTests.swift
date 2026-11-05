import Foundation
import SignDesktopCore
import Testing

@Test
func test_decode_when_view_received_returns_workflow_view() throws {
    let record = Data("""
        {"version":1,"type":"view","revision":3,"phase":"update_available",
        "message":"An unsent image is available.","upload_available":true,"retained":false,
        "last_check":"2026-11-05T12:00:00+00:00","last_result":null,"error":null}
        """.utf8)

    let result = try DesktopMessage.decode(record)

    #expect(result == .view(WorkflowView(
        revision: 3, phase: .updateAvailable, message: "An unsent image is available.",
        uploadAvailable: true, lastCheck: "2026-11-05T12:00:00+00:00"
    )))
}

@Test
func test_decode_when_notification_received_returns_request() throws {
    let record = Data("""
        {"version":1,"type":"notification","id":"attempt-button-7","kind":"button",
        "title":"Sign ready to upload","body":"Press the sign's button now."}
        """.utf8)

    let result = try DesktopMessage.decode(record)

    #expect(result == .notification(DesktopNotification(
        id: "attempt-button-7", kind: .button, title: "Sign ready to upload", body: "Press the sign's button now."
    )))
}

@Test(arguments: ["{}", "not json", "{\"version\":1,\"type\":\"unexpected\"}"])
func test_decode_when_record_invalid_raises_protocol_error(_ input: String) {
    let record = Data(input.utf8)

    #expect(throws: DesktopProtocolError.invalidRecord) {
        try DesktopMessage.decode(record)
    }
}

@Test
func test_decode_when_version_unknown_raises_version_error() {
    let record = Data("{\"version\":2,\"type\":\"view\"}".utf8)

    #expect(throws: DesktopProtocolError.unsupportedVersion) {
        try DesktopMessage.decode(record)
    }
}

@Test
func test_decode_when_notification_text_oversized_raises_protocol_error() {
    let title = String(repeating: "x", count: 101)
    let record = Data("""
        {"version":1,"type":"notification","id":"test","kind":"button","title":"\(title)","body":"button"}
        """.utf8)

    #expect(throws: DesktopProtocolError.invalidRecord) {
        try DesktopMessage.decode(record)
    }
}

@Test
func test_encode_when_action_taken_returns_versioned_literal_record() throws {
    let action = ActionRecord(action: .upload, revision: 3)

    let result = try encodeRecord(action)

    #expect(String(decoding: result, as: UTF8.self) ==
        "{\"action\":\"upload\",\"revision\":3,\"type\":\"action\",\"version\":1}\n")
}

@Test
func test_encode_when_notification_submitted_returns_matching_acknowledgment() throws {
    let ack = NotificationAcknowledgment(id: "attempt-button-7", submitted: true)

    let result = try encodeRecord(ack)

    #expect(String(decoding: result, as: UTF8.self) ==
        "{\"error\":null,\"id\":\"attempt-button-7\",\"submitted\":true,\"type\":\"ack\",\"version\":1}\n")
}

@Test
func test_encode_when_record_oversized_raises_size_error() {
    let text = String(repeating: "x", count: 16 * 1024 + 1)

    #expect(throws: DesktopProtocolError.recordTooLarge) {
        try encodeRecord(text)
    }
}
