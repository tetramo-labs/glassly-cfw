import Foundation

/// Which Unicode scalars the glasses' resource fonts draw, measured through the
/// immediate builtin-text command (mode 15). The native adapter rejects a whole
/// string when one glyph is missing, so a string that draws proves every scalar
/// in it, and a refused string is split until each scalar is known. The OTA
/// does not carry the font partition, so this is the only way to learn the
/// repertoire; the phone's MemoMindOneRenderer pins the result.
public enum FontProbe {
    public enum Resolution: String, Codable, Sendable {
        /// A refused chunk is bisected down to the scalar.
        case exact
        /// A refused chunk is bisected only when one of three sample scalars
        /// draws; otherwise its scalars stay unresolved (treated as absent).
        case sampled
    }

    public struct Block: Equatable, Sendable {
        public let name: String
        public let first: UInt32
        public let last: UInt32
        public let resolution: Resolution

        public init(_ name: String, _ first: UInt32, _ last: UInt32, _ resolution: Resolution = .exact) {
            self.name = name
            self.first = first
            self.last = last
            self.resolution = resolution
        }
    }

    public struct Run: Codable, Equatable, Sendable {
        public let first: UInt32
        public let last: UInt32

        public init(first: UInt32, last: UInt32) {
            self.first = first
            self.last = last
        }
    }

    public struct BlockResult: Codable, Equatable, Sendable {
        public let name: String
        public let first: UInt32
        public let last: UInt32
        public let resolution: Resolution
        public let present: Int
        public let absent: Int
        public let unresolved: Int
        public let requests: Int
    }

    public struct Report: Codable, Equatable, Sendable {
        /// Maximal runs of consecutive scalars that drew.
        public let runs: [Run]
        public let blocks: [BlockResult]
        public let requests: Int
        /// Refused strings: each one costs the stock glyph lookup a miss.
        public let misses: Int
        /// The first scalar not swept because the miss budget ran out, or nil when every block was settled.
        public let nextScalar: UInt32?

        /// The runs as a Swift `[ClosedRange<UInt32>]` body (MemoMindOneRenderer.fontRanges).
        public var swiftRanges: String {
            runs.map { String(format: "0x%04X ... 0x%04X", $0.first, $0.last) }.joined(separator: ", ")
        }

        /// The runs as a Kotlin `List<IntRange>` body.
        public var kotlinRanges: String {
            runs.map { String(format: "0x%04X..0x%04X", $0.first, $0.last) }.joined(separator: ", ")
        }
    }

    public enum Failure: Error, Equatable, LocalizedError {
        /// Plain ASCII was refused: no frame lease, no text command, or no font.
        case asciiRefused
        /// An unassigned scalar drew: the font substitutes a placeholder for
        /// every glyph, so refusals cannot measure anything.
        case unassignedDrawn

        public var errorDescription: String? {
            switch self {
            case .asciiRefused: "The glasses refused plain ASCII text; nothing can be measured"
            case .unassignedDrawn: "The glasses drew an unassigned scalar; the font substitutes placeholders"
            }
        }
    }

    /// Mode 15 carries at most 255 bytes of UTF-8.
    public static let maxStringBytes = 255

    /// What the phone may ask the glasses to draw inline, by Unicode block.
    /// Large ideographic and syllabic blocks are sampled; everything a Latin,
    /// European or symbol-heavy notification can contain is settled exactly.
    public static let blocks: [Block] = [
        Block("Basic Latin", 0x0020, 0x007F),
        Block("Latin-1 Supplement", 0x00A0, 0x00FF),
        Block("Latin Extended-A", 0x0100, 0x017F),
        Block("Latin Extended-B", 0x0180, 0x024F),
        Block("IPA Extensions", 0x0250, 0x02AF),
        Block("Spacing Modifier Letters", 0x02B0, 0x02FF),
        Block("Combining Diacritical Marks", 0x0300, 0x036F),
        Block("Greek and Coptic", 0x0370, 0x03FF),
        Block("Cyrillic", 0x0400, 0x04FF),
        Block("Cyrillic Supplement", 0x0500, 0x052F),
        Block("Armenian", 0x0530, 0x058F),
        Block("Hebrew", 0x0590, 0x05FF),
        Block("Arabic", 0x0600, 0x06FF),
        Block("Devanagari", 0x0900, 0x097F),
        Block("Bengali", 0x0980, 0x09FF),
        Block("Gurmukhi", 0x0A00, 0x0A7F),
        Block("Gujarati", 0x0A80, 0x0AFF),
        Block("Oriya", 0x0B00, 0x0B7F),
        Block("Tamil", 0x0B80, 0x0BFF),
        Block("Telugu", 0x0C00, 0x0C7F),
        Block("Kannada", 0x0C80, 0x0CFF),
        Block("Malayalam", 0x0D00, 0x0D7F),
        Block("Sinhala", 0x0D80, 0x0DFF),
        Block("Thai", 0x0E00, 0x0E7F),
        Block("Lao", 0x0E80, 0x0EFF),
        Block("Tibetan", 0x0F00, 0x0FFF, .sampled),
        Block("Myanmar", 0x1000, 0x109F),
        Block("Georgian", 0x10A0, 0x10FF),
        Block("Hangul Jamo", 0x1100, 0x11FF, .sampled),
        Block("Ethiopic", 0x1200, 0x137F, .sampled),
        Block("Khmer", 0x1780, 0x17FF),
        Block("Latin Extended Additional", 0x1E00, 0x1EFF),
        Block("Greek Extended", 0x1F00, 0x1FFF, .sampled),
        Block("General Punctuation", 0x2000, 0x206F),
        Block("Superscripts and Subscripts", 0x2070, 0x209F),
        Block("Currency Symbols", 0x20A0, 0x20CF),
        Block("Letterlike Symbols", 0x2100, 0x214F),
        Block("Number Forms", 0x2150, 0x218F),
        Block("Arrows", 0x2190, 0x21FF),
        Block("Mathematical Operators", 0x2200, 0x22FF),
        Block("Miscellaneous Technical", 0x2300, 0x23FF),
        Block("Enclosed Alphanumerics", 0x2460, 0x24FF),
        Block("Box Drawing, Blocks and Shapes", 0x2500, 0x25FF),
        Block("Miscellaneous Symbols", 0x2600, 0x26FF),
        Block("Dingbats", 0x2700, 0x27BF),
        Block("Supplemental Arrows and Symbols", 0x27C0, 0x2BFF, .sampled),
        Block("CJK Radicals", 0x2E80, 0x2FDF, .sampled),
        Block("CJK Symbols and Punctuation", 0x3000, 0x303F),
        Block("Hiragana", 0x3040, 0x309F),
        Block("Katakana", 0x30A0, 0x30FF),
        Block("Bopomofo", 0x3100, 0x312F),
        Block("Hangul Compatibility Jamo", 0x3130, 0x318F),
        Block("Katakana and Bopomofo Extensions", 0x31A0, 0x31FF),
        Block("Enclosed CJK Letters and Months", 0x3200, 0x32FF, .sampled),
        Block("CJK Compatibility", 0x3300, 0x33FF, .sampled),
        Block("CJK Unified Ideographs Extension A", 0x3400, 0x4DBF, .sampled),
        Block("CJK Unified Ideographs", 0x4E00, 0x9FFF, .sampled),
        Block("Yi", 0xA000, 0xA4CF, .sampled),
        Block("Hangul Syllables", 0xAC00, 0xD7AF, .sampled),
        Block("CJK Compatibility Ideographs", 0xF900, 0xFAFF, .sampled),
        Block("Alphabetic Presentation Forms", 0xFB00, 0xFB4F),
        Block("Arabic Presentation Forms-A", 0xFB50, 0xFDFF, .sampled),
        Block("Variation Selectors", 0xFE00, 0xFE0F),
        Block("Vertical, Combining Half Marks and CJK Compatibility Forms", 0xFE10, 0xFE6F),
        Block("Arabic Presentation Forms-B", 0xFE70, 0xFEFF, .sampled),
        Block("Halfwidth and Fullwidth Forms", 0xFF00, 0xFFEF),
        Block("Specials", 0xFFF9, 0xFFFD),
        Block("Enclosed Alphanumeric Supplement", 0x1F100, 0x1F1FF, .sampled),
        Block("Miscellaneous Symbols and Pictographs", 0x1F300, 0x1F5FF),
        Block("Emoticons", 0x1F600, 0x1F64F),
        Block("Transport and Map Symbols", 0x1F680, 0x1F6FF),
        Block("Supplemental Symbols and Pictographs", 0x1F900, 0x1F9FF),
        Block("Symbols and Pictographs Extended-A", 0x1FA70, 0x1FAFF, .sampled),
    ]

    /// The scalars of `block` the native decoder accepts as glyph requests: no
    /// controls (bytes 1..31 are x shifts, NUL is invalid), surrogates or
    /// noncharacters.
    public static func scalars(_ block: Block) -> [UInt32] {
        (block.first ... block.last).filter { value in
            value >= 0x20 && !(0xD800 ... 0xDFFF).contains(value) && !(0xFDD0 ... 0xFDEF).contains(value)
                && value & 0xFFFE != 0xFFFE && value <= 0x10FFFF
        }
    }

    public static func utf8(_ scalars: [UInt32]) -> Data {
        var out = Data()
        for value in scalars {
            out.append(contentsOf: Array(String(Unicode.Scalar(value)!).utf8))
        }
        return out
    }

    private static func utf8Count(_ value: UInt32) -> Int {
        value < 0x80 ? 1 : value < 0x800 ? 2 : value < 0x10000 ? 3 : 4
    }

    /// `scalars` in order, packed into strings of at most `maxStringBytes` of UTF-8.
    public static func chunks(_ scalars: [UInt32]) -> [[UInt32]] {
        var out: [[UInt32]] = []
        var current: [UInt32] = []
        var bytes = 0
        for value in scalars {
            let size = utf8Count(value)
            if bytes + size > maxStringBytes {
                out.append(current)
                current = []
                bytes = 0
            }
            current.append(value)
            bytes += size
        }
        if !current.isEmpty {
            out.append(current)
        }
        return out
    }

    /// Sweep `blocks` through `draw`, which sends one mode-15 string and
    /// returns whether the glasses drew it (`ok`) or refused it (`invalid`);
    /// any other outcome should throw. Two calibration strings come first:
    /// ASCII must draw and an unassigned scalar must be refused.
    public static func probe(
        blocks: [Block] = blocks, from: UInt32 = 0, sampled: Bool = false, missBudget: Int = 0,
        draw: (Data) throws -> Bool, progress: ((BlockResult) -> Void)? = nil
    ) throws -> Report {
        // Resuming after a reboot: drop the blocks already settled and clip the one `from` lands in.
        // `sampled` forces the cheap resolution everywhere: an absent block then costs a few misses
        // instead of one per scalar. The stock glyph lookup leaks on every miss and the glasses reboot
        // after about a hundred, so `missBudget` stops the sweep at a block boundary before that.
        let blocks = blocks.compactMap { block -> Block? in
            block.last < from ? nil : Block(block.name, max(block.first, from), block.last, sampled ? .sampled : block.resolution)
        }
        var requests = 0, misses = 0
        func draws(_ scalars: [UInt32]) throws -> Bool {
            requests += 1
            let drew = try draw(utf8(scalars))
            if !drew {
                misses += 1
            }
            return drew
        }
        guard try draws(Array("The quick brown fox 0123456789 ~".unicodeScalars.map(\.value))) else {
            throw Failure.asciiRefused
        }
        guard try !draws([0x0378]) else { throw Failure.unassignedDrawn }

        var present: [UInt32] = []
        var results: [BlockResult] = []
        var nextScalar: UInt32?
        for block in blocks {
            if missBudget > 0, misses >= missBudget {
                nextScalar = block.first
                break
            }
            let before = requests
            var found = 0, absent = 0, unresolved = 0
            /// `scalars` were refused as a whole: settle each one.
            func bisect(_ scalars: [UInt32]) throws {
                if scalars.count == 1 {
                    absent += 1
                    return
                }
                let mid = scalars.count / 2
                for half in [Array(scalars[..<mid]), Array(scalars[mid...])] {
                    if try draws(half) {
                        present.append(contentsOf: half)
                        found += half.count
                    } else {
                        try bisect(half)
                    }
                }
            }
            for chunk in chunks(scalars(block)) {
                if try draws(chunk) {
                    present.append(contentsOf: chunk)
                    found += chunk.count
                    continue
                }
                switch block.resolution {
                case .exact:
                    try bisect(chunk)
                case .sampled:
                    var hit = false
                    for sample in Set([chunk[0], chunk[chunk.count / 2], chunk[chunk.count - 1]]).sorted() {
                        if try draws([sample]) {
                            hit = true
                            break
                        }
                    }
                    if hit {
                        try bisect(chunk)
                    } else {
                        unresolved += chunk.count
                    }
                }
            }
            let result = BlockResult(name: block.name, first: block.first, last: block.last, resolution: block.resolution,
                                     present: found, absent: absent, unresolved: unresolved, requests: requests - before)
            results.append(result)
            progress?(result)
        }
        return Report(runs: runs(present), blocks: results, requests: requests, misses: misses, nextScalar: nextScalar)
    }

    /// Maximal runs of consecutive values.
    public static func runs(_ scalars: [UInt32]) -> [Run] {
        var out: [Run] = []
        for value in Set(scalars).sorted() {
            if let last = out.last, last.last + 1 == value {
                out[out.count - 1] = Run(first: last.first, last: value)
            } else {
                out.append(Run(first: value, last: value))
            }
        }
        return out
    }
}
