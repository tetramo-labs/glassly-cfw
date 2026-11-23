# GLASSLYCFW/13

Ambient light readings for the phone, on top of GLASSLYCFW/12. Built and
verified offline; not flashed or physically accepted.

## Runtime changes

- `7e/2c [01][interval ms u16 LE]` arms or renews a 90 s light lease and
  `7e/2c [00]` drops it. While it is live the left arm reads its TI OPT3001
  every `interval` (held to 200..5000 ms) from an LVGL timer and each reading
  reaches the phone from the master as `7e/2d [00][sample u16][flags][lux u16]
  [ms tick u32][panel level]`. See "Revision 13" in [runtime.md](runtime.md).
- The sensor is on the left arm, which is the slave on Nimo-4026: readings
  cross to the master as private UI message `0x7e2d` through the stock
  inter-arm transport, the path the notification relay uses for `0x7e28`.
- The stock firmware powers the sensor only while its auto-brightness wants
  it. Under the lease the runtime powers it when it finds it off (flag 01 in
  the reading) and powers it off again when the lease ends, unless the stock
  auto-brightness or the factory lux stream asks for it by then.
- No new stock hook. The input gate passes one more message id.

`runtime/nimo/light.c` is 950 bytes (1,012 with the router's case and the
gate's extra compare); the runtime is 47,147 of 83,488 bytes
(36,341 free). Static UI frame chains stay at 2,192 B; the light timer's chain
is 48 B and the emulator measured 32 B.

## Matching app changes

The Glassly App's NIMO drivers (iOS and Android) answer the light-sensor
contract (`session.lightSensor`) on GLASSLYCFW/13 and later: they hold the
lease while a miniapp subscribes, renew it every 45 s and apply the report
policy (first reading, then a change of `minDelta` or the heartbeat) on the
phone. `value` and `peak` are lux.

## Verification

```sh
python3 tests/run_tests.py --revision 13 --g2-source <pinned-G2-reference> --output <new-evidence-directory>
```

All six stages passed (G2 reference: MemoMind CFW commit `7edca45`,
`tests/g2_compat/upstream`). Host tests cover the lease, the timer at each
interval, the forced power and its three restore cases (stock wants it, the
factory stream holds it, nobody does), a failed read, a refused hand-over, a
full UI queue, the master's forwarding and its refusals. The RV32 emulator
runs the same on the linked blob for a left slave, a right master and a left
master, checks that the timer is created and deleted only on the UI task and
never from its own callback, and replays `tests/hardware/steps-13.json`
(57 steps) on both arms. The emulator's run list had lost the revision 12
head and IMU gate check in the merge that produced GLASSLYCFW/12; it runs
again here (17 checks).

Image and source hashes are in [the manifest](../analysis/cfw13-manifest.json).

## Physical acceptance still required

Steps 53-57 of `steps-13.json`, none of which has run on glasses:

- that a reading arrives at all: the hand-over uses the inter-arm UI transport
  with a private message id, which no hardware run has yet shown to deliver
  (the notification relay's use of it runs only when the ANCS client is on the
  slave arm);
- that LVGL timers on the left arm keep firing with the display off;
- the lux scale against a known light, and the reading dropping with the left
  arm's sensor covered;
- flag 01 with the app's auto-brightness off, and the sensor returning to off
  after the lease;
- that the stock auto-brightness still steps while the lease is live.

Steps 1-52 are GLASSLYCFW/12's, whose text, canvas checksum and accelerometer
steps were not recorded as run either.
