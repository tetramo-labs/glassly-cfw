# Independent dashboard-island constructor review

Reviewed `scripts/build_memomind_dashboard_reclaim.py`, SHA256 `93d7c4536b1817eea9e5633964f18191ee5a204a1856b76cec08a2058b4073e8`, against the frozen native findings in `../dashboard-reclaim-review-20261102/report.md`. No production changes, candidate file or device action in this review. Source/hash pin applies to this exact revision; later changes need a delta review.

**No concrete constructor/layout blocker found.** This supports an offline candidate and actual-caller regression, not live admission or a claim that no hidden interior references exist. The independent executable check is `check-constructor.py`; all42 assertions passed in `checks.json`. It imports the production constructor, reconstructs only in memory, and never writes a firmware image. It is not RV32 emulation; the parent's actual04271fb2 caller tests supply separate behavioral evidence.

## Fixed image and interval enforcement

The public constructor requires exact installed diagnostic OTA SHA256 `a9c9b36e062066e5b363b625c9205c18753b905624708068b79da5b912b8d917`. Each of six original whole renderer bodies and its complete first-instruction span is independently witnessed before editing, even with an empty payload. Entry failures use `7d558280` (c.li a0,-1; c.jr ra) and append compressed nop for the four6-byte gates. Gates preserve the actual original6/6/4/4/6/6-byte instruction boundaries; no stack adjustment, heap, input dereference, native call or changed gp/tp occurs in a gate.

Six tail capacities are486/430/332/450/518/530 =2746 bytes. Strict dictionary keys must be exact integer entries (Boolean keys rejected), values immutable `bytes`, lengths even and individually bounded. Unknown islands, odd/oversized/mutable payloads and any renderer byte drift are rejected. The helper accepts a body and enforces the six renderer hashes; it is intentionally less source-restrictive than the public OTA constructor, so callers needing image provenance must use `construct_dashboard_reclaim`, not infer it from `apply_renderer_islands` alone.

The body length does not change. The six functions are contiguous, so the constructor's unchanged-prefix/suffix check plus fixed per-function loop covers the complete edited union. Table0436312c..04363173, launcher descriptor initializer0439a38c..0439a3c7, shared navigation, calibration and installed appended runtime are outside it and remain byte-identical. Component3 header CRC/compression/outer checksums are updated by the established repacker; metadata and the other five component streams retain both raw and packed bytes. Final source-independent parser verification and existing application/staging bounds remain enforced.

Empty-tail reconstruction in memory produced2229111 bytes, SHA256 `0317abeac1d8b545216152b2d14220bdb91b99a14f5293c8444696769fa1af39`, app body SHA256 `2032f108fbd611506921c52573099024625e77c2e06536df85b7371fe6651240`. These hashes record deterministic offline evidence only, not admission to any flasher catalog.

## Caller and executable limits

The native contract remains the frozen one: actual indexed dispatcher04271fb2 calls original entry addresses through all9 slots; return-1 takes04266b06(type) fallback. Inputs are borrowed; renderer parsing allocations do not exist when the entry returns immediately. No descriptor replacement/minimal-parent lifetime change is introduced. Preparatory cache iteration, dashboard producers, later fallback behavior and the existing parent lifecycle remain active.

Zero tail fill is executable-address padding containing illegal RV32 zero instruction encodings; it is **not** an MPU execute-disable region, writable storage or a safe no-op sled. It can help make an unexpected stale interior jump fail, but does not establish such jumps impossible. Actual payload link address, alignment, instructions/relocations/imports, return convention, fallthrough, cross-fragment calls, new pointer sources, stack/heap and lifetime require separate checks. Enforcing even length is appropriate for RV32C byte placement; it is not a general ELF/ABI validator and the documentation correctly requires prelinked payloads. Empty islands are not automatically callable. No larger contiguous capacity is represented.

The required behavioral review remains actual dispatcher execution for all9type rows, direct gate calls, retained caller state and borrowed-input sentinels, failure paths and no tail execution. Raw literal/interior reference scans are bounded evidence, especially for computed, encoded or other-image pointers. The constructor does not pretend to close those gaps.

## Scope wording

Manifest fields explicitly say `live_flashing_enabled:false`, `hardware_validated:false`, `dashboard_fully_removed:false`. Verification requires exact reconstructed manifest equality, rejecting an edited live flag or payload metadata. Proof limitations correctly state fragmented RX only, no heap saving/full dashboard removal, independent payload validation, residual computed-interior uncertainty and no live catalog admission. No live registry/catalog is modified by this constructor.

One nonblocking wording improvement was sent to the parent: the module phrase “establishes byte ownership” is stronger than what this constructor alone proves. “Enforces fixed byte witnesses and edit intervals” describes it precisely. The explicit proof limitations already constrain the operational claim. No additional permissions or hardware sequence are proposed by this review.
