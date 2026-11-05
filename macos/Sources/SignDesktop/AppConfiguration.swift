import Foundation

struct AppConfiguration {
    let executable: URL
    let configuration: URL
    let logDirectory: URL

    init(info: [String: Any]) throws {
        guard let executable = info["MySignExecutable"] as? String, executable.hasPrefix("/"),
              let configuration = info["MySignConfiguration"] as? String, configuration.hasPrefix("/")
        else {
            throw ConfigurationError.missingPaths
        }
        self.executable = URL(fileURLWithPath: executable)
        self.configuration = URL(fileURLWithPath: configuration)
        logDirectory = self.configuration.deletingLastPathComponent().appendingPathComponent("desktop-logs")
    }
}

enum ConfigurationError: Error, LocalizedError {
    case missingPaths

    var errorDescription: String? {
        "This app is missing its workflow paths. Build it with mysign workflow desktop-build."
    }
}
