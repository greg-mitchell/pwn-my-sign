import Foundation
import SignDesktopCore
import Testing

@Test
func test_append_when_multiple_records_arrive_returns_all_complete_records() throws {
    var framing = LineFramer()

    let records = try framing.append(Data("first\nsecond\n".utf8))

    #expect(records == [Data("first".utf8), Data("second".utf8)])
}

@Test
func test_append_when_record_is_split_returns_reassembled_record() throws {
    var framing = LineFramer()
    _ = try framing.append(Data("first".utf8))

    let records = try framing.append(Data(" record\n".utf8))

    #expect(records == [Data("first record".utf8)])
}

@Test
func test_append_when_utf8_character_is_split_returns_original_bytes() throws {
    var framing = LineFramer()
    let bytes = Data("Sign ✓\n".utf8)
    _ = try framing.append(bytes.prefix(6))

    let records = try framing.append(bytes.suffix(from: 6))

    #expect(records == [Data("Sign ✓".utf8)])
}

@Test
func test_append_when_record_exceeds_limit_raises_size_error() throws {
    var framing = LineFramer(maximumBytes: 5)

    #expect(throws: DesktopProtocolError.recordTooLarge) {
        try framing.append(Data("123456\n".utf8))
    }
}

@Test
func test_append_when_record_matches_limit_returns_record() throws {
    var framing = LineFramer(maximumBytes: 5)

    let records = try framing.append(Data("12345\n".utf8))

    #expect(records == [Data("12345".utf8)])
}

@Test
func test_finish_when_partial_record_remains_raises_incomplete_error() throws {
    var framing = LineFramer()
    _ = try framing.append(Data("unfinished".utf8))

    #expect(throws: DesktopProtocolError.incompleteRecord) {
        try framing.finish()
    }
}

@Test
func test_finish_when_records_complete_returns_without_error() throws {
    var framing = LineFramer()
    _ = try framing.append(Data("complete\n".utf8))

    #expect(throws: Never.self) { try framing.finish() }
}
