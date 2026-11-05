import Foundation
import SignDesktopCore
import Testing

@Test
func test_append_when_diagnostics_arrive_returns_written_log() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let log = BoundedLog(directory: directory, maximumBytes: 10)

    try log.append(Data("hello".utf8))

    #expect(try Data(contentsOf: log.current) == Data("hello".utf8))
}

@Test
func test_append_when_log_would_overflow_returns_previous_log() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let log = BoundedLog(directory: directory, maximumBytes: 10)
    try log.append(Data("previous".utf8))

    try log.append(Data("current".utf8))

    #expect(try Data(contentsOf: log.previous) == Data("previous".utf8))
}

@Test
func test_append_when_chunk_exceeds_limit_returns_only_bounded_tail() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let log = BoundedLog(directory: directory, maximumBytes: 5)

    try log.append(Data("123456789".utf8))

    #expect(try Data(contentsOf: log.current) == Data("56789".utf8))
}

@Test
func test_append_when_log_rotates_again_returns_only_latest_previous_log() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let log = BoundedLog(directory: directory, maximumBytes: 5)
    try log.append(Data("first".utf8))
    try log.append(Data("second".utf8))

    try log.append(Data("third".utf8))

    #expect(try Data(contentsOf: log.previous) == Data("econd".utf8))
}

@Test
func test_append_when_directory_is_file_raises_file_error() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    try Data("occupied".utf8).write(to: directory)
    let log = BoundedLog(directory: directory)

    #expect(throws: (any Error).self) { try log.append(Data("diagnostic".utf8)) }
}
