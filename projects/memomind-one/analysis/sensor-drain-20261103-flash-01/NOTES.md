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

## Later confirmation

The second read-only boot attempt reconnected successfully. The installed
256-byte app header matched the pinned bytes, and the live capability response
reported GLASSLYCFW/10 with batch ABI2, FINISH5 and RELEASE6. See the separate
`boot-confirmation.json`; the original transfer checkpoint remains unchanged.

A separate sensor connection initially timed out before sending commands. Its
retry completed a 15-second passive capture: 15 contiguous ALS records, no
reported gaps or overwrites, FINISH with a fully acknowledged empty tail, then
generation-owned RELEASE returning inactive. No IMU records arrived. This checks
the running command lifecycle, not calibrated sensor response, nonempty finish
tail retention, expiry scheduling or physical display output. Full results and
remaining limits are in `sensor-verification.json`. No second OTA was performed.
