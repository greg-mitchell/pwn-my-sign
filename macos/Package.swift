// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SignDesktop",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "SignDesktop", targets: ["SignDesktop"])],
    targets: [
        .target(name: "SignDesktopCore"),
        .executableTarget(name: "SignDesktop", dependencies: ["SignDesktopCore"]),
        .testTarget(name: "SignDesktopCoreTests", dependencies: ["SignDesktopCore"]),
        .testTarget(name: "SignDesktopTests", dependencies: ["SignDesktop"]),
    ]
)
