# Read-only acquisition of the real CUS8 bad-sector map

**Use one fixed KV getter call into an owned116-byte record, preserve its status, then validate that copied record with the exact native checks.** This distinguishes a missing record from a stored valid all-zero map without a second unlocked read. It requires no KV initializer, store mount, repair, allocation, badmap save or flash mutation. The getter's normal native task/lock requirements still apply.

The full native getter/iterator/loader/CRC paths passed43 offline RV32 cases with synthetic read-only KV pages. This is executable ABI/validation evidence, not acquisition of the device's real map. No phone or runtime/source changes were made; shared Ghidra exports used`-readOnly -noanalysis`.

## Exact interfaces

Pinned stock1.0.3.127 app body SHA256`81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, base`041eb020`, nativegp`02011688`:

```c
uint32_t kv_get(uint32_t key, void *owned_out,
                uint32_t capacity, uint32_t *actual_length); //04235032
int badmap_load(void *ignored_context, uint8_t *owned_out96,
                uint32_t length);                           //042a9d0a
uint32_t badmap_record_crc(const void *record116);             //042a9c84
int badmap_bits_valid(const uint8_t *bitmap96);                //042a9cca
```

The final helper returns **1 valid,0 invalid**. It does not return-1. The top-level loader returns0 for present-valid **or absent**, and-1 for invalid input, KV error or validation failure. CRC helper returns CRC32 of exactly the first112bytes. Both pure helpers have16-byte frames, allocate nothing and modify no global state.

## Getter lifecycle, synchronization and ownership

[04235032](first/function-04235032.asm) preserves four integer arguments. NULL output, NULL length pointer or zero capacity returns13 before touching the length. For valid arguments it zeroes`*actual_length`; if native KV mutex`02011af0` is NULL it returns2, without initializing anything.

When initialized, it acquires that existing mutex via`0200ec3a`, scans records, copies successful data into the caller's buffer and sets actual length, then releases through`0200ecb2`. The copy and returned length are established **under the mutex**; no flash/XIP record pointer escapes. Once returned, the diagnostic owns a stable copied snapshot and can validate it after unlock. A concurrent later KV change cannot alter that copy. Do not acquire the same mutex around the public getter, which would add a recursive-lock hazard.

The lock wrapper checks native execution-context predicates and asserts on invalid context; it calls the native take operation with60000 timeout units and asserts unless acquisition succeeds. Unlock also checks native context. These are not clean diagnostic status errors. Use the already-running ordinary application task, outside ISR/critical sections and without holding the KV mutex. No scheduler/lock initialization is needed or appropriate for the diagnostic.

`0423463e(previous)` iterates4KiB pages over512KiB from the typec4 KV base, obtained by`04235554`; on the captured map this is device0 XIP`046f8000..04778000`. The base getter may populate its RAM-only cached base on first use. It does not format or write flash. The normal KV initializer`04234ac8` creates the mutex, resolves that base, sets format mode and runs separate startup walks; **the getter does not call it**. Uninitialized status2 must remain unavailable, not trigger initialization/repair.

The getter verifies sector magic`57714b78`, header XOR checksum, native format mode, sector state and record bounds/state. Mode2 additionally checks record-header integrity and payloadCRC8 through`0434cc64`. Actual assembly for its lower table-driven CRC`0434cc3a` is retained: the decompiler's empty-looking loop is incomplete and must not be interpreted as a no-op. The machine tests execute that actual CRC8 path.

| Getter status | Meaning for this fixed diagnostic |
|---|---|
|0|Record copied; `actual_length` is stored length, still requires badmap-format validation|
|7|No matching key after valid traversal; length0; native loader treats this as an effective all-zero bitmap|
|2|KV mutex not initialized; not absence|
|4|KV sector/record integrity or structural error; not absence|
|13|Invalid argument or destination too small; length stays0 for valid-pointer short-capacity calls|

The getter does not allocate, free, repair, delete or program anything on the inspected path. The initialized-base machine tests also observed no global-state writes. It has no caller-buffer writes before its successful copy; failures leave the data buffer unchanged. Zero the owned record before the call anyway, and emit no unvalidated bytes after failure. `actual_length` needs a distinct aligned32-bit location, not an alias inside the record.

## Full116-byte physical badmap validation

[042a9d0a](first/function-042a9d0a.asm) requires non-NULL output and length96, ignores context, and calls exactly`kv_get(6009hex,local_record,116,&actual_length)`. Status7 zeros96 output bytes and returns0. Otherwise every condition below is required before copying bytes16..111 to the output:

| Offset / size | Required content |
|---|---|
|0 /4|LE32 magic`474d4231`|
|4 /4|LE32 version1|
|8 /4|LE32 **unified physical base`01500000`**, not per-device offset`00500000`|
|12 /4|LE32 **physical size`00300000`**|
|16 /96|768-bit physical bad-sector bitmap|
|112 /4|LE32 CRC32 over the first112bytes, using reflected polynomial`edb88320`, initial/final complement|

The getter must return0 and exactly116bytes. `042a9c84(record)` computes the CRC; `042a9cca(record+16)` checks the bitmap. The bitmap's bit order is least-significant bit first within each byte. Bit`i` represents device1 physical sector`00500000 + i*4096`, or unified address`01500000+i*4096`. Bits0..15 (64KiB directory) must be clear. Bits16..767 may contain genuine bad sectors, including sectors512..767 in the future reserved thirdMiB. The96-byte record is the physical3MiB identity and must not be shrunk, relabeled2MiB, synthesized or cleared when native logical cache capacity is reduced.

Validation failures return-1 from the loader without writing output. A stored valid all-zero bitmap and an absent key both produce loader0 with zero output, hence **loader-only success cannot distinguish presence**. Do not call the getter once for status and the loader again for bytes: they would be separate snapshots and can disagree.

## Smallest fixed diagnostic design

Accept only the dedicated badmap opcode with its exact empty/fixed payload; expose no key, address, capacity or function pointer input. Use the existing owned scratch allocation for a116-byte record and separate32-bit length. No additional96-byte copy is required: after validation the96-byte slice remains inside the owned record until serialization copies it.

```c
uint32_t actual = 0;
uint32_t rc = kv_get(0x6009, record, 116, &actual);
if (rc == 7) {
    /* presence=absent, effective bitmap=96 zero bytes; no stored record claimed */
} else if (rc != 0) {
    /* unavailable/error; preserve native rc; no bitmap */
} else if (actual != 116 ||
           le32(record+0) != 0x474d4231 || le32(record+4) != 1 ||
           le32(record+8) != 0x01500000 || le32(record+12) != 0x00300000 ||
           badmap_record_crc(record) != le32(record+112) ||
           badmap_bits_valid(record+16) == 0) {
    /* presence=invalid; no validated bitmap */
} else {
    /* presence=present_valid; serialize exactly record[16..112) */
}
```

Return distinct `absent`, `present_valid`, `invalid` and `unavailable/error` states, with native getter status and actual length. For absence, explicitly label any zero bitmap as **effective default**, not a stored record. For present-valid include fixed physical identity and96-byte bitmap/192hex characters; preserve all genuine bits. Stop on getter/validation failure. No call to saver`042a9dd4`, setter`04234b5c`, mount/formatter or CUS8 repair routine belongs in this path.

Release request-owned memory only after parsing fixed scalar input, retain owned record through native calls and synchronous response copying, and free exactly once afterward. Run the getter in the existing normal task with nativegp/tp and normal ABI; do not hold the display lock or a custom critical section during the KV scan. Lock acquisition can block/assert; response allocation remains the existing runtime's separate OOM concern. This review establishes the native source/ownership contract, not a new asynchronous completion or cancellation guarantee.

## Stack and executed evidence

The getter's own frame is64bytes. Sector iterator adds16 and cached-base getter48: actual native execution observed **128bytes** for the getter chain, with RTOS take/give mocked. The top-level badmap loader's local116-byte record lives in its144-byte frame, making the observed full-chain maximum **272bytes**. CRC32 and bitmap validators each use16bytes. These are observed fixed native paths, not an interrupt-inclusive or real-RTOS worst-case bound. The recommended single getter plus owned-record validation avoids the loader's extra144-byte stack frame; custom helper/response frames still require compiler review.

[emulation.json](emulation.json) records43passing cases. [emulate.py](emulate.py) runs the actual pinned RV32 getter,128-sector iterator, cached base getter, badmap loader, CRC32, bitmap validator, nativeCRC8, memcpy and memset in Unicorn2.1.4. Only RTOS take/give are mocked; synthetic initialized globals and read-only KV pages replace hardware. Every allocation/free, native initializer, assertion or flash-write/erase/save entry is forbidden, and any target write outside scratch/stack raises. Callee-saved registers, gp/tp, output guards, exact take/give pairing and native return values are checked.

Cases include both KV formats; absent keys requiring129iterator calls; valid zero and nonzero maps; retained bits16/511/512/767; forbidden directory bits0/15; wrong magic/version/base/physical size;115/117-byte records; CRC32 corruption; KV header/payload corruption; different key; uninitialized getter; invalid buffers/lengths; unchanged outputs on error. The raw getter correctly accepts a structurally valid KV record with an invalid badmap header, demonstrating why the second validation stage is necessary.

The parent executed this harness successfully in its working native-test environment; this review checked the resulting43-case artifact. The child environment's initial Unicorn JIT smoke exited132 even on one ADDI, so that local failure is not counted as native firmware execution and the successful parent run was not repeated. No real badmap was acquired, no physical mutex/XIP controller or concurrent KV writer was emulated, and no persistence claim follows from these offline tests.
