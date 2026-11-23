# Read-only text release admission review

The corrected script passes the current-source transformation review. No production files were written and no candidate was admitted by this review. The final firmware candidate and its actual pins remain pending independent construction/verification.

A blocking cloning bug was identified in the initial script: the range from the first Raster fixture method to the first RectCopy fixture method also contained both existing Bundle methods. Cloning that range duplicated the Bundle tests. Root changed the end marker to the first Bundle fixture method, restricting the clone to the two Raster methods. Both saved dry runs inspect this corrected script; run-002 adds stronger full-source reversal checks.

The in-memory dry run uses synthetic digest/size values and the actual current catalog/test source. It executes only the source transformation portion, with Path reads/writes restricted to an in-memory dictionary. It proves:

- Exactly one new text catalog entry, stream variant and digest constant are inserted.
- Removing only the intended text additions recovers the previous catalog source byte-for-byte, including all six earlier release entries, stream pins, validation code and ordering.
- The test method count grows from18 to20, adding exactly the required Text fixture test and repaired-CRC/raw-runtime rejection test. All20 names are unique.
- Removing only the new text property and two methods recovers the previous test source byte-for-byte. Existing test method bodies and assertions are preserved.
- The two new methods contain text paths/pins and no stale Raster/Bundle release names, digest variables or substituted numeric pins.

Read-only inspection also confirms admission requires `verify_canary` reconstruction equality plus exact proof equality, decompression through `unpack_ota`, unchanged packed components1/2/4/5/6 versus the raster release, and the expected256-byte app header. It pins the complete image,150-byte OTA header, metadata stream and app stream. The validator's profile remains the existing fixed canary profile; the comment explicitly disclaims boot proof. Catalog and test content is assembled before either source write. Template substitution is checked for unresolved IMAGE/HEADER placeholders, but template compilation remains a separate root check.

The optimized-Python guard was executed with `python3 -O`: it rejected before imports/file access with the explicit assertion requirement. Normal admission was not executed. The source transform remains tied to exact current textual markers; a future source rearrangement needs another review. Two output source writes are sequential rather than atomic, so an IO failure could leave only the catalog updated; this is a recoverable local source-edit concern and not device execution. Required compilation/tests must still pass before use.

Evidence: admission-review/run-002/report.json, generated-catalog.swift.txt and generated-tests.swift.txt (synthetic only), optimized.stderr. Script/source SHA256s are pinned in admission-review.json. The dry-run helper is admission-review/check_transform.py and requires a new output directory.
