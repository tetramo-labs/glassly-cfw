// SPDX-License-Identifier: MIT
// Independent struct.pack LE16 fixtures verified by the verbatim pinned G2mode9 branch.
// SourceSHA256 94722d8cace415d9e6edb160e282ea654befca75d6d376499d7aa1c627e3d3f6
// Evidence: analysis/rect-copy-swift-20261102/reference.json
enum RectangleCopyVectors {
    static let cases: [(name: String, source: [Int], destination: [Int], hex: String)] = [
        ("odd", [1, 3, 7, 5], [11, 13, 7, 5], "0901000300070005000b000d0007000500"),
        ("full", [0, 0, 600, 350], [0, 0, 600, 350], "090000000058025e010000000058025e01"),
        ("last-pixel", [599, 349, 1, 1], [0, 0, 1, 1], "0957025d01010001000000000001000100"),
        ("high-bytes", [256, 257, 257, 3], [0, 0, 257, 3], "0900010101010103000000000001010300"),
        ("overlap", [0, 0, 10, 10], [1, 1, 10, 10], "09000000000a000a00010001000a000a00"),
        ("self", [3, 5, 9, 7], [3, 5, 9, 7], "0903000500090007000300050009000700"),
    ]
}
