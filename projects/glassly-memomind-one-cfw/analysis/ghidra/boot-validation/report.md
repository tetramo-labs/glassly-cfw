# Captured second bootloader: application verification and OTA activation

The acquired second bootloader's ordinary application handoff does **not CRC the full 2 MiB app allocation**. Its optional cryptographic verifier hashes the **header's declared body length**. Normal compressed OTA activation erases the **component's decompressed byte length rounded to 4 KiB**, then programs the emitted bytes. These findings remove the specific full-allocation verification concern for the inspected path; they do not establish exclusive ownership of the proposed tail or authorize a write.

## Provenance and architecture

Input: [boot-body.bin](../../boot-acquisition/boot-body.bin), 60,856 bytes, SHA256 `3ec87a7b0426bfca6ccb8f1c422b3ad075309f5ab053f8d25aef9dbf53e859bc`. The independently acquired 32-byte header has magic `a4e49a17`, body length `edb8`, CRC32 `820b4708`, and load address `02068000`; body CRC was independently rechecked. The source is the read-only device capture, not an OTA component or fabricated ELF. Acquisition artifacts were not modified.

Imported as raw `RISCV:LE:32:default:gcc` at `02068000` into isolated `projects/memomind-boot-live-20261031`. [ISA evidence](isa-classification.json) records independent startup discriminators: halfwords `280d` at offset `2e` and `20f1` at offset `5c` are RV32 `C.JAL` to initialization `02068060` and main `02068128`, with corresponding return flow. RV64 interpretation as `C.ADDIW` is inconsistent. Startup uses 32-bit pointer loads/stores, derives `gp=02077498`, sets `sp=02080000`, and clears BSS `02076db8..0207ac8c`. The uninitialized BSS block in the analysis database models that range; it is not acquired memory. `startup-raw.asm` retains a GNU raw-disassembler diagnostic that incorrectly selected RV64 compressed interpretations despite its machine option; use the explicit RV32 Ghidra exports and raw halfwords for these instructions.

## Reset-time selection and application handoff

Main `02068128` reaches [020684f4](function-020684f4.c), which identifies itself as the WuQi second bootloader. Selected bootmap state byte +5 controls the route: `1` enters compressed activation `02068ea2`; `0` tries type `18` then type `20` through [020683fc](function-020683fc.asm). A missing map or failed app selection takes an error path. No recovery transport or successful recovery procedure is established by that error path.

Bootmap selection `0206c698` checks each copy through `0206c652`: CRC32 covers `8 + count*20` metadata bytes and compares the next word. It chooses the valid copy with the **lower unsigned generation** when both are valid. In the [captured maps](captured-bootmaps.json), both copies are valid: physical `7fc000` has generation `ffffffd2`, state 0; `7fd000` has generation `ffffffd3`, state 1. The selected copy is therefore `7fc000`. The 20-byte type `20` record has physical start `001eb000`, load `041eb020`, body length `001bd540`, and allocation `00200000`. Only the low byte of record word 0 identifies the type; its other bytes must not be interpreted as a second length. No type `18` record is present in these captured copies.

`020683fc` checks the image magic at `physical_start+04000000`. At `02068450..52` it calls the authentication condition; if false it proceeds directly to handoff. If true, `020684ca..ce` calls the image authenticator and requires result zero. After admission:

- `02068458..78` compares the map load address with `physical_start+04000020`. For an XIP match, it does not copy. Otherwise the copy length is **map body_length**, loaded at `0206846e`, not map allocation.
- `02068492` reads header +24 as an optional boot-argument pointer and populates it.
- `020684c6` jumps to the **map load address**. It does not select the entry from header +12 in this function.

This function does not read header +16 (body CRC) and has no CRC call. The inspected ordinary path contains no full-allocation CRC or digest calculation. The retained CRC caller searches locate metadata/OTA CRC uses, not an app-allocation CRC in this handoff. This is a bounded executable-path conclusion, not a claim about every indirect call, first-stage ROM, manufacturing loader, or hardware security mechanism.

## Conditional authentication: exact covered bytes

[020686e2](function-020686e2.asm) reads hardware configuration index `29` through `02069f36 -> 0206d6a6` and returns true only when its low byte equals `66`. The lower read writes the index/control registers and reads `01430020`; the physical configuration technology and current register value were not acquired. Calling it a measured fuse state would overstate the evidence.

[0206899e](function-0206899e.asm) reads `header.body_length` at +4, locates the trailer at `header+32+body_length`, and walks the count byte at +20. Records use `[type:u8, algorithm:u8, length:LE16, bytes...]`; type 1 supplies signature bytes and a nonzero algorithm indicator, type 2 supplies a key blob. Missing records return 11. At `020689e0..e6`, arguments to [0206873e](function-0206873e.c) are key/key length, signature/signature length, **header+32**, **header.body_length**.

The verifier hashes the key blob and compares its 32-byte digest against security-register trust records read by `0206a47e`. The primary record is 44 bytes at offset 0; alternate 36-byte records at offsets `2c` and `50` require magic `39281047`. This is an SPI security-register read using command `48`, not a read from the ordinary captured first 64 KiB flash range. It then hashes precisely the supplied app body span, parses a DER key requiring a 256-byte modulus, performs the RSA operation, and checks PKCS#1 v1.5-style padding plus SHA-256 DigestInfo and the 32-byte digest. The raw 19-byte constant at `020756b0` is `3031300d060960864801650304020105000420`.

Thus the implemented optional authentication is RSA-2048/SHA-256 over the **declared body**, not the header, trailer, or remaining allocation. The active app header has trailer count zero. Together with the observed successful boot of this custom image, that is consistent with the optional condition being inactive on this route; it is an inference, not a live configuration-register measurement. No signature bypass or security-setting modification is proposed or performed.

## Compressed OTA activation and physical write limits

[02068ea2](function-02068ea2.c) obtains type 4 staging storage. It can skip a `SECU` outer structure, then requires inner magic `abcd6543`, validates the component table CRC and packed-stream CRC using `0206b964`, and bounds packed bytes against staging capacity. Merely skipping `SECU` records does not demonstrate outer-signature verification. Each component record is `[decompressed_length, compressed_length, destination, flags]`; special destinations 0/1/2 with flags zero decode metadata into RAM, while ordinary components use the flash path.

At `020691ee..02069220`, ordinary activation does:

```
erase(0, component.destination,
      (component.decompressed_length + 0xfff) & 0xfffff000);
lzma_decode(component.destination, &actual_output,
            compressed_pointer, component.compressed_length);
require(actual_output == component.decompressed_length);
```

For the observed app container, decompressed length includes the **32-byte image header plus body**. The erase helper [0206a246](function-0206a246.c) rejects unaligned address/length, uses 64 KiB blocks only when aligned and fully inside the requested span, otherwise 4 KiB sectors, and does not expand to partition allocation.

Decoder [0207114e](function-0207114e.c) reads the 13-byte LZMA-alone header and outputs in chunks using two 16 KiB buffers. [020710d6](function-020710d6.c) writes ordinary flash at destination plus emitted count through `0206a204 ->` [0206a104](function-0206a104.c). The latter sends page-program command `32` with `min(remaining, 256-(address&255))` bytes, advances exactly that count, and stops at zero. It does not pad programming to a full sector or allocation. Special metadata destinations use a RAM copy instead.

The record's expected decompressed count is compared **after decoding**; this is not proof that maliciously inconsistent LZMA sizes cannot overrun an expected component range. The bounds conclusion applies to valid constructed streams whose LZMA size and component size agree. No adversarial container was executed.

The activator validates and commits updated bootmap metadata to the alternate sector, clears the pending state through `0206c7c8`, then resets through `0206b710(6,0)`. The erase/program proof above concerns ordinary image components; metadata sectors and other components have their own writes.

## Consequence for the proposed app tail

The [live header arithmetic](live-app-bounds.json) uses the actual captured app header, SHA256 `643fd6b82cf02ac58295cfe68656fce52671de74e67d208d4172da000d24315f`, and agrees with the selected map body length:

| Range or bound | Physical address / size |
|---|---|
| App allocation | `[001eb000,003eb000)`, 2 MiB |
| Header + current declared body end | `003a8560` exclusive |
| Corresponding normal compressed OTA erase end | `003a9000` exclusive |
| Proposed tail | `[003ab000,003eb000)`, 256 KiB |
| Tail gap after declared body | 10,912 bytes |
| Tail gap after rounded erase end | 8,192 bytes |

The proposed tail is outside the inspected reset authentication span and current valid compressed-activation erase/program span. This updates the missing-bootloader limitation in the earlier [app-tail report](../app-tail-store/report.md); that report remains a historical artifact and was not edited here. Its independent ownership findings and separate whole-partition updater path `042400b6` still matter. Cache survival across all OTA paths is not implied.

A real reservation must cap every future header/body and rounded erase extent before `003ab000`, reject incompatible layouts, and include metadata/erase-replacement overhead in usable cache capacity. This boot analysis alone does not prove that no runtime service, alternate loader, ROM path, or factory process owns the tail; nor does it demonstrate a reset after an actual tail write, atomicity under power loss, or recovery from failure. No device action or flash write was performed in this investigation.
