# Minimal visible text patch candidate

Recommended literal: **Bluetooth disconnected → Glassly firmware ready**.
Both are 22 ASCII bytes. No image bytes were edited in this investigation.
The target is an on-glasses system toast with a verified path to an LVGL label.

Exact bytes, source hash and offsets are in [candidate.json](candidate.json).
Input is the validated stock 1.0.3.127 segment-3 body, SHA-256
`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`.

| Property | Value |
|---|---|
| Body offset | `0x17d710` |
| XIP address | `0x04368730` |
| Existing text | `Bluetooth disconnected` |
| Proposed text | `Glassly firmware ready` |
| Proven capacity | 22 text bytes + existing NUL (23 bytes total) |
| NUL body offset | `0x17d726` |
| English resource ID | `0x50` |
| Resource pointer slot | `0x0437f8c8` |

The exact NUL-terminated source occurs once in the body. An exhaustive raw
little-endian pointer scan finds one pointer occurrence, at the resource slot
above; Ghidra finds that same sole data reference in
[disconnected-refs.txt](disconnected-refs.txt). These statements do not rule out
computed pointers, but the identified computed lookup is described below.
Preserve the NUL and all adjacent bytes; do not treat alignment padding as extra
capacity. There are no printf substitutions in either literal.

## Locale proof

[0x0429c1c0](final/function-0429c1c0.c) reads language setting `0x5501`.
[0x0429be3e](final/function-0429be3e.c) subtracts one, so the live baseline's
`lang=2` selects table index 1 (English). [Lookup 0x0429c290](function-0429c290.asm)
computes `0x0437f384 + 4 * (257 * language_index + resource_id)`.
For `(1, 0x50)`, this is `0x0437f8c8`, whose value is `0x04368730`.
The decompiler omits some register-forwarded arguments, so the assembly is the
stronger evidence for the sequential language-read/conversion calls.
The reported font value 20 is consistent with [0x0429c226](final/function-0429c226.c),
which reads setting `0x5502`; this patch does not change font configuration.

## Display path, not a log or protocol identifier

1. [Display dispatcher 0x0425b38a](render/function-0425b38a.c), normal event class
   12, masks the connection state with `0x7f`. State 1 is suppressed. Other states
   reach `0x0428287e(4, &state, 1, callback)` at call site `0x0425b818`.
2. [System-UI builder 0x0428287e](toast/function-0428287e.c), type 4 and length 1,
   selects resource ID `0x4f` for state 1, `0x51` for state 2, and **`0x50` for
   state 0**. It copies the selected text into heap storage via `0x0428219a`
   and stores its pointer at `0x02011dc8`, beside type at `0x02011dc4`.
3. [System-UI initializer 0x0428261a](render/function-0428261a.c) creates the
   display container and invokes [0x042823a8](render/function-042823a8.c).
   For UI kind 2, that function passes the stored type and text into
   [0x0426e29a](final/function-0426e29a.c).
4. That renderer creates a label through
   [0x042a61f0](label/function-042a61f0.c), calls
   [0x042a6220](label/function-042a6220.c) with the text, and selects the
   `bt_disconnect` icon. The wrapper calls [0x042bf14c](toast/function-042bf14c.c),
   the LVGL label text setter: it manages `label->text`, copies text into label
   storage, and refreshes label layout. This establishes actual display use.

All exported functions retain corresponding assembly files and incoming-reference
lists in their directory's `functions.json`. Other builder callers are at
`0x0425b8ea` (generic system-UI request) and `0x04287622` (type 6 network error).
The latter does not select this literal.

## Visual check and why this candidate

On stock firmware first, keep the glasses worn/awake in their normal idle UI,
then turn off the phone's Bluetooth. Confirm the glasses show **Bluetooth
disconnected**. After an independently approved and accepted patch installation,
repeat the same action and expect **Glassly firmware ready**. Re-enable Bluetooth
to reconnect. This is the proposed trigger based on native event semantics;
this agent has not performed the live visual baseline. Merely closing the app
may select **App disconnected** (state 2), which is a separate unchanged literal.
Toast suppression during other UI modes remains possible.

`Bluetooth connected` was rejected as the primary candidate because the normal
connection event explicitly suppresses state 1. `Brightness %d` was found in the
resource table, but this bounded pass did not prove an active rendering caller.
The recommended disconnect literal keeps byte length, pointers, structure sizes,
code and format arguments unchanged. Same-length editing limits the change's
scope; it does not establish firmware acceptance, a recovery route, or successful
execution of a modified image.
