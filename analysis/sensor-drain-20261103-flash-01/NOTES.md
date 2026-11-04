# Revision 10 flash

The pinned sensor-drain-001 image transferred once through the unchanged native
Swift OTA tool. All 2,247,403 image bytes were reconstructed from its durable
application trace and matched SHA-256; all 549 blocks and 3,841 chunks verified.
The peer acknowledged reboot. That acknowledgment does not establish boot.

The initial sandboxed SDP query timed out without transmitting. The authorized
probe outside the sandbox verified identity and heartbeat, then the OTA completed
without automatic retries. The first post-reboot connection timed out opening
RFCOMM; no boot or sensor checks completed in that attempt. A user wake was
requested. V6 remains the last verified boot until a later confirmation.

`checkpoint.json` records the exact image, runtime and installed-header pins.
`transfer-verification.json` summarizes the independent parser proof and hashes
the complete local proof and sealed trace. It is application callback evidence,
not independent HCI capture or full installed-runtime readback. The helper checks
the 256-byte installed app header and live version, following the proven V6
read-only verification path; its build recipe is included. Raw captures, binary
images, the compiled helper and host device inventory remain local.
