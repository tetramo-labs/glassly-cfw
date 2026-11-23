// swift-tools-version: 5.9
import Foundation
import PackageDescription

let infoPlist = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    .appendingPathComponent("Sources/memomind/Info.plist").path

let package = Package(
    name: "MemoMindKit",
    platforms: [.macOS(.v13), .iOS(.v15)],
    products: [
        .library(name: "MemoMindCore", targets: ["MemoMindCore"]),
        .library(name: "MemoMindBluetooth", targets: ["MemoMindBluetooth"]),
        .executable(name: "memomind", targets: ["memomind"]),
    ],
    targets: [
        .target(name: "MemoMindCore"),
        .target(name: "MemoMindBluetooth", dependencies: ["MemoMindCore"], exclude: ["README.md"],
                linkerSettings: [.linkedFramework("IOBluetooth", .when(platforms: [.macOS]))]),
        .executableTarget(name: "memomind", dependencies: ["MemoMindCore", "MemoMindBluetooth"],
                          exclude: ["Info.plist"],
                          linkerSettings: [.unsafeFlags(["-Xlinker", "-sectcreate", "-Xlinker", "__TEXT",
                                                         "-Xlinker", "__info_plist", "-Xlinker", infoPlist],
                                                        .when(platforms: [.macOS]))]),
        .testTarget(name: "MemoMindCoreTests", dependencies: ["MemoMindCore"]),
    ]
)
