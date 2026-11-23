# Reentrancy decision: use a child overlay, not foreground reordering

The discovered move-to-index ABI is real, but **it is not admitted for this implementation**. The earlier native-overlay-abi.md statement 'do not touch diagnostics owner after move' is insufficient: graphics/scene callers continue to use their owner/core after presentation. Native042cf6fa sends active-screen CHILD_CHANGED0x22 synchronously, and a static API-table proof does not establish that the active screen has no callback capable of deleting the graphics owner. Do not call it from this path on that basis.

Root and implementation agent selected a stronger ownership arrangement: persistent diagnostic metadata is a hidden screen child, while its visible image is a child of the CFW graphics image. The existing painter042cb8ec draws parent then children, so the overlay naturally follows/overlays the main image with no sibling move/foreground function. The metadata owns palette/pixels/descriptor, separate from scene pixels. It holds only the overlay weak pointer, not a borrowed graphics-owner pointer.

Native evidence for the controlled image parent:

- Image class04385b38 points to base04385e10 and event042bd9f2. Its child-change event0x22 has no additional image-specific operation beyond calling the base handler.
- Base handler042cda18 at0x22 queries styles and may call042c9750 to dirty layout. It has no delete/free in that branch.042c9750 marks object/screen layout flags and resumes refresh timer if present.
- Generic event dispatcher042c766a applies callback event filters. The CFW graphics callback is registered for DELETE0x21 only, so it does not execute for0x22. That event does not bubble: the no-bubble mask0x0b0f27ff contains bit(0x22-0x11). Generic dispatch may invoke current input-driver feedback first, as with existing native events; this bounded class/callback proof is not a claim that arbitrary future installed handlers are safe.
- Native deletion core042cf4de sends object's DELETE0x21 **before** recursively deleting children. Therefore overlay callback userdata must never point at the freed graphics owner.

Current diagnostics.c follows the necessary lifetime ordering: its overlay DELETE callback only clears `diagnostic_owner.overlay`; metadata DELETE synchronously deletes any live overlay while metadata is still alive, then frees its inline descriptor/palette/pixels. If graphics is deleted first, its child overlay clears the surviving metadata's pointer. If the metadata sibling is deleted first, it deletes the overlay before freeing metadata, leaving nothing for later graphics-child recursion. This covers both screen sibling deletion orders. The main graphics destructor may dispose/free graphics owner before overlay-child callback because the latter never references graphics owner. No native move/foreground helper is linked by the selected design.

Read-only source review found and reported two issues, now corrected by the owning agent:

1. The first diagnostics-present call was in the non-scene compile branch; actual MM_GRAPHICS_SCENE presentation did not call it. Current scene_present invokes diagnostics after the main image source is set.
2. Mode11 explicitly released scene core, then the image destructor released it again, incrementing epoch twice. Current mode11 calls `mm_scene_session_dispose` once and captures epoch afterward; the destructor's repeat dispose is guarded by initialized0.

Remaining scoped limitations to retain in final claims: diagnostic metadata resets when its screen is destroyed; current native counters cover executed scene-dispatch refusals/workspace refusals rather than all BT/queue/native/overlay allocation failures; epoch preservation is currently captured for explicit mode11 and is best-effort if metadata must be allocated, not a globally persistent epoch across arbitrary lease/UI destruction. Canary registry/workers remain untouched. Actual compiled-size/stack/gates, lifecycle mocks (including both screen deletion orders), allocation-failure paths and native byte witnesses still require the implementation agent's final test evidence.
