# Bundle verifier and admission read-only review

All22 synthetic positive/fault cases pass against the corrected verifier. The positive trace contains exact reset/HIDE/final-scratch replies, repeated settled tags, the late-failure case, nativeMTU-split GM requests, intermediateACKframes, the B8/checker visual bundle, empty/highbit/trailing bundle, four malformed bundles, lease renewal and clear. It models a timeout-based300second hold; no actual device, elapsed hold or user confirmation is represented.

Three findings were fixed by root and independently checked: settled notifications could precede their originating primary reply/request; scene replyHex was less strict than the helper; and request transmissions could overlap while responses arrived in the expected order. The last issue was reproduced as accepted inrun-003. The final verifier rejects a new transmit submission while a business request remains pending, and the same22case suite passes inrun-004. ExactABI and tag types, notification event/order/source, final scratch correlation, packet completion, canonical hex, late-failure status, expected pixels and hold conditions have negative coverage.

The admission script syntax and all current source-rewrite markers are valid. Its exact reconstruction/proof/unchanged component/header checks precede literal catalog admission; catalog and test texts are assembled before writes. Optimized Python is refused before mutation. The reviewer did not run the ordinary admission script or modify production sources.

Explicit limit: fragmentACKs are parsed/checksummed, but this verifier does not independently enforce their head/order. Production GMSession does enforce intermediate ACKheads. Future notifications, continuous pixel retention and physical single presentation are not proven. Final hardware and visual results remain separate.

The artifact-source hashes and exact case outcomes are inreport.json andrun-004/report.json. Earlier runs are preserved: run-001 had an ineffective uppercase test vector, corrected to use alphabetic hex; run-003 records the real pre-fix overlapping-request acceptance.
