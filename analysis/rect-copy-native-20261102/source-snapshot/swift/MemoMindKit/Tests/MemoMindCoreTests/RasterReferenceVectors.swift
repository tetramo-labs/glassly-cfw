// SPDX-License-Identifier: MIT
// Offline dual reference: compiled portable C mm_rle_encode AND unmodified
// extracted G2 TypeScript rleEncode executed with Node22 --experimental-strip-types.
// Both independently agreed for every fixture. No Python/C/Node execution in Swift tests.
// G2 revision1a6db4fd75de202a96599cc8f9f12fa721e7c3ce. License: LICENSE.
// tests/g2_compat/upstream/demos/video-bench.ts SHA256 c9188190724da6f7ba28fb145e26f9f4df3128b80fc60aab0ecda81739a84131
// tests/g2_compat/upstream/patches/zlib_glue.c SHA256 94722d8cace415d9e6edb160e282ea654befca75d6d376499d7aa1c627e3d3f6
// runtime/portable/rle.c SHA256 61a5ba6f0285867b426655f3c40b1aaefe50ef414b79f8241b1f18be5576a062
enum RasterReferenceVectors {
    static let runs: [(count: Int, rleHex: String)] = [
        (1, "150a00ffff0a00ffff0a00ffff0a005234"),
        (2, "250a00ffff0a00ffff0a00ffff0a005134"),
        (3, "350a00ffff0a00ffff0a00ffff0a005034"),
        (4, "450a00ffff0a00ffff0a00ffff0a004f34"),
        (5, "550a00ffff0a00ffff0a00ffff0a004e34"),
        (6, "650a00ffff0a00ffff0a00ffff0a004d34"),
        (7, "750a00ffff0a00ffff0a00ffff0a004c34"),
        (8, "850a00ffff0a00ffff0a00ffff0a004b34"),
        (9, "950a00ffff0a00ffff0a00ffff0a004a34"),
        (10, "a50a00ffff0a00ffff0a00ffff0a004934"),
        (11, "b50a00ffff0a00ffff0a00ffff0a004834"),
        (12, "c50a00ffff0a00ffff0a00ffff0a004734"),
        (13, "d50a00ffff0a00ffff0a00ffff0a004634"),
        (14, "e50a00ffff0a00ffff0a00ffff0a004534"),
        (15, "f50a00ffff0a00ffff0a00ffff0a004434"),
        (16, "05100a00ffff0a00ffff0a00ffff0a004334"),
        (17, "05110a00ffff0a00ffff0a00ffff0a004234"),
        (254, "05fe0a00ffff0a00ffff0a00ffff0a005533"),
        (255, "05ff0a00ffff0a00ffff0a00ffff0a005433"),
        (256, "050000010a00ffff0a00ffff0a00ffff0a005333"),
        (257, "050001010a00ffff0a00ffff0a00ffff0a005233"),
        (65534, "0500feff0a00ffff0a00ffff0a005434"),
        (65535, "0500ffff0a00ffff0a00ffff0a005334"),
        (65536, "0500ffff150a00ffff0a00ffff0a005234"),
        (131_070, "0500ffff0500ffff0a00ffff0a005334"),
        (131_071, "0500ffff0500ffff150a00ffff0a005234"),
    ]
    static let colors: [String] = [
        "0000ffff0000ffff0000ffff00005334",
        "0100ffff0100ffff0100ffff01005334",
        "0200ffff0200ffff0200ffff02005334",
        "0300ffff0300ffff0300ffff03005334",
        "0400ffff0400ffff0400ffff04005334",
        "0500ffff0500ffff0500ffff05005334",
        "0600ffff0600ffff0600ffff06005334",
        "0700ffff0700ffff0700ffff07005334",
        "0800ffff0800ffff0800ffff08005334",
        "0900ffff0900ffff0900ffff09005334",
        "0a00ffff0a00ffff0a00ffff0a005334",
        "0b00ffff0b00ffff0b00ffff0b005334",
        "0c00ffff0c00ffff0c00ffff0c005334",
        "0d00ffff0d00ffff0d00ffff0d005334",
        "0e00ffff0e00ffff0e00ffff0e005334",
        "0f00ffff0f00ffff0f00ffff0f005334",
    ]
    static let crossRow = "f001100211"
}

extension RasterReferenceVectors {
    static let capacityFullSHA256 = "f56c4a5c4a731875ee56bc334019d18f51fe732c89e255eea348730f78220dae"
    static let capacityBoxSHA256 = "89b56550df8b2926afe632b43a22ddc2c494fcef2faf22d3e75edd05a22d9aba"
}
