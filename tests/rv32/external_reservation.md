# Native external-store reservation regression

Run from the repository root with the pinned environment:

```sh
.tools/rv32-tests-venv/bin/python tests/rv32/external_reservation_emulator_test.py --output /tmp/memomind-reservation-new-run
```

The output directory must not exist and must be outside `analysis/ghidra`.
Missing dependencies, Unicorn versions other than 2.1.4, disabled assertions,
source drift and a constructor recipe mismatch fail the stage. `report.json`
records success or failure, partial case results, command and source hashes.
No firmware image is emitted and no hardware API is invoked.

The runner preserves the names, order and predicates of all 46 cases in the
SHA-pinned `analysis/ghidra/external-reservation-review/boundary-tests.json`:
23 cases for the production constructor's 1 MiB reservation and 23 cases for
the reviewed 512 KiB reference. Each profile covers erased/valid/old-capacity
mounts, valid last-page and invalid reserved-page entries, genuine bad-sector
bits in reserved/directory/active sectors, three I/O wrappers with four boundary
requests each, and whole-store reset with and without an active bad sector.
The real 1 MiB `build_memomind_storage.PATCHES` tuple must exactly match all
11 reviewed address/before/after/purpose tuples. The native body is patched
only in emulator memory; its resulting digest must match the frozen review.

`native_store_mount.py` extracts the native mount harness from
`analysis/ghidra/native-store-inventory/inventory.py` and takes explicit body,
capacity and bitmap inputs. The production RV32 mount/CRC/directory checks
execute from stock application body SHA-256
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.
Directory reads and badmap retrieval are synthetic callbacks; mutation or
package-validation callbacks are forbidden during read-only mount. Whole-reset
and wrapper cases execute native code with explicitly mocked flash/KV/cache/
critical-section/availability callbacks. Reset read/erase mocks assert every
physical range remains inside the reduced device-1 store. `callback_hook_events`
counts mocked entry/return hooks, not instructions; the mount helper's
`instructions` field counts all emulated instruction hooks.

Passing this suite does not prove physical flash topology, concurrent ownership,
power-loss behavior, preservation under stock OTA/recovery, or every native
format/compaction/package-verifier path. It establishes the reviewed capacity
boundaries under stated mocks. Source witnesses for all eleven edits are
required even when a site's full native caller is outside these cases.
