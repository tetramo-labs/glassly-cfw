# Stock BLE phone link and OTA transports (app image, 2026-11-10)

Exports in this directory (`a`..`m`) come from `ExportFunctions.java` / `InspectAddresses.java`
on `segment-3.body.bin`. Revision 25 builds on these findings.

## GM link selection

- `042d9aa6()` returns the phone link type: 1 = RFCOMM 0x7033 context 0x0205af78, 2 = `042d8aae()`,
  3 = SPP 0x1101 (flag 0x020120d4, set by `042ded50`), 4 = BLE (flag 0x02012077), 5 = `042d9a6e()`
  (context 0x0205afb0), 0 = none. `042de142()` (phone connected) is true for 3, 4 and the rest.
- 0x02012077 is only ever cleared (`042deb6e`); no stock code sets it. Peer address: 0x02012088
  (shared with link 3).
- `042dad7c(total)` reserves a link for a multi-frame send (sets 0x020120a8, 0x020120ac = type);
  type 4 reserves without further checks. `042dae7a` ends it.

## GM writer

- `042db006(data, len)` returns 1 when sent. Its BLE branch (`jal 0431a712` at 0x042db2a8) passes
  peer 0x02012088 and chara NULL; `0431a712` refuses NULL, so stock never sends GM over BLE.
- First 8 bytes `39 71 22 dc 4a d8 52 d4` (addi16sp -64; sw s0/s2/s4) are position independent;
  the continuation is 0x042db00e.
- Callers: `042e61cc` (frames from `042f008a`; flag 0 writes directly, flag 1 posts message 0x3b to
  task 0xd) and the BT task handler `042dfc8c` (0x3b: waits up to 10 x 200 ms while `04216db2(peer)`
  reports the Classic link busy, unless `042d9a3e(peer)`).

## GM receive

- `042e8350(data, len, ctx, ctx_len, out_flag)` parses packet-aligned buffers (byte 0 0xFA or a
  fragment index, u24 logical length) and dispatches through `042e70a4`.
- `042d9be0(peer, data, len)` posts `042361b8(0xd, 0x3a, data, len)` (copied); message 0x3a in
  `042dfc8c` calls `042e8554(data, len)`, which parses with the global context 0x020120f8.

## OTA transports

- `042393cc` (OTA init) installs three transport vtables: SPP 0x0435d9c0 (`0424161c`, UUID 0x7034),
  BLE 0x0435d958 (`04240488`) and IAP2 0x0435d984 (`04240d42`), in DAT 0x02011b70 / 0x02011b20 /
  0x02011b2c. Layout: +0 name, +8 init, +0x14 / +0x18 / +0x1c callback setters, +0x20
  `send(conn, buf, len)` returning 0 on success (the buffer is freed after the call, `04238b70`).
- All seven BLE methods are empty stubs (`0424043e`..`0424047c`; +0x1c and +0x20 return 0).
- The BLE slot's callbacks are fixed: receive `0423cc32(conn, data, len)` → `0423cafa(BLE vtable, …)`
  (the first transport to send claims the OTA session), disconnect `042388e0(conn)` →
  `04238788(conn, BLE vtable)` (aborts that session and writes the resume record).

## LE connections and advertising

- GATT link listeners (`04319adc(cb)`, four slots at 0x0205bffc) are called by `04319caa` on event
  0x12d as `cb(conn, peripheral, connected)`: `peripheral` is 1 for links where the glasses are the
  peripheral, `connected` is 1 for +0xc == 3 and 0 for +0xc == 1.
- `042d55f6` (stock listener) stops advertising on connect (`042d556a`) and restarts it on
  disconnect only under conditions (`042d52bc`).
- `042d52bc` (start advertising): flags, 16-bit service list 0x9200, 'GM' manufacturer data,
  name; needs `0421b5c2`, slot 0x02011690, BT core ready, not advertising (0x02011ffc), no LE peer
  (0x02012004) and a bonded phone (`042164c6`).
- Stop-advertising call sites in the BT task: 0x042e0ff6, 0x042e1020, 0x042e2062, 0x042df852,
  0x042d5b56 (0x042d5694 is the LE-connect stop and stays).
- `0421465e` (LE connection policy) resolves the central's address (`04318caa`), compares it with the
  bonded phone 0x0201132c, then posts app event 0x3f3 after 2000 ms; the security request
  (0x2bc) retries and drops the central when it fails.

## GATT characteristic permission

The walker (`0431a42e`) copies chara node byte +0x1f into the 0x20e message at +0x3c; the BT core
(`14060900`) stores it as the attribute permission byte. Its bit meanings in this EtherMind stack
are not established, so revision 25 gates on the connection window instead.
