// swift-tools-version: 5.9
import Foundation
import PackageDescription

let infoPlist = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    .appendingPathComponent("Sources/nimo/Info.plist").path

let package = Package(
    name: "NimoKit",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "nimo", targets: ["nimo"])],
    targets: [
        .executableTarget(
            name: "nimo", exclude: ["Info.plist"],
            linkerSettings: [.unsafeFlags(["-Xlinker", "-sectcreate", "-Xlinker", "__TEXT",
                                           "-Xlinker", "__info_plist", "-Xlinker", infoPlist])]
        ),
    ]
)
