# Native small-overlay visibility and stacking proof

Bounded read-only/noanalysis exports from existing stock app project, mapped body base041eb020, original bodySHA81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8. No program analysis/write or device operation. Export commands/logs are beside `native/`; `.asm` is authoritative where decompiler omits arguments.

## Visibility

Pinned SDK `GlassSDK/include/gm_plugin_lvgl_api.h:338–344` declares add/clear flag `(object*,uint32 flags)→void`; HIDDEN value1. Prior compiled RV32 table-layout proof establishes add flag offset20; adjacent clear flag is24. Raw native table04366168+24=0436618c contains `e4d82c04`→**042cd8e4**. New native export confirms a0 liveobject,a1 mask, flagsword object+24 AND~mask, and for HIDDEN invalidates/redirties layout. Frame64 bytes; no plugin lifecycle/range guard or stored callback/pointer argument. It is not a no-op or a quiescence barrier. Use only the owning display task. Matching hide API042cde58 is already proved.

## Layer ordering

**042cf6fa(object*,int32 index)→void** is the native move-to-index operation; frame32 bytes. It resolves negative indices by adding parent child count, rejects out-of-range/already-same indices, shifts the existing sibling pointer array and writes object at the selected index. `-1` chooses the final child. It directly sends parent event0x22 (CHILD_CHANGED) then invalidates the parent. It does not allocate in its own body, but parent event/layout callees are not an allocation or reentrancy-free guarantee. Require a live nonroot object with a live parent; its apparent null paths are not a safe general null API.

The existing stock convenience wrapper **042a6dc6(object*)→void** (`analysis/ghidra/display-adapter/lvgl/function-042a6dc6.asm`) null-checks, gets parent via042cf43e, childcount042cf47a and tailcalls042cf6fa(object,count-1). Its16-byte frame is released before tailcall. It has no plugin-state check.

Last child is topmost in ordinary draw: newly exported042cb8ec renders parent events14/15/16, then loops children from0 up to count-1 and calls042cba00. Assembly witnesses042cb986 index0,042cb996 increment,042cb99c child render. Existing occlusion search042cb856 walks count-1 downward, consistent with top-first coverage. Thus the overlay can be brought above a graphics image created later without deleting/recreating its metadata owner.

Because moving invokes a synchronous parent event, finish descriptor/source/dimension/unhide work before move and do not dereference the diagnostic owner afterward without confirming it remains alive. Never retain graphics-owner pointers in persistent diagnostics. Parent-deletion callbacks must free only their own objects/data; screen destruction can delete siblings in either relevant order. Parent mutation/reentrant destruction through unrelated stock callbacks remains a contract of the existing controlled launcher context, not a blanket LVGL guarantee.

## Source and storage

Reuse the proven direct source setter042bd7fa(image,const descriptor*), pos042c963e(image,int32x,int32y), size042c96ec(image,int32w,int32h). Existing `P.image_source` hardcodes600x350 and must not be reused unchanged for a small overlay. Type9 descriptor encodes width bits10..20 and height bits21..31; size includes64-byte indexed palette plus packed rows. Choose even width/tight stride, stable descriptor and aligned palette storage. A dedicated wrapper should use the actual overlay dimensions and position, never infer that sizing the object rescales the source correctly.

Type0 const-source setter borrows descriptor/data; it does not copy them. Keep both alive through the LVGL image lifetime. Use existing DELETE callback ownership: invalidate magic, detach/delete timer if any, release source backing only under serialized deletion, freeowner once. Do not mutate/final-free while another task can render. `042b68c8` named cache_invalidate in CFW is a no-op in this stock build, not a fence; safety comes from synchronous display-task ownership and actual decoder lifecycle established by `analysis/ghidra/canvas-quiescence-review/report.md`.

A current-screen diagnostic metadata child can survive graphics mode11 deletion, hide overlay and preserve counts/cache epoch within that screen. Screen destruction resets it; this differs from G2's boot-lifetime singleton and must remain explicit. Separate overlay pixels preserve the clean raster: mode9/delta/retained operations never copy diagnostics into scene content. Mode7 itself updates desired visibility only; apply visibility/source/ordering on the next actual presentation if preserving upstream no-immediate-display-change semantics.
