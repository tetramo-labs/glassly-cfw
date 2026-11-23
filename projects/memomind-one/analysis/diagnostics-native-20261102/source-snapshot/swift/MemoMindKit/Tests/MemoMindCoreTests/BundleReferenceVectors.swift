// SPDX-License-Identifier: MIT
// struct.pack fixtures checked by verbatim pinned G2mode8 dispatch; child calls mocked.
// SourceSHA256 94722d8cace415d9e6edb160e282ea654befca75d6d376499d7aa1c627e3d3f6
// Evidence analysis/bundle-swift-20261102/reference.json
enum BundleReferenceVectors {
    static let cases: [(name: String, children: [String], wire: String)] = [
        ("empty", [], "0800"),
        ("geometry", ["2400"], "080102002400"),
        ("copy-then-delta", ["096400b4003f001f006500b5003f001f00", "0300000101010080"], "08021100096400b4003f001f006500b5003f001f0008000300000101010080"),
        ("reset-geometry", ["290000010000", "2400"], "0802060029000001000002002400"),
        ("highbit-image", ["93010000000000000000"], "08010a0093010000000000000000"),
    ]
}
