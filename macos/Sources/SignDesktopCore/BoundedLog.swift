import Foundation

public final class BoundedLog {
    public let current: URL
    public let previous: URL
    private let maximumBytes: Int
    private let files: FileManager

    public init(directory: URL, maximumBytes: Int = 256 * 1024, files: FileManager = .default) {
        current = directory.appendingPathComponent("desktop.log")
        previous = directory.appendingPathComponent("desktop.previous.log")
        self.maximumBytes = maximumBytes
        self.files = files
    }

    public func append(_ data: Data) throws {
        guard !data.isEmpty else { return }
        try files.createDirectory(at: current.deletingLastPathComponent(), withIntermediateDirectories: true)
        let existingSize: Int
        if files.fileExists(atPath: current.path) {
            let attributes = try files.attributesOfItem(atPath: current.path)
            existingSize = (attributes[.size] as? NSNumber)?.intValue ?? 0
        } else {
            existingSize = 0
        }
        if existingSize > 0 && existingSize + data.count > maximumBytes {
            if files.fileExists(atPath: previous.path) { try files.removeItem(at: previous) }
            try files.moveItem(at: current, to: previous)
        }
        if !files.fileExists(atPath: current.path) {
            try Data().write(to: current, options: .atomic)
        }
        let stream = try FileHandle(forWritingTo: current)
        defer { try? stream.close() }
        try stream.seekToEnd()
        try stream.write(contentsOf: data.suffix(maximumBytes))
    }
}
