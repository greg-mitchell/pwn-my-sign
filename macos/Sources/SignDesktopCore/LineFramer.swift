import Foundation

public struct LineFramer {
    private var partial = Data()
    public let maximumBytes: Int

    public init(maximumBytes: Int = 16 * 1024) {
        self.maximumBytes = maximumBytes
    }

    public mutating func append(_ data: Data) throws -> [Data] {
        var records: [Data] = []
        for byte in data {
            if byte == 10 {
                records.append(partial)
                partial.removeAll(keepingCapacity: true)
            } else {
                guard partial.count < maximumBytes else {
                    partial.removeAll(keepingCapacity: false)
                    throw DesktopProtocolError.recordTooLarge
                }
                partial.append(byte)
            }
        }
        return records
    }

    public func finish() throws {
        guard partial.isEmpty else { throw DesktopProtocolError.incompleteRecord }
    }
}
