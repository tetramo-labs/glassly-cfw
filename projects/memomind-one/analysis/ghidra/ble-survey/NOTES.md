# BLE command channel survey (app image, 2026-11-07)

App-side GATT server API (stock, used by app_gatts.c / app_ble_adv.c):

- `0x0431a7fe register_service(desc[0x24])` → node* (list head DAT_0201223c). desc: +4 flags=1,
  +6 uuid16, +0x18 0xf0000000, +0x1c 0x1ffff (GAP/GATT) or 0xffff (custom 0x9200/0x9300).
  Nodes: +0 next, +4 copied desc (0x14 bytes), +0x20 chara list head.
- `0x0431a93a register_chara(service, desc[0x68])` → node*. desc: +4 flags=1, +6 uuid16,
  +0x18 0xffffffff (handles assigned later: +0x18 value handle, +0x1a cccd handle, +0x1c cccd value,
  +0x20/+0x22 more handles), +0x1e props (0x02 read, 0x0e read|write|write-no-rsp, 0x20 indicate),
  +0x58 read cb `u16 cb(msg, node+4, buf, len)`, +0x5c write cb `void cb(msg, node+4, data, len)`,
  +0x60 cccd cb `void cb(msg, node+4, enabled)`, +0x64 read-multiple cb.
  Both register functions kick the registration state machine (`0431a42e` / `0431a6a8(1)`) only
  while DAT_02012230 ("pending") is set — adding a service after boot needs that path re-run.
- `0x0431b4dc(cb)` / `0x0431b4f0(cb)` set connect/disconnect callbacks (DAT_02012240/44);
  `0x04319adc(cb)` adds a GATT event listener (4 slots at DAT_0205bffc); `0x0431aa24(cb)` sets a
  second-level listener.
- `0x043199d2(opcode, buf, len)` posts to the BT core work queue (0x212 read response from the
  server handler, 0x217 read-multiple response, 0x21e/0x21f/0x220 client ops).
- **Notify/indicate egress: `0x0431a712(peer_addr[6], chara_node, data, u16 len)`** builds
  {addr6, value_handle(+0x18), data*, len} and posts opcode **0x210**; refused while DAT_02012231
  (registering) is set or the handle is unassigned. 0x213 (`0431b536`) is the Service Changed
  indication sent from the connect callback.
- Registration state machine `0x0431a42e()`: walks services (handle at +0x1c == -1 → register
  service, opcodes 0x20b/0x20c) and their charas (handle +0x18 == -1 → 0x20e uuid16 / 0x20f
  uuid128), one message at a time; BT-core replies re-enter via the listeners (0x04319adc /
  0x0431aa24 → `0431a32c`) and finish with `0431a3fc()` (register done). `0431b504(1)` arms
  the pending flag; `0431a6a8(1)` clears it and calls the disconnect/done callback. So a
  post-boot service can be added: register nodes, arm pending, call `0431a42e()`; whether the
  BT core accepts additions after register_done is a hardware question (ERR_STALE_GATT_DB exists).
- Advertising control: slots live in a ring at PTR_020116c4 (`04316df8(id)` finds/creates one,
  DAT_0201220a counts them); `043179c2(0)` restarts every enabled slot via `04317164(id)`,
  `043179c2(1)` suspends; `0431750a` posts 0x170 then rebuilds params. Adv enable: `04317164(slot id)` posts opcode 0x169 {enable=1, slot...}; `0431733e(enable, n, ids, ...)`
  and `043173f6(enable)` apply it to every configured slot (slot struct 0x38: +8 configured, +9 enabled,
  +0xb state, +0xd id, +0x10/+0x12 interval, +0xe own address). Own address: `04318222()` →
  DAT_0205bfec. Registration done callback: `0431a3fc()` → DAT_02012240 (app_gatts' 0421c1d6, which
  sends Service Changed via 0x213). The adv payload setter is still unread; the stock slot's data
  (device name) is enough for a phone to find the glasses and discover a new service.

## Rev 16 experiment (before any channel code)
A diagnostic command that (1) registers service 0x9400 + chara 0x9401 (props 0x1c) with a write
callback that counts bytes, (2) arms pending and calls `0431a42e()`, (3) enables the stock adv slot
via `04317164(DAT_0201220a-1)`, and reports the handles/status. Then scan from the Mac (CoreBluetooth),
connect, write, and read the counter — proves post-boot registration and the write path on hardware.
- `0x0431aa80(opcode, msg)` is the server handler: 0x165 read req, 0x164 write req (CCCD writes
  routed to +0x60), 0x166 read-multiple, 0x162/0x163/0x15f/0x160 connection/bond events with
  records DAT_02012228 / DAT_0201222c, 0x169 stores a 16-byte key at DAT_0205c00c.
- Advertising: `0x04317a46()` returns `04316df8(DAT_0201220a)` (adv slot); `0x04316d42(params, len)`
  builds adv params (type 0x10001, own address from DAT_020116cc), `0x04317578(slot, min, max)`
  sets the interval. The enable call is still to be found (adv-params-callers.txt).
- The stock gate `0x0421b5c2` returns 1: app_ble_adv init always runs and registers 0x9200/0x9201
  and 0x9300/0x9301 (ring relay), yet no LE advertising was captured while Classic-connected.

Plan for a Glassly channel (rev 16): register service 0x9400 + chara 0x9401 (props write|write-no-rsp|notify)
from the runtime init, write cb → post a display-worker job tagged BLE, egress via the notify
opcode; advertise with the stock slot; phone side CoreBluetooth central (iOS only gain).
