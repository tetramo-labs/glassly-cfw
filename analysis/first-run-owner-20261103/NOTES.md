# Revision 11: first-run display ownership

The user reports cycling language/welcome text after connecting Glassly. The new
local pairing log records a successful GLASSLYCFW/10 handshake followed by repeated
display-busy errors while the iAP2 accessory remains connected. The sanitized log
summary retains only firmware handshake evidence and the busy-error count; the
raw app log stays local. Live top-app readback was not collected.

The stock display-task startup reads setting 5205. Zero selects welcome
descriptor 0200fcf4; nonzero selects launcher 0200fc7c. The existing minimal
launcher replacement retained this first-run choice. The welcome app can therefore
keep the display while the CFW wake/frame guards correctly refuse acquisition
outside the launcher.

V11 replaces the four-byte instruction at 0425bf50 from `addi a0,s2,-0x30c`
to `addi a0,s1,-0x384`, using the already initialized descriptor bases. Both
branches now enter the minimal launcher. The setting read and app-manager call
remain intact; there are no settings or pairing-data writes. No other stock
entry or welcome callback is patched. The runtime differs from V10 only in the
version string, and remains 96,448 bytes. The exact application-body difference
is three instruction bytes plus one version byte.

The RV32 test executes the original and patched selector with setup values
0, 1, 2 and -1, and rejects each changed instruction-witness byte. Settings reads
and the final app-manager entry are mocked; this is not physical boot proof.
The initial sandboxed emulator runs exited with SIGILL; the unrestricted run
passed. App catalog, resource and adapter tests pass on Mac/iOS simulator/Android.
All 145 offline regression stages passed with no source drift or missing mapped
stages. This includes the first-run selector regression. Full G2 suite porting
and hardware verification remain incomplete; see regression-verification.json.

V10 remains the installed, boot-verified version. V11 needs an update followed
by confirmation that the welcome loop is absent and Glassly can present a frame.
The Mac Bluetooth adapter was off during the user's phone-pairing test; it was
not changed or used to disrupt that connection.
