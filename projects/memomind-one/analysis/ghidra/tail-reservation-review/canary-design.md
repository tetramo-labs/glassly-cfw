# Bounded app-tail canary design (proposal only)

A **single-sector experiment is feasible as the next empirical step**, after read-only inventory and a reviewed fixed-range runtime command. It can test native erase/program/readback and reset acceptance for that sector and build. It cannot certify all256KiB as free, prove every stock owner's behavior, or establish production transactional storage. No experiment was run here.

## Fixed extent and admission

Use device0 sector **`[003d1000,003d2000)`** (XIP`[043d1000,043d2000)`), interior to proposed tail`[003ab000,003eb000)`. It is4KiB aligned and deliberately not64KiB aligned. Retain neighboring guard sectors`[003d0000,003d1000)` and`[003d2000,003d3000)` for comparison. Neither the current declared body nor its normal rounded OTA erase extent reaches these addresses.

First extend **read-only** acquisition to inventory the whole proposed tail and guard sectors in existing256-byte chunks, with repeated read equality and hashes. Read the live app header and both bootmaps again. Require valid selected map, type20 physical`001eb000`, allocation`200000`, current body length matching the header, no overlapping non-app map record, and:

```
body_start = 001eb020
body_end = body_start + declared_body_length   // checked arithmetic
round_up(body_end,4096) <= 003ab000
```

For the current captured build, body end`003a8560`, rounded end`003a9000`; future canary runtime builds must recompute this. Reserving256KiB leaves only**10,912 bytes** of app growth from the captured build before the tail. Every future constructor must enforce the new limit (`body_length <= 0x1bffe0`), not merely the old2MiB allocation. Raw body and compressed staging bounds are independent.

Require the canary sector to be exactly4096 bytes of`ff`, with a saved host backup and digest. If it is non-erased or changes between reads, **stop and identify that content/owner**. Do not silently preserve-and-overwrite an unknown stock sector. An erased/stable sector is supporting evidence, not proof of non-ownership. Guard sectors may contain data; save them exactly and never erase them. Maintain the original bootmap/header snapshots and known-good OTA separately.

## Native boundary

The new profile should accept no caller-selected device, address, erase size, driver address, or arbitrary program blob. Compile in this sector and exact program limit. Use an explicit versioned operation and session nonce, one request at a time; unexpected operation/order, malformed length, map/layout mismatch or lower failure rejects. The canary pattern should be a fixed256-byte layout containing a magic, version, physical address, nonce and checksum, generated/copied into owned SRAM. Do not use borrowed TLV bytes or XIP data as the program source.

Use normal task-context `erase(0,003d1000,4096)` and `program(0,003d1000,owned_pattern,256)` from[abi.md](abi.md). Avoid`04329b90`, raw controller calls, lock-mode changes, driver reinitialization, protection manipulation and startup hooks. Acquire owned scratch with the existing nonasserting allocator before mutation; use a small stack frame and preserve normal native ABI/gp. Release the request before entering native flash calls after copying validated scalar inputs. The flash mutex is acquired by the native wrapper, not around the custom workflow.

Native calls have no cancellation deadline. A lost response means uncertain completion, so reconnect and read state rather than blindly retrying. Nonzero driver status, mismatched readback, guard change or disconnect stops normal progression. Return exact status and observed readback only after the native call completes; do not report enqueue or command reception as write success. Response allocation itself can fail, so host recovery must rely on subsequent readback, not a presumed completed response.

## Proposed sequence

1. Complete/read back the baseline inventory and live layout checks. No OTA transfer, plugin install, factory/ANC diagnostic writes, or other custom flash workload should run concurrently. Native locking serializes calls but does not arbitrate logical multi-operation ownership.
2. Erase only the fixed sector; read all16 chunks and require all`ff`. Compare both guard sectors with their snapshots.
3. Program the256-byte canary page once. Read the entire4KiB sector; require the exact pattern in its first page and`ff` afterward. Recompare guards and app header/bootmap identities. Save full raw evidence and hashes before resetting.
4. Request the established ordinary reset only after successful readback and completed native operations. Reconnect, confirm the expected runtime/build, reacquire header/maps and the sector. Require the canary to persist unchanged, guards unchanged, and ordinary function checks to pass. Exercise a bounded representative set of normal settings/UI/Bluetooth actions, then reread; record precisely which paths were exercised.
5. Restore the original all-erased sector with a second fixed4KiB erase. Read it and both guards; require exact baseline equality. Reset again, reconnect and repeat equality/function checks. The host's original backup remains available even though restoration here requires no program operation.

If reset fails, restoration through the same application is not guaranteed to be reachable. A successful prior OTA does not establish a hardware recovery path. The design minimizes modified bytes and excludes declared code; it does not eliminate that residual experimental risk or claim a proven fallback recovery interface.

## What the result would and would not prove

A pass would establish this particular sector's controller erase/program behavior, unchanged guards, normal-reset acceptance and no observed use during the recorded workload. It would justify a subsequent explicit CFW reservation/backend design against the pinned image. It would not prove all64 sectors unowned, OTA preservation, wear tolerance, atomicity during power loss, other-core/ROM/factory exclusions, or full G2 dynamic-cache semantics.

A persistent cache still needs a versioned directory, malformed/partial-state rejection, bounded logical capacity, replacement/spare sectors, and commit/recovery rules. Exactly256KiB of physical space does not supply256KiB of arbitrary logical data plus transactional metadata and scratch. OTA may invalidate the cache; that policy is acceptable if detected explicitly. No fake plugin entry or native bad-sector bit is involved in this app-tail experiment.
