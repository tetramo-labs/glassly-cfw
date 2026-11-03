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
Native record, sanitizer, service-gate and catalog tests pass. The clean required offline suite passes all138 stages, including235 Python
and137 Swift tests, with no source drift or missing mapped stages. The final
run is `analysis/regression-20261103-v6-final`; the curated result is
`regression-verification.json`. Eighteen required upstream suite/integration
entries remain incomplete; offline success is not full hardware parity.

Historical native fixture runtime hashes are now explicitly bound to fresh
builds only after blob and source verification. Stock-image pins and test bodies
are unchanged by that binding. The revision6 empty-shapes diagnostic assertion
was separately updated to expect presentation and verify unchanged pixels.
Earlier failed reports are retained locally; the final run re-executes every
stage and reuses no earlier passes.

No hardware acceptance is inferred from offline checks. The connection search
uses a 660-second deadline and new captures for each attempt. It stops on a
successful preflight or a verified boot header, preserving partial failures.
Glassly bundling is explicitly allowed before device verification.

The 660-second search made22 unsuccessful preflight attempts; the last ended
after651.57 seconds. A later23rd attempt also timed out. No revision6 transfer
started. Glassly commit `09fb43a97a` bundles the exact candidate and both mobile
clients renew ownership through control leases, without empty-shape keepalives.
