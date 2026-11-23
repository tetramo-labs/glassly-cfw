# Revision 3 and native OTA pacing

Revision 2 stopped after 16 KiB when stock firmware returned `0000004012040007d0`: success, next absolute offset 16402, next length 1024, field 2000. No retransmission or reboot was sent. The original revision 1 app header was read back afterward. See the sealed revision 2 flash-attempt record.

Stock app SHA256 `81346c77371a91544dd0b79dd7f108f553f60d5459a3e7e797ebffbebbda5ba8`, function `04238da8`, emits field 2000 when peer-state helper `04214bae(0)` is nonzero or `04214b0c(0)` returns 4. Otherwise the field is zero. For more than 4096 bytes remaining, that path requests 1024 instead of 4096 bytes. The next offset remains the forward cursor plus the 18-byte container header. The exact machine code is executed in `tests/rv32/ota_pacing_native_test.py` with peer-state, logging and transport calls mocked. Cases include final blocks and failed sends.

The Swift driver accepts only the two observed fields. For 2000 it conservatively waits two seconds, checking control-link health every 100 ms. Timing units and a causal connection to charging have not been independently proven. Unknown fields, repeated ranges, stale resumes, out-of-image ranges and early terminal ACKs still stop the transfer. This change does not implement retries.

`verify-ota.py` independently reconstructs every transmitted byte, validates CRCs/sequences/ranges and checks callback timestamps show at least two seconds between a paced ACK and the next OTA transmission. Its historical complete-transfer fixture and 20 additional positive/negative cases pass. Callback evidence is not an independent radio capture.

Revision 3 contains the same notification/settings code as revision 2, with a new runtime version string. Its distinct container CRC requires a fresh OTA; an old resume offset remains rejected. App distribution remains gated on physical boot verification.

Build:

```sh
python3 scripts/compile_memomind_graphics.py analysis/ota-pacing-20261103/build-03 \
  --scene-session --input-observer --flash-reader --external-tail-reader \
  --storage-diagnostics --full-store-reader --flash-canary --raster-commands \
  --rect-copy --command-bundles --text-commands --diagnostic-commands \
  --reset-undo-trim --minimal-launcher --flash-scene --wake-control \
  --notification-relay --cfw-revision 3 --rx-profile app-rx-96k-v1
python3 scripts/build_memomind_minimal_owner.py \
  captures/firmware/ota-1.0.3.127-glassly-text.bin \
  analysis/ota-pacing-20261103/build-03 analysis/ota-pacing-20261103/image-03
```
