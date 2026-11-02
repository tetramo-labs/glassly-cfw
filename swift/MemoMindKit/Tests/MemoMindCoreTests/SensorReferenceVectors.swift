// SPDX-License-Identifier: MIT
// Independently struct.pack encoded and checked by pinned original C control branches.
// Evidence: analysis/sensor-swift-20261102/reference.json
enum SensorReferenceVectors {
    static let cases: [(name: String, kind: String, values: [Int], wire: String)] = [
        ("compass-stop", "compassStop", [], "0a00"),
        ("compass-default", "compassDefault", [], "0a01"),
        ("compass-0-0", "compassConfig", [0, 0], "0a0200000000"),
        ("compass-49-65535", "compassConfig", [49, 65535], "0a023100ffff"),
        ("compass-50-5", "compassConfig", [50, 5], "0a0232000500"),
        ("compass-1000-5", "compassConfig", [1000, 5], "0a02e8030500"),
        ("compass-2000-256", "compassConfig", [2000, 256], "0a02d0070001"),
        ("compass-2001-360", "compassConfig", [2001, 360], "0a02d1076801"),
        ("compass-65535-65535", "compassConfig", [65535, 65535], "0a02ffffffff"),
        ("als-query", "alsQuery", [], "1000"),
        ("als-stop", "alsStop", [], "1002"),
        ("als-500-1-5000-0", "alsStart", [500, 1, 5000, 0], "100100f40101008813"),
        ("als-500-1-5000-1", "alsStart", [500, 1, 5000, 1], "100101f40101008813"),
        ("als-0-0-0-0", "alsStart", [0, 0, 0, 0], "100100000000000000"),
        ("als-99-65535-65535-1", "alsStart", [99, 65535, 65535, 1], "1001016300ffffffff"),
        ("als-100-1-1-0", "alsStart", [100, 1, 1, 0], "100100640001000100"),
        ("als-5000-256-5000-1", "alsStart", [5000, 256, 5000, 1], "100101881300018813"),
        ("als-5001-0-0-1", "alsStart", [5001, 0, 0, 1], "100101891300000000"),
        ("als-65535-65535-65535-0", "alsStart", [65535, 65535, 65535, 0], "100100ffffffffffff"),
    ]
}
