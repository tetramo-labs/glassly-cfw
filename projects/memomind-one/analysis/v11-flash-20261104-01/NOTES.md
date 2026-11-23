# Revision 11 flash and phone confirmation

Native Mac pairing and V11 transfer succeeded: 549 blocks, 3,840 chunks, no
automatic retries. Independent trace reconstruction verified all 2,247,074
image bytes. The glasses acknowledged reboot. Exact image/runtime/header hashes
are in transfer-checkpoint.json. The first Mac boot readback timed out.

Subsequent phone logs confirm a live GLASSLYCFW/11 handshake at
2026-11-04T08:35:46.289Z. This establishes the firmware booted; installed-header
readback and physical display appearance remain unverified.

At 08:36:00.942Z, the record transport reports a rejected or malformed ACK.
Later sends fail because the same session is unusable, while the accessory
remains compatible/connected. Raw ACK bytes are absent, so the original
rejection cause is not established. See phone-log-confirmation.json.

The matching Glassly bundle is pushed on dev at b5a2910045. Raw captures and
phone logs remain local. Earlier checkpoints preserve their original status.
