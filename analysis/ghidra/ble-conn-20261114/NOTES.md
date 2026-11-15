# Bonded-phone check, connection update and security request (app image, 2026-11-14)

Exports in `a/` come from `ExportFunctions.java` on `segment-3.body.bin`; `bcore/` holds two
empty `FindScalar` scans (0xb04 and 0xb06 are not encoded as single immediates in the BT core).
Revision 26 builds on these findings.

## Stock LE connection policy

- `0421465e(conn)` runs on every LE link event (conn: address at +0, address type +6, kind +7,
  handle u16 +8, state +0xc, reason +0x10). At state 3 it skips known rings (`0424eef2`), then
  calls `042133e2(conn)` (bonded phone) and resolves the central's address through `04318caa`
  against the bonded address at 0x0201132c (`04212eec`, true when equal). A match stores the
  peer as the current phone (`04213150(3|5, conn, …)` copies it to 0x020128b6 and arms the
  0x3f4 timer); anything else that is not the bonded phone is disconnected (`04319c04`) unless
  it arrived as a peripheral-role kind 2 link, which gets the 2000 ms 0x3f3 timer instead.
- `042133e2(peer6)` = `DAT_020128bc != 0 && memcmp(0x020128b6, peer, 6) == 0`: true for the
  central the stock currently treats as the phone. `04212eec(peer6)` = `memcmp(peer, 0x0201132c,
  6) == 0` (and true for a NULL pointer): the bonded address itself. Both take a bare 6-byte
  address, so the BLE link's saved peer works as the argument.
- 0x3f3 handler (`04217546` at 0x0421978c..): unless the link is already secured
  (`0x020128b5 != 0`), it sends the security request `04318dca(peer, type, kind)` =
  `043199d2(0x2bc, [peer6][type][kind], 8)` and re-arms itself with `attempts * 1000 + 2000` ms;
  past two attempts it logs, posts 0xd/4 and disconnects (`04318052` = `043199d2(0x175,
  [peer6][0], 7)`).
- `043199d2(opcode, payload, len)` is the app's synchronous RPC into the BT core (`04316d00` →
  `0434b3a4`); it returns 0 when the core accepted the message and 0xb when Bluetooth is
  off/busy or the core refused it.

## BT core connection parameter update

- The user command dispatcher `1406334e` (case = opcode − 0x200) handles 0x27a as
  `bt_service_le_conn_update_param_req` with an 18-byte payload: `[peer6][u16 ×6]`, looked up
  among the three LE connection records at 0x10233c04 (active flag at +0, address at +2), then
  copied into message 0xb04 for LE module 0xb as `[slot][pad][u16 ×6]`. 0x27b is
  `bt_service_le_conn_update_param_rsp` (20 bytes, `[peer6][accept][u16 ×6]`, message 0xb06).
  The six words follow the HCI order the EtherMind API takes: interval min, interval max,
  latency, supervision timeout, CE length min, CE length max. The stock app never issues
  either (no 0x27a/0x27b immediates in the app image), so the central's defaults apply.
- Strings in the BT core name the neighbours: `bt_service_le_security_request`,
  `bt_service_le_start_encryption`, `bt_service_le_disconnect`, `bt_service_le_set_phy`,
  `bts_le_connect`.

## Used by revision 26

`glassly_ble_on_link` keeps the central's address type and kind and sends
`043199d2(0x27a, [peer6][12][24][0][400][0][0], 18)` (15-30 ms, latency 0, 4 s) as the link
comes up; the hello accepts a peer at once when `042133e2(peer) || 04212eec(peer)`; control
`80 02` resends the update with the phone's values and `80 03` resends the security request
`043199d2(0x2bc, [peer6][type][kind], 8)`. The BT core's return codes are reported in the
control replies and the status block.
