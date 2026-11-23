# Hidden LVGL owner prerequisite

The pinned SDK `gm_plugin_lvgl_api.h` declares `void (*obj_add_flag)(gm_plugin_lvgl_obj_t *, gm_plugin_lvgl_flag_t)` and `GM_PLUGIN_LVGL_FLAG_HIDDEN = UINT32_C(1)`. Compiled RV32/ilp32f [hidden-offset.c](hidden-offset.c) produces `.srodata` bytes `20000000 01000000`: table offset 0x20 and flag value 1.

Native table `0x04366168 + 0x20 = 0x04366188`, body offset `0x17b168`, contains `58de2c04`, pointing to `0x042cde58`. [Native export](function-042cde58.c) and [assembly](function-042cde58.asm) show a direct LVGL flag operation, with no plugin callback-range or lifecycle guard. Arguments are object in a0, uint32 flags in a1; return is void. The function ORs object flags at offset 0x24. It does not store a callback or borrowed argument pointer. Its entry frame is 64 bytes.

Hiding is not a completely side-effect-free operation: it invalidates the old object area, can adjust focus if the object is focused, and can mark layout dirty when layout participation changes. For a registry-only child, perform creation and immediate hiding on the display task, before yielding to refresh. Keep it nonfocused, without an image source, and do not infer that a hidden object is removed from the child list or immune to ancestor deletion. Parent deletion still determines the owner lifetime; the previously verified object-delete callback/timer cleanup contract must be used. Setting HIDDEN does not itself prove any timer/context lifetime scheme correct.

No device or runtime-source changes were made for this proof. A compiled owner implementation still requires review for self-delete paths, event callback cleanup, parent/screen replacement, bounded ring overflow and stock dispatch forwarding.
