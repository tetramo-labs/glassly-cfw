# Native Swift firmware eligibility

`EligibleFirmware.load(data:expectedSHA256:)` is the only public construction path. It returns immutable `data`, canonical lowercase `sha256`, `modified`, `profile` and `releaseName` values. It is not `Decodable` and has no public initializer. The caller must supply an explicit64-character ASCII hexadecimal SHA256; uppercase hex is accepted, whitespace/non-ASCII is rejected. The bytes are copied into owned storage before validation so a caller's `bytesNoCopy` buffer cannot later change the validated image.

The internal catalog currently contains exactly:

| Release | Bytes | SHA256 | Classification |
|---|---:|---|---|
| stock-1.0.3.127-jhv3-release |2185697|`08ff64abb1fc66c12779bbc2f34d44eeabf8a9433bb0089ca842245b64acf712`|Captured vendor stock|
| exclusive-store-reader-001 |2223753|`270dfe85438e6ff0f904a09215e15419292e16b8c7bbc36aafec50543c780c55`|Modified reader with six CUS8 refusal gates, historically boot/header/profile verified|
| flash-canary-001 |2226788|`79a4158c5d82b97c248d0dd2b7e366df03206393c1c2a7275677b8985d81398a`|Reviewed offline canary at initial catalog admission; later hardware evidence is separate|
| raster-commands-001 |2227971|`b89a6adab63bb8e09c2b05a261af4ae9b80f5b7fc4e81c15c016dc457dfba261`|Reviewed offline modes3/6 release; exact image hardware boot/raster behavior untested|

Other canary candidates, raw runtime blobs, other runtime variants and arbitrary CRC-correct images are excluded. No JSON file, environment variable, supplied manifest, expected hash alone or command-line opt-in adds a release. `FirmwareCatalogProvenance.json` is human/audit evidence, not an input to eligibility. Adding a release requires a reviewed code change, literal pins, updated provenance and required actual-fixture tests.

Swift performs native CryptoKit SHA256 and its own CRC32/IEEE implementation. It checks exact catalog length, whole-image hash, ME envelope signature/version, BE payload length/CRC, inner magic, LE table CRC, combined compressed-stream CRC, exactly one metadata plus six component streams, bounded stream lengths, component allocation limits, LZMA properties/dictionary/declared lengths and no bytes before the final CRC left unaccounted for. The150-byte container header and all seven compressed-stream hashes/sizes/ranges also match compiled pins. Opaque header words are pinned as bytes rather than assigned invented semantics.

This is intentionally **not a full Swift constructor or decompressor port**. Swift does not decode LZMA, verify decoded component body CRCs/partition records, reconstruct patches, discover signature enforcement or prove safe future boot. Exact catalog bytes were previously decoded/reconstructed by the offline Python tools. The reader image has separate historical native boot/header/profile evidence; the canary and raster entries record offline reconstruction and mocked-native validation at their initial catalog admission. The provenance file records these source paths/hashes and decoded results explicitly. The runtime validator invokes no subprocess, Python interpreter, external executable or network operation.

`FirmwareImageTests` includes independent SHA/CRC vectors and a separate bitwise CRC reference for adversarial containers, truncation/overflow/range/stream-header cases, caller-buffer mutation, and a syntactically valid but fake-compressed/CRC-correct image that the catalog rejects. All four actual firmware fixtures are required and found by ascending from the test source path; absence fails tests rather than skipping them. The generic internal container inspector is testable, but it cannot construct public eligibility.

Run from any working directory:

```sh
swift test --package-path /path/to/repo/swift/MemoMindKit --filter FirmwareImageTests
```

For `flash-canary-001`, `verify_canary` reproduced every output byte, the exact manifest and the stored construction proof from text-patched source SHA256 `941022530ba1e091af2a65983e6c51d9e9d077fb606b631f2892b05d9eea6876` and runtime blob SHA256 `c30da32f8759627aa85247757d0ccae67466a730b5802827246fe2d91a699992`. The fixed constructor applies the six owner gates and three registry carve edits; this update performs no OTA or device operation. The catalog's exact canary pin is a reviewed admission decision, **not a claim of hardware validation**. Its native flash writer is present but starting it remains a separate explicit operation with its own backup, preflight and authorization requirements. Constructor flags such as `live_flashing_enabled` do not constitute boot evidence.

The library targets Apple platforms with CryptoKit. No claim is made that historical eligibility replaces device identity checks, explicit write authorization, connection/lifetime checks, OTA correlation or a recovery procedure; those belong to the OTA transaction and caller.

For `raster-commands-001`, the same fixed canary constructor was independently replayed from the pinned text source and runtime61392B SHA256 `4f4d211d885560a65da97c4a5d0b6a7d34231a254e7c8181507e3f2a9aaa5328`. Every output byte, manifest field and stored verification result matched. This retains the full reader/diagnostics/input/canary implementation, six owner-refusal gates and three exact boot-clear/heap carve edits; mode3/6 is the only added command scope. It remains a hardware-untested raster release at admission; earlier canary hardware evidence does not establish this new image's boot or raster behavior. The unchanged reader profile string is `H001Y-1.0.3.127-flash-canary-v1`; `releaseName` and whole-image SHA distinguish the new release. The150-byte container header hash and256-byte expected app-header prefix are different artifacts and are recorded separately. Native8192-byte message and64KiB scene-store limits remain in place; mode3's highbit selects the first/left bbox on the single display.
