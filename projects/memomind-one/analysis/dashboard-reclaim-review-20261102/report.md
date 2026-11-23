# Independent launcher reclamation review

Stock segment3 SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, base041eb020. This pass reads parent evidence in `../dashboard-reclaim-20261102`, existing native/CFW source, and exports the existing shared app DB with `-readOnly -noanalysis`. No production, firmware, device or persistent project edits. New findings/exports are confined to this directory.

## Decision

Replacing launcher callbacks while retaining descriptor identity is a sound direction, but **five descriptor substitutions alone do not prove the launcher band reusable**. Two external paths still enter launcher internals: shared go-home0427253a, and calibration04273ee6→04272960. Their closure operates on launcher objects0200fc40/44 and state0200fc74/78. A replacement that leaves those objects null while retaining those functions is not established safe. Preserve valid minimal objects and the relevant behavior, or deliberately replace the external functions' launcher-specific arms. User authorization to discard stock dashboard behavior permits the latter, but the new contracts and all callers still need executable validation.

The recognized band is `[04270738,04273e90)`,57 functions and14168 defined bytes, not the wider initial inventory interval through04274100. Calibration begins at04273e90 and is outside this reclamation claim. There is no proven whole-band free extent or quantified heap saving yet.

## External entry closure

`range-refs.txt` scans recognized references to every address inside the band (including interiors), and `all-interior-literals.json` scans every byte offset of the pinned body for little-endian32-bit values inside it. Combined with the parent's inventory/raw-entry scan, recognized external roots are:

| Root | External route | Required handling |
|---|---|---|
|0427253a|32 recognized call/parameter sites, including main dispatcher, notifications, app callbacks and calibration|Preserve exported entry or replace with compatible callback. Retaining it retains internal04271cda and possible04271640 paths.|
|04272664|main dispatcher0425b38a,042986a8,042671a6|Returns bit31 of0200fc74; preserve address/defined status semantics.|
|0427267a|04298522|Returns whether either top two bits of0200fc74 is set; same requirement.|
|04272960|calibration04273ee6 at04273f04|Do not omit. Calls04272920(200), sets bit30/time/deadline and invokes042726ba.|
|Five descriptor callbacks|RAM0200fc7c initialized from XIP0439a38c|Replace exact initializer slots; preserve descriptor identity and other fields.|
|Six renderer entries through nine table slots|0436312c..04363173|Indirect table path must be removed/retargeted or retained; absence of individual Ghidra xrefs is insufficient.|

`known-preserve-closure.json` computes recognized direct in-band callees from the first four roots:15 functions/1434 bytes. This is a **lower bound**, not complete liveness: callback parameters, table calls, unresolved indirects and external callees returning into the band must be added. Notably042726ba passes042707ac as an asynchronous callback; that function is outside this direct-only closure. A direct graph alone undercounts precisely this sort of retained route.

The apparent external04273734 references from04262c8e are **descriptor-mediated**, not hardwired calls to the old handler. At04262df6 the caller loads `a5=*(a0+0x2c)` then calls it at04262dfe; the second route likewise loads descriptor+2c. Replacing initializer0439a3b8 redirects these routes after normal startup copying. The first route has **no null callback guard**, so retain a non-null replacement even if its behavior is an intentional no-op. The dispatcher owns/releases incoming message TLVs after the callback through042e85ae; a minimal replacement must not free or retain that borrowed payload.

Table proof:04271fb2 scans9 rows of8 bytes starting0436312c, compares byte0, loads callback+4 at04272192 and invokes it at0427219a. Keys2/4/5/6/7/8/9/10/11 target042711a4/04270f98/04270dd2/04270dd2/04270c82/04270c82/04270ace/042708e2/042708e2. These six renderers cover contiguous `[042708e2,042713bc)` =2778 bytes. This is a useful narrow candidate only after the indexed dispatcher and all producers/callback paths are proved retired. The table itself and its data/assets are not automatically free.

The raw all-interior scan found the same14 even code-pointer literals (9 table slots+5 descriptor slots). The additional41 values are odd address-like instruction words, e.g. LUI encodings endingb7/37; they are not aligned RV32 instruction entry pointers. This check does not exclude addresses built by arithmetic, encoded/compressed tables, live RAM mutations, ROM/B-core pointers or incomplete disassembly. No new recognized external interior instruction entry was found in the Ghidra reference scan. That is bounded negative evidence, not universal exclusivity.

## Concrete retained-path hazards

0427253a checks top app identity and high state bits; launcher path calls04271cda(0), welcome path forwards the argument to04274b12. 04271cda calls04271640 when underlying app is AI-QA; otherwise cancels queued class11/event2 and calls042a88fe. 04271640 clears bit31, calls shared visibility helpers, and passes0200fc44/40 into LVGL visibility/opacity operations. Merely keeping the go-home function's bytes does not preserve valid objects.

04273ee6 is outside launcher band: for keys5000/5001 it calls04272960, reads bit31, registers0427253a as calibration callback, then may switch apps. 04272960→04272920→042726ba also accesses0200fc44/40 and invokes shared UI functions. `closure/function-042726ba.c` has multiple setting-dependent paths; zeroing state is not a proof every path avoids objects. `042a65fc` directly calls LVGL style lookup using its object parameter, without its own null guard. No admission based on null placeholder objects.

A safe minimal replacement needs an explicit policy for these external interfaces: either compatible root/header objects with their state valid through every caller, or replacement routines preserving ABI while intentionally suppressing removed dashboard behavior. Keep the welcome arm of go-home if welcome remains registered; suppressing all of it changes first-run/onboarding routing beyond a dashboard-only retirement.

## Minimal-parent ABI and lifecycle

Descriptor0200fc7c is0x3c bytes before next descriptor0200fcb8. Registry0425d922 retains descriptor pointer identity; multiple routing paths compare that identity. Retain names, identity, class/priority/active fields, startup copy and registry wiring. Startup0425bd9e registers launcher plus other apps and chooses welcome versus launcher according to setting5205; a launcher-only implementation must not assume first boot always selects launcher.

| Offset / XIP word | Callback ABI | Minimal behavior / ownership |
|---|---|---|
|+08 /0439a394|`void init(app_descriptor*)`|App manager passes descriptor in a0; stock uses descriptor+38 borrowed entry context. No allocation-failure return protocol exists at the caller. Initialize only owned objects/state on display worker; do not treat a return code as admission.|
|+10 /0439a39c|`void destroy(void)` (no argument contract required)|Manager calls without setting an owner argument. Release only resources created by replacement, and clear pointers. Never invoke stock destroy after skipping stock init.|
|+20 /0439a3ac|`void tick(void)`|0425db94 invokes it on base/active overlays/current top; no forced argument. No-op is structurally viable if no pending owned housekeeping.|
|+28 /0439a3b4|`bool event(app*,uint32 kind,const void *payload)`|0425dbfc moves incoming payload into a2; a0 descriptor/a1 kind. Borrowed synchronous payload. Return0 when intentionally unconsumed; returning1 suppresses later routing.|
|+2c /0439a3b8|`void message(app*,uint32 event,void *borrowed_tlvs,uint32 flags)`|04262c8e sets a3=0 on known route. Do not free/retain caller payload. Keep non-null.|

All are RV32 code pointers with ordinary integer ABI; preserve gp/tp/callee saves and16-byte stack alignment in compiled replacements. Existing read-only exports establish interface, not a compiled replacement's correctness.

**The actual CFW parent is the LVGL active screen, not launcher0200fc40.** `runtime/graphics/native.c:screen()` calls042d01b2→042ccc62. `launcher_active()` separately compares both0425db22 and0425daf8 to0200fc7c. Stock042a5f24 creates a600x350 child of that active screen and saves it as0200fc40; its header child is0200fc44. It does not create/replace the active LVGL screen. Thus a CFW parent can continue using the existing active screen while omitting dashboard children, provided the external helper contracts above are changed coherently. Do not delete the shared active screen to tear down only the launcher.

Stock destroy unregisters21 settings listeners, removes callbacks/timers/delayed messages, frees shared widget state via0426fc4c/04267550, deletes0200fc40 and nulls0200fc40/44. Skipping stock init and then calling stock destroy would mix ownership. A replacement should register no old listeners and must not free uncreated shared widget state. Build it for reboot initialization, not hot swapping out a currently live launcher while its async callbacks remain queued.

Current CFW owner/diagnostic registry objects are siblings of the dashboard container on the active screen. Deleting0200fc40 does not delete them. Graphics20ms timer removes owner if launcher identity/parent/lease changes; input and diagnostics have their own documented ownership. Minimal launcher destroy must either rely on a reviewed bounded period before those timers clean up, or synchronously request existing owned cleanup with reentrancy proof. Do not assume dashboard container deletion supplies the CFW DELETE events. Screen destruction does delete both, but is a different operation and affects other apps.

## Flash and heap are separate

Replacing descriptor pointers alone changes reachability, not memory capacity. Reclaiming flash requires exact candidate intervals, all inbound/direct/indirect closure, no fallthrough/interior branches and constructor overlap/hash checks before reusing bytes. Retain byte-identical sentinels around shared helpers and calibration. App code itself is XIP; its14KiB band is not14KiB live heap.

Omitting dashboard init can avoid LVGL children, cache-decoded payloads, listeners and timers, but the bytes saved depend on settings/data/lifecycle. Dashboard cache code at0429dxxx has KV-backed variable allocations and GM routes; launcher retirement alone does not retire that cache subsystem. Resources/fonts/bitmap tables can be shared by other apps. No asset span or heap byte count is approved from labels or one caller set. The known fixed launcher globals remain at0200fc40..0200fc7b and may have external consumers; do not turn them into arbitrary CFW RAM merely because visual dashboard code was removed.

## Bounded next action and acceptance

Implement an offline **minimal launcher profile without reusing any old launcher bytes first**. Change the five exact descriptor initializer words; define the go-home/suspend/getter compatibility boundary explicitly; preserve the stock active screen and descriptor. Tests should execute actual app-manager callers with the new callbacks, plus calibration and representative notification/back callbacks, welcome selection, duplicate init/destroy, incoming borrowed TLV cleanup, active-screen destruction, CFW graphics/input/diagnostics owner cleanup and low-allocation failure. Poison deleted old objects and assert that callbacks/queued events do not touch them. Verify stock byte witnesses and exact app-body layout.

Only after that profile's retired paths are bounded and tested, nominate narrow independent code clusters such as the six renderers, and prove zero remaining incoming routes in the **patched** image including constructor-generated references. Preserve historical tests as reference; do not claim stock dashboard compatibility. A measured free-heap/largest-block before/after snapshot can establish practical heap benefit separately from verified flash reuse.

## Narrower first cut: fail the six card renderers at their original entries

After inspecting the six actual renderer exports in `cards/`, **entry-preserving failure stubs are the narrower offline candidate than replacing the descriptor**. ABI is `int renderer(const record *const *borrowed_records, int count)`; each original renderer creates/parses its own temporary structures, frees those allocations on both success/failure, and returns0 when drawn or-1 when no usable parsed item. The caller's pointer array is stack-local and is not transferred to the renderer. An immediate-1 stub creates no temporary allocation to clean up and need not inspect either argument.

At0427219a dispatcher calls the renderer; `0427219c beq a0,zero,042722e6` returns directly on0. **Nonzero enters042721a0→04266b06(type)**, then diagnostic logging and epilogue. Thus a-1 stub takes the existing failure/fallback path rather than pretending a card was rendered. The dispatcher's preparatory cache iteration and any earlier setting/state effects still occur. It does not retire dashboard producer/cache code or establish a heap byte saving. This is an intentional removal of card rendering while preserving the larger parent lifecycle and shared callers.

Preserving all six original entry addresses also preserves the nine existing table slots and any exact-entry aliases missed by Ghidra. It still does not protect unknown interior entry points. The pinned full-body literal/reference scan found no recognized external interior entry into these functions; actual patched caller tests remain required before using their tails.

| Original entry | Function end exclusive | Safe whole-instruction gate span | Tail after gate | Tail bytes |
|---|---|---:|---|---:|
|042708e2|04270ace|6|042708e8..04270ace|486|
|04270ace|04270c82|6|04270ad4..04270c82|430|
|04270c82|04270dd2|4|04270c86..04270dd2|332|
|04270dd2|04270f98|4|04270dd6..04270f98|450|
|04270f98|042711a4|6|04270f9e..042711a4|518|
|042711a4|042713bc|6|042711aa..042713bc|530|

Total candidate tail space2746 bytes across six fragments. Four entries start with a2-byte compressed stack adjustment followed by a4-byte store; a4-byte-only overwrite splits that old store. For clean instruction-span guards use `7d5582800100` (c.li a0,-1; c.jr ra; c.nop) over their complete6-byte prologue span; the two short-store entries admit `7d558280` over4 bytes. Splitting an unreachable instruction is not in itself proof of runtime failure, but treating entry+4 as an original instruction boundary would be false. All tail placements need their own alignment, section-length, fallthrough and overlap checks; some tails start2mod4, which is legal RV32C but not necessarily a desired data alignment.

The offline test should execute the **actual04271fb2 caller** for all9 keys and representative trigger branches, with real table pointers and the exact candidate gates, explicit mocks only for external cache/UI APIs. Assert exactly one failure fallback for reached renderers, no renderer allocation/free, preserved caller callee-save/gp/tp/stack, no tail execution, unchanged table/descriptor/neighbor bytes, borrowed-record sentinels and null/unavailable early paths. This makes the narrow cut concrete without introducing minimal-parent ownership changes. Independent all-address interior scans and code-pointer-table checks should be rerun against the reconstructed candidate; runtime payload references into a reclaimed fragment must themselves be accounted for.
