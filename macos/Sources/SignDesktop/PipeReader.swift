import Dispatch
import Foundation

@MainActor
final class PipeReader {
    private let source: any DispatchSourceRead

    init(handle: FileHandle, receive: @escaping @MainActor (Data) -> Void) {
        source = DispatchSource.makeReadSource(fileDescriptor: handle.fileDescriptor, queue: .main)
        source.setEventHandler { [weak self] in
            MainActor.assumeIsolated {
                guard let self else { return }
                let bytes = handle.availableData
                if bytes.isEmpty { self.cancel() }
                receive(bytes)
            }
        }
        // Dispatch must release the descriptor before it can safely be closed or reused.
        source.setCancelHandler { try? handle.close() }
        source.resume()
    }

    deinit { source.cancel() }

    func cancel() {
        source.cancel()
    }
}
