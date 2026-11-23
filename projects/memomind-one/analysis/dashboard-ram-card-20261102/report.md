# Dashboard card RAM removal boundary

Read-only analysis of stock H001Y1.0.3.127 segment3, SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, base041eb020. New exports use existing app DB `-readOnly -noanalysis`. No source/device/firmware changes. This report is a **cold-boot candidate design**, not permission to free live UI state, and no actual RAM delta was measured.

## Narrowest useful candidate

A3-entry suppression appears sufficient for the **recognized direct state-access set**, without gating every UI function:

| Function | Existing behavior | Candidate |
|---|---|---|
|04264f26|Allocates global card state and root/content containers|Return before allocation; retain02011d2c==NULL from normal BSS initialization.|
|04265060|Immediately reads `state[1]` without checking state|Void no-op, before all dereferences/callback registration.|
|042652e8|Loads `*state` without checking state|Void no-op, before its first global load/dereference.|

Each admits a complete4-byte original instruction span. Suggested gate encoding `01458280` is `c.li a0,0; c.jr ra`, benign for the observed void callers; exact before bytes are in `proof.json`. This is a proposal only, not an edited image. All recognized calls to04265060 ignore its return. Parent caller regression should similarly verify initializer/visibility callers and actual compiled gates.

**Initializer-only removal is unsafe**: native04265060 computes state+4 then dereferences it;042652e8 first loads02011d2c then dereferences it. Preserve these addresses as gated API entries so outside consumers are not left pointing into retired code. No reclaim of this subsystem's instruction bytes is proposed here.

All30 recognized direct readers/writers are exported in `native/` and classified in `reader-classification.json`. Except the initializer and those two unsafe APIs, functions have explicit state-NULL guards or call042642ca, check its zero return, and leave before accessing state. The draw-event callback04264616 also checks state before querying event/object geometry. This is based on actual function control flow, not “no references” alone. The read/reference manager may omit encoded pointers, dynamic aliases, other images or incompletely analyzed code; preserve that bounded scope.

## Exact savings and limits

Init04264f26 calls0434e6da(0x80), zeroes128 bytes, then creates two LVGL base objects via042a6008→042cd8ba. The first is464×350, child of supplied parent; the second440×330, child of the first. At base class04385e10, word+28 is000002ca; allocator042cf7ee uses `(classword>>4)&0xffff` =44 bytes per object. Therefore **216 requested payload bytes** (128+44+44) are definitely avoided if this init otherwise succeeds.

That number excludes allocator headers/rounding, LVGL spec attributes, child arrays, style entries, text buffers and later card/image objects. Root/container dimensions do not imply a framebuffer allocation: these are LVGL objects, not 464×350 pixel buffers. Do not advertise large fixed RAM savings from their geometry. Two created objects also cause child-array/spec/style allocations; their exact total depends on parent state and style/constructor paths. Static216 bytes is a defensible requested-byte lower bound, not a measured free-heap delta.

Larger lazy state allocations found in actual card builders:

| Owner offset | Creator | Requested bytes |
|---|---|---:|
|+14|042653c2|160|
|+18|04265800|84|
|+1c|04265b8c|28|
|+20|0426609e|24|
|+24|042662d8|8|
|+28|04265e4e|208 plus up to4×480 buffers in entries|
|+2c|04266452|56|
|+30|0426663e|32|
|+34|04266d54|84 plus512-byte text buffer and a separate text/object manager|

These are alternative/current-state allocations, not all simultaneously resident. Builders first call destructive clear042642ca. Resource descriptors at owner+38/+44/+50/+5c/+68/+74 hold lazy image data, with optional per-item resource descriptors in the+14 allocation. No actual decoded-resource byte total was established from names. Existing six renderer-retirement gates stop some producers but still invoke fallback04266b06, which can create labels; the3-entry subtree suppression additionally prevents those allocations through the null-state path. It also avoids transient card builder allocations when they are reached, though existing renderer parse temporaries/cache iteration can still occur before calling them.

## Ownership and cleanup

02011d2c is inside the normal startup BSS region (the initialized RAM copy ends02011730; see `../ghidra/append-hook/report.md`). Only init04264f26 and destroy04267550 are recognized writers of the global pointer. Do not infer that an already running system has NULL state: the candidate must boot with initializer suppressed. A live patch that merely gates init leaves previous resources and callbacks alive and does not save RAM.

042642ca is **not a harmless “is initialized” getter**. When state/content exists it frees state-specific allocations, nested resource buffers and text-manager data, removes content children, clears pointers and calls042e2302(0), then returns1. Missing state/content logs and returns0. Suppression relies on its existing NULL early return; do not call it speculatively from a host query. It may affect stock text/stream behavior in the non-null path.

Destroy04267550 checks state, calls042642ca, deletes content/root objects when still parented, frees128-byte state and sets the global NULL. With a cold-boot suppressed initializer it returns without freeing anything; this is the intended idempotent teardown. Child/event/animation callbacks are not created when the builders return through missing state. For already-live objects, deletion order and queued callbacks require a different analysis; this proposal does not attempt hot teardown.

The subsystem is **shared beyond dashboard**. Init has three recognized callers: launcher04273454,0426b686 and042814b8. Their surrounding code builds other UI and invokes card APIs. Cleanup also has callers0426aefc/0426b930 besides launcher destroy. Global suppression intentionally removes card content from those stock flows too; stock visual compatibility is excluded, but their remaining code must remain safe. Do not describe this as launcher-only behavior change.

Callback/state lifetime holes to retain explicitly: some helpers with context parameters do not directly load02011d2c and therefore are absent from the30-reference set. Their callback creation must be unreachable when init is suppressed, or their callers proved independently safe. No live pointer census or exhaustive indirect closure is claimed. Parent actual-caller tests should cover those routes before hardware use.

## Required executable and live checks

Small offline test target: apply the exact3 gates in memory to pinned code, initialize02011d2c to0, and execute all30 state functions with explicit native log/external-call mocks and poison arguments. Assert no object/heap allocation/free, no state dereference, no card callback registration, no state resurrection and correct caller ABI. Missing-state diagnostics may still log; they must not be confused with success or crash. Exercise actual launcher init/destroy continuation and the two other initializer callers with the existing parent/header helpers modeled, plus cold boot, duplicate init/cleanup, fallback and settings/visibility transitions. Dynamic callback helpers require either registration-path closure or dedicated absent-state cases. Do not treat direct no-op entry tests alone as proof all caller paths safe.

If that passes, use a separately reviewed offline candidate and root-owned capture for a same-screen/same-settings heap-before/after comparison: current free, low-water and largest free where actually supported, no subtraction of counters from different boots as a precise allocation measure. Verify graphics scene/diagnostics/input still admit correctly on the active screen, owned deletion/lease works, and the selected other stock transitions do not dereference absent cards. A measured saving above216 bytes can then be attributed carefully to the concrete removed subtree; no amount beyond the static base is claimed now.

## Executable NULL-state harness

`emulate-null-state.py` implements90 actual RV32 cases: all30 recognized state APIs with zero, poison and valid borrowed-pointer argument patterns. It maps the two stock reset-copy ranges and zero BSS, asserts02011d2c is NULL, applies only the three exact witnessed gates in memory, and executes original native function bytes. Real042642ca may execute as the builders' common reset; only02003d5e logging-enabled predicate is mocked to disabled. Every allocator/LVGL/event/I/O/other native code call is an error, not a stubbed success. Writes must stay in the case's own stack; native RAM and borrowed input sentinels must remain unchanged. Gates additionally preserve every GPR excepta0, return0, and perform no data-memory access. All APIs preserve callee saves/gp/tp/SP and return within a fixed instruction budget.

This tests init/destroy entrypoints and original queued-event/read APIs under cold-zero ownership. It intentionally does not execute a complete launcher/other-app constructor with imaginary successful LVGL calls; those constructors still create unrelated UI. It also does not model dynamic aliases or actual callbacks previously registered by a live state. The parent native JIT run is pending when this section was written; do not treat the syntax check as executable proof. Output is analysis JSON only, never a firmware file.
