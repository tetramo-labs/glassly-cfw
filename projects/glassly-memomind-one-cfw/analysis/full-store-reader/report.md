# Full managed-store read profile

The optional `--full-store-reader` profile is compiled at `runtime/build/full-store-read-001/graphics.bin` (54,016 bytes, SHA256 `83290f4c3d300b3f479bcd60865ffb5cc29b55e5887e635fac6f0d0d208d352b`). It requires storage diagnostics, external-tail reader, flash reader, input observer and scene session. The C macro also rejects a full-store reader without diagnostic support. No writer, eraser, reservation or new native API was added.

Query identity is `H001Y-1.0.3.127-full-store-read-v1`. The three device0 ranges remain exact. Device1 now has one disjoint range `[0x500000,0x800000)`, named `managed-store` by the Python client. Its 3,145,728 bytes require 12,288 reads of 256 bytes. Query advertises exactly four ranges. The directory and external-tail names remain available only in the old pinned profiles; they are not redundant subranges of the new profile.

Every read still requires a 256-byte aligned physical offset, length1..256, and containment in a single range. It uses the existing native `04329ad8(device,physical,destination,length)` veneer, releases the request first, uses a zero-initialized 1024-byte owned workspace and32KiB admission headroom, emits bytes only on return0, and frees exactly once. There are no read retries. Native lock/MMIO waits remain noncancellable; host timeout is not a device timeout. The96-byte reader frame and0-byte veneer frame exclude native/interrupt frames and do not establish a whole-task bound.

`capture_memomind_flash.py` needed no changes: its profile/region choices derive from the production client map. Select `--profile H001Y-1.0.3.127-full-store-read-v1 --region managed-store` with an independently known app-header prefix. It verifies the header before the store, fsyncs each chunk before journaling completion, and refuses overwrites and partial resumption. The storage diagnostic client/capture tool now accept an explicit profile limited to diagnostic-v1 or full-store-read-v1; their default remains diagnostic-v1 and strict query matching remains mandatory.

Offline validation passed:

- ASan/UBSan production reader:26,464 range/ownership cases plus failures. This enumerates every aligned page with lengths1 and256; diagnostics are aborting stubs in this host range-only test.
- Actual RV32 code:12 groups/163 calls, including original flash failure/ownership/TLV scenarios, newly admitted middle-store addresses, real diagnostic serialization and fixed RAM/native veneers. Native hardware APIs/RAM are synthetic.
- Actual service/display/input gates:7,955 cases; C entry bodies mocked.
- Production Python/GM replay:117 flash responses plus46 diagnostic responses. Every response is checked through strict profile, fragmentation, correlation and schema checks.
- Seven new Python cases: compiler prerequisite, pinned ELF/blob manifest, old-profile rejection, boundary/type checks, complete 3MiB fake capture with contiguous offsets/header-first/hash, diagnostic profile selection, CLI profile limits. Existing reader and diagnostic client tests also pass.
- Fresh builds of the original flash-reader, external-tail and diagnostic profiles are byte-identical to their pinned blobs. New runtime source hashes show no drift. No existing emulator pins changed.

`report.json` records all12 changed source/test files and hashes, exact old profile hashes and validation paths. No device operation or OTA construction was performed by this task. Full read availability does not establish exclusive ownership, safe writes, boot validation, or native flash-store integration.
