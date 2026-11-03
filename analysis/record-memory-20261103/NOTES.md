# Revision 6: record scratch lifetime and empty raster takeover

The 6,144-byte record reply buffer now exists only during process/finish. The
JSON parser copies it before finish frees it; closing the owner during a command
still defers session destruction until finish. Allocation failure before parser
entry executes no command. The host sanitizer tests cover all seven allocation
sites, verify scratch release between calls, and retain dictionary/cleanup tests.
On RV32 the session structure loses 6,140 bytes (array replaced by one pointer).
Allocator rounding and actual device heap savings remain unmeasured.

Standalone empty mode36/164 now goes through the regular raster dispatcher,
preserving pixels while taking ownership from an animated scene. This matches
G2 image_dispatch's takeover before immediate drawing. The old special case
only renewed the native lease and left animations running. The native RISC-V
regression verifies the frame stops changing after takeover for both aliases.

Build recipe: full revision5 compile flags with `--cfw-revision 6`, output
`build-06`; image `image-06`. Runtime remains 96,128 bytes in the existing
98,304-byte allocation. Image validation leaves the other five components exact.
Native record, sanitizer, service-gate and catalog tests pass. The complete
required offline suite is also running at `analysis/regression-20261103-v6`;
its separate final report determines broader regression status.

No hardware acceptance is inferred from offline checks. The connection search
uses a 660-second deadline and new captures for each attempt. It stops on a
successful preflight or a verified boot header, preserving partial failures.
Glassly bundling is explicitly allowed before device verification.
