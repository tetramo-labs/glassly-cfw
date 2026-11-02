# Status strip and header RAM retirement review

The smallest supported boot-only status/header slice is three fixed entry gates: disable status initializer `0426f2c2`, header initializer `04268336`, and header updater `042683f0`. Combined with the separately reviewed card three-gate slice, actual RV32 execution passed140 native calls with cold owner state, at incoming SP modulo16 values0 and8. Only the logging-enabled predicate is mocked false. No allocator, free, LVGL operation, resource loader, timer, flash or KV operation may execute; unreviewed instructions are rejected. This is bounded native closure evidence, not a whole boot/hardware proof.

The **status/header requested-allocation lower bound is1,224 bytes**: four eagerly allocated status context blocks total984, one status LVGL object44, and omitted header label116/image80. This excludes allocator overhead, child arrays, styles, text copies, decoded resources and the selected status style. It is not a measured free-heap delta. The44-byte header container created by the launcher outside the gated initializer remains and is not counted. The card agent's separate216-byte lower bound is not included here.

## Exact gates and boot state

All replacements are `01458280`: `c.li a0,0; ret`. The earlier provisional message's `80820100` was a transposed encoding error caught immediately by emulation and is **not** this recipe. No firmware file/device was changed during analysis.

|Entry|Original4bytes / complete instructions|Caller ABI and closure|
|---|---|---|
|0426f2c2|411122c4 / `c.addi sp,-16; c.swsp s0,8(sp)`|void initializer, borrowed parent in a0; recognized callers04273454,0426b686,042814b8. All three deliberately omit this UI.|
|04268336|011106ce / `c.addi sp,-32; c.swsp ra,28(sp)`|void initializer, borrowed header parent in a0; only recognized caller04273454.|
|042683f0|411122c6 / `c.addi sp,-16; c.swsp s0,12(sp)`|void updater; callers04273266 and04272a36. Existing code already null-guards label; explicit gate retires it.|

Zero return is ignored by these void callers; other argument registers, callee saves, gp/tp, SP and RA are preserved. Gate execution does not access memory or adjust stack. Existing source witnesses are pinned to stock segment3 SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.

Normal startup clears `[02011878,0205e128)` (the existing canary profile extends the endpoint256bytes). Every omitted owner/context/resource global below is inside that interval. This is **not a hot-unload recipe**: it neither frees already-live objects nor cancels callbacks from an already-initialized old UI. Existing globals are retained at their addresses; none is reassigned as CFW scratch.

## Status closure and exact allocation requests

`0426f2c2` creates a136×340 side container stored at02011d84, then calls all four context allocators. It is not the600×34 topbar. Context initializers only allocate and zero their block:

|Context|Initializer|Requested bytes|Cleanup|Active visual builder|
|---|---|---:|---|---|
|02011d50|0426898a|232|04269780→042696da|style1:04268f02|
|02011d74|0426ca26|232|0426d7de→0426d726|style2:0426cee4|
|02011d58|04269d04|320|0426a886→0426a7ca|style3:0426a1be|
|02011d24|042637cc|200|0426423c→042641a8|style4:04263c56|

`status-init-refs.txt` shows the sole recognized caller of each context allocator is the gated initializer. `context-refs.txt` finds only allocator/cleanup writes to the four context pointers. `all-context-function-refs.txt` covers all32 context users: recognized incoming routes stay inside the status/style closure. There is no recognized alternate allocator or direct external style construction route.

Root02011d84 is set only by init and cleared by cleanup. Style selector02015890 is set only by0426f320/0426fb4a after successful root validation. Battery-mode flags02015894 are set only after root validation. With the initializer gated at cold boot, these remain zero; style-specific tick/battery/update dispatch does not select a style.

|Public native route|Cold-zero behavior|
|---|---|
|0426f126,0426f320,0426fb4a,0426f78c|root null→return/log; no style assignment, builder or callback registration|
|0426f414,0426f492,0426f4c8,0426f56e|root null→return/log; no object/animation/reorder call|
|0426f5bc,0426f60c,0426f73c,0426fa20|style0 selects no style callback; flags0 prevents battery-only object arm|
|0426f3c0/0426f3ea|write only four respective scalar settings bytes; all eight setters exported and executed|
|0426f8ee|does not set status selection fields at style0; forwards to card0426502a, which independently null-guards card owner|
|0426f96e|if batchdepth nonzero sets pending scalar; otherwise null root avoidsLVGL, then card04265042 independently null-guards card owner|
|0426f998/0426f9b2|batchdepth/pending scalars only; deferred refresh follows above null guards|
|0426fc40|existing no-op|
|0426fc4c|null root/resource/context checks; cleanup of absent contexts does nothing|

The settings writes at02011d28/29,02011d54/55,02011d5c/5d,02011d78/79 and batchdepth/pending02011d88/89 remain intentional. They are not heap allocations. The harness asserts their exact values for setting updates and batch transitions, while owner/style/resource pointers remain zero. Card-related forwarding remains valid with an existing card too; this status slice does not claim to retire card functionality by itself.

Style switches call0426f126, which destroys the previous selected visual tree and decoded resources before constructing the new style. **Do not sum all four visual trees as simultaneously resident.** The four context blocks themselves remain allocated until complete status cleanup.

## LVGL and decoded-resource costs

Class constructor042cf7ee extracts instance size from classword+28 bits4..19. Raw stock class bytes establish44-byte ordinary object at04385e10,80-byte image at04385b38,116-byte label at04385bd0. Constructor additionally grows parent child-pointer arrays; a parent's first child may allocate36-byte spec attributes042cdf0c. Styles, callbacks, label text, allocator rounding/metadata and nested helper allocations are additional costs.

Direct creation sites on each first-construction branch yield these **base-instance lower bounds**, before resources and other costs:

|Selected style|Objects / images / labels|Base instance bytes|
|---|---|---:|
|1|17 /6 /4|1692|
|2|14 /10 /5|1996|
|3|8 /5 /4|1216|
|4|9 /5 /4|1260|

These are derived static first-construction paths, not measured hardware allocation totals. Exact decoded-image sizes cannot be inferred from object display dimensions.

Resource042a4f0e fetches by name through04260db8, may expand an outer container, then allocates retained decoded bytes and places the owning data pointer in descriptor+8. For the compressed palette formats7 and9 it requests respectively `8 + ceil(width/8)*height` and `64 + ceil(width/2)*height`, where width/height come from the actual resource header; other admitted uncompressed formats copy `resource_length-4`. Cleanup042a5766 frees descriptor+8 under the image utility lock and zeroes the12-byte descriptor. Temporary resource-provider references and decompression allocations are separate; shared provider caches are not claimed exclusive to dashboard.

Styles load ten named digit resources each, plus charge and style-specific assets. Style1 includes clock hands; style2 includes time background and percentage; style3 includes eight cstyle icon slots (including duplicate schedule name); style4 includes charge. The four style cleanup functions explicitly release these buffers. Thus decoded pixels can dominate the1–2KiB base objects, but absent actual resource headers/live descriptor lengths, no numerical payload savings is claimed.

## Header-specific ownership

The launcher itself creates600×34 header container0200fc44. Gated04268336 clears its children, creates label02011d44 and image02011d48, and loads `icon_dnd` into descriptor02015748 (`data` at02015750), with cached name02011d4c. Only this initializer writes those pointers in the recognized reference set. The updater042683f0 only checks label then calls shared clock formatter042a2e9a. Header root deletion would free its label/image, but the decoded icon's data is separately owned.

There is no recognized ordinary launcher-destructor call releasing02015748. The initializer releases it only if a different cached name is present; its own constant name is always `icon_dnd`. Thus avoiding first load on a new boot avoids a potentially persistent decoded buffer; deleting the existing header alone does not establish that buffer reclaimed. Shared clock helpers042a2e6e/042a2e9a remain untouched for other screens. Suppressing the initializer also omits its clock-format scalar reset; other screens call the same helper in their own initialization.

`header-range-refs.txt` shows external recognized references enter only the two function starts; interior branches remain within their functions. Global and code reference results are bounded negative evidence, not proof against unknown arithmetic pointers/ROM behavior.

## Requested dashboard cache supplement

`cache-caller-refs.txt`, `cache-init-refs.txt`, and `cache-callers/` export all recognized users of0429dc8e plus init0429f676 and wrapper042a6f30. The tracked allocator requests payload+16, maintains list02016128/count0201612c/current bytes02016130/peak02016134. Payload residency is variable. Initialization zeroes a0x544-byte global control block and sets its initialized bit before requesting a60-byte temporary tracked buffer; a forced NULL returns0xb after0429e06a. Other recognized callers explicitly test allocator NULL, but this alone does not prove downstream app/cache lifecycle after permanent denial. Initialization may also access/migrate KV state before allocator denial. Do not treat allocator gating as a pure cache-disable contract without testing the complete init/consumer state machine. No cache gate is included in this status/header recipe.

## Reproduction and limits

```sh
.tools/rv32-tests-venv/bin/python analysis/dashboard-ram-status-20261102/emulate_retirement.py NEW_REPORT.json
```

`retirement-rv32-v2.json` is the final140-call result; `retirement-rv32.json` is the earlier successful version before explicit scalar-value assertions were added. The final script includes all six combined gate witnesses, reads original bytes, and modifies only emulator memory. No production source, OTA or device operations occurred. Real settings callbacks/scheduler/concurrent screen destruction and actual free-heap improvement require the parent's separately reviewed cold-boot candidate and hardware measurements. Flash reclamation is independent: no XIP code/asset bytes are counted as RAM savings.
