# RX append budget review

**No bound change is adopted or needed for the current mode8 work.** The parent reports that the new bundle profile fits the existing65536-byte limit. This independent read-only review establishes the physical arithmetic and required guard changes for a possible later96KiB profile, such as future mode15 growth. It does not construct or approve a larger firmware image, modify sources, or operate hardware.

## Verified current layout and hypothetical96KiB bound

Independently unpacked `captures/firmware/rect-copy-001/firmware.bin` using the existing strict container decoder. Its SHA256 is `680163e3789831cd3eda89a60b208cb0e85eaa61c46067dbd6d59ff26cee1885`. The decoded app ends in the exact62240-byte `runtime/build/rect-copy-001/graphics.bin`, SHA256 `c2c702f42d92e0b1dccc99e647f4038c391305e0b1ec642ded205c1a6c30dca7`. Checked arithmetic and source identities are in [arithmetic.json](arithmetic.json).

The fixed app allocation is device0 `[001eb000,003eb000)`, including its32-byte header. App body loads at XIP`041eb020`. The appended RX runtime starts at physical`0039bea0`, XIP`0439bea0`, body offset`001b0e80`; the existing source body/padding and fixed gate addresses stay unchanged.

| Runtime bound or artifact | Declared app end, physical | Ordinary OTA erase end | Raw allocation remaining | Allocation remaining after erase |
|---|---|---|---:|---:|
|Current rect62240B|`003ab1c0`|`003ac000`|261696B|258048B|
|Current policy65536B|`003abea0`|`003ac000`|258400B|258048B|
|Hypothetical98304B|`003b3ea0`|`003b4000`|225632B|225280B|

A96KiB append would produce body length1871488 and header+body1871520, both within the existing2097152-byte allocation. The bare physical append interval has323936 bytes available; this is arithmetic, **not an adopted runtime maximum**. Next stock partition begins at`003eb000` and is untouched by these extents.

The historical proposed device0 mutable-tail reservation `[003ab000,003eb000)` is not compatible with this growth: **the currently shipped rect image already overlaps its first448 bytes**. That old proposal must not be treated as an active reservation. Current fixed canary/exclusive store uses device1, with canary sector`007ff000` and store range`00500000..00800000`; it does not reserve the device0 app tail.

The captured bootloader analysis in `analysis/ghidra/boot-validation/report.md` proves the inspected ordinary compressed activation erases `round_up(component_decompressed_length,4096)` from the component destination and programs its actual valid declared output. Header+body length is the component length here. Its declared-body CRC/conditional authentication analysis does not introduce a64KiB extension limit. This is not universal ROM/factory recovery proof and does not make malformed LZMA sizes safe.

Current OTA staging payload is2228650 bytes, rounded2232320, within2482176 (`0x25e000`). A future image's compressed length must be measured after actual recompression. Raw append headroom alone does not prove staging fit; no hypothetical compression result is claimed.

## Where64KiB is enforced

These are conservative software/profile policy gates, distinct from the physical app/staging limits:

* `runtime/graphics/graphics.ld`: RX MEMORY origin`0439bea0`, LENGTH`0x10000`. Service entry remains`0439bea0`, display gate`0439bee0`; zero data/BSS/GOT/initializer assertions remain applicable regardless of budget.
* `scripts/compile_memomind_graphics.py::MAX_BLOB_BYTES`:65536. Both `inspect_elf`'s PT_LOAD end and the emitted blob length check enforce it. The build report records `max_blob_bytes`. Link script selection currently uses the same fixed graphics linker script.
* `scripts/build_memomind_graphics.py::construct_graphics`: accepts only16-aligned blob lengths up to65536. Exclusive-owner and canary constructors call this base constructor, so relaxing only the compiler/linker would still reject a larger blob downstream.
* `scripts/test_compile_memomind_graphics.py`: explicit64KiB ELF-end acceptance and one-byte-overflow rejection. `scripts/test_build_memomind_graphics.py`: exact65536 constructor boundary and65552 rejection, plus expected258400-byte raw headroom. Preserve these as default-profile checks.

Independent physical checks should stay unchanged: `append_memomind_app.py::append_app` pins type20/start/end/load/allocation and requires `new_body_size+32 <= allocation`; updates body length/CRC, metadata length, LZMA sizes, outer counts/CRCs; re-decodes and verifies the original prefix and untouched streams. The base constructor's `_guard_final_bounds` checks raw app size and both compressed staging payload and rounded erase length after repacking. Exclusive-owner and canary layers recheck final bounds and component identity after their edits.

The first diagnostic `build_memomind_runtime.py` has its separate4096-byte policy. Do not relax it. Likewise65535 message lengths,64KiB native asset store, scene heap budgets,512-byte per-function stack guards and fixed flash-reader allowlists are unrelated to append RX length and must not be changed by a larger code profile.

## Required changes only if an observed later build exceeds64KiB

1. Introduce a fixed, explicit96KiB profile selection shared by linker, ELF inspection and blob constructor verification. Keep the default graphics/old profiles at64KiB. Do not trust arbitrary manifest `max_blob_bytes` or an unrestricted caller-supplied limit to grant admission.
2. Use the same entry/display addresses and all existing RX-only/ABI/relocation/static-memory assertions. Changing LENGTH alone must not move the gates. The new budget covers text/rodata only; it grants no SRAM/BSS allocation. Preserve native gp/tp/stack contracts, per-function512B limit and cumulative stack investigation.
3. Propagate that exact new-profile selection through base graphics → exclusive-owner → canary construction and exact reproduction. `memomind_flasher.py` dispatches verification by manifest format; the selected verifier must reproduce the appropriate profile without broadly making every legacy graphics image eligible for96KiB. Preserve previous manifest equality and outputs.
4. Add separate96KiB boundary tests: exact98304 accepted by the selected profile,98305 ELF end and next16-aligned oversized blob rejected; default65536 still accepted/defaultoversize rejected; wrong/missing profile cannot widen. Confirm app-header, metadata, component/LZMA lengths, CRCs and rounded erases agree after reconstruction; preserve untouched stream hashes and original instruction witnesses.
5. Actual emitted ELF must retain one PT_LOAD, RX flags, file==memory length, physical==virtual addresses, expected ilp32f entry, no writable/NOBITS/relocations/undefined symbols. Fixed AUIPC/JALR hook targets remain unchanged; local link ranges and compiler code must still pass actual disassembly/emulation. Existing emulator mappings derive their range from `ENTRY+len(blob)` (`graphics_runtime_emulator_test.py:51–53`, gate harness equivalent), so no fixed64KiB map enlargement was found there. Keep each historical binary pin and add a new build pin rather than replacing it.
6. Native Swift `FirmwareImage.swift` admits fixed release hashes, component tables and lengths; it does not accept any arbitrary96KiB runtime based on this review. A new final release needs its own measured OTA/runtime identities and catalog entry after validation. Preserve all prior release identities. Python live eligibility likewise requires exact constructor reproduction, not this arithmetic report.
7. Recompute final compressed staging usage and physical end/rounded erase end from the actual candidate, retain the offline proof, and run native handler/gate/regression coverage before hardware consideration. Source-size growth alone says nothing about runtime heap/stack or worst-case display latency.

## Scope conclusion

A profile-specific96KiB RX append fits the already established device0 app allocation and inspected ordinary OTA erase path with225280 bytes remaining after its rounded erase. There is no discovered hardware64KiB append boundary. The64KiB limit remains in force for current work; this report records a future option, not a recommendation to enlarge it preemptively. No prior fixed pins, constructor guards, runtime sources, firmware files or device state were changed.
