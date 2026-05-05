// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "StockDashboard",
    platforms: [.iOS(.v17), .macOS(.v14)],
    targets: [
        .executableTarget(
            name: "StockDashboard",
            path: "Sources/StockDashboard"
        )
    ]
)
ㄅ
