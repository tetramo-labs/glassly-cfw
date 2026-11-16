# GLASSLYCFW/11

Prepared for the matching Glassly App Nimo fixes. This revision is built and
verified offline; it has not been flashed or physically accepted. The last
hardware-tested revision remains v10 (35 steps, both eyes confirmed correct).

## Runtime changes

- Input lease `7e/29 [01]` enables or renews forwarding for 90 seconds; `[00]`
  disables it. Head-up `86`, head-down `87`, taps `88..8c`, press `98` and
  release `99` reach `7e/26` while this lease or the display lease is active.
  The payload retains side 0 right / 1 left and the gesture sequence. This
  allows an idle dashboard to be opened without first acquiring the display.
- Brightness `7e/23 [ff]` releases the manual ALS hold without clearing the
  retained scene. Levels 0..32 keep their existing meaning.
- ANCS intake on the slave sends bounded records through the stock inter-arm
  UI transport (`041fc078`, private message `7e28`). The master forwards them
  on `7e/28` only while its notification lease is live. Immediate send failure
  leaves the notification with the stock intake; STATUS's last byte counts
  send failures modulo 256. Delivery is not acknowledged end to end.

The inter-arm binding was checked against the local 1.1.5.1 disassembly:
messages up to 512 bytes are copied before return; relay records are at most
142 bytes. Head message IDs come from the stock UI dispatcher. No vendor
source or images are included in this repository.

## Matching app changes

The Glassly App rasterizes ordinary and builtin labels because this runtime
has no native builtin font; mono clock text retains its cached font path.
Ordinary text uses 20px text and 27px line spacing. The mirror measures scene
font advances instead of the stock 16px face. Both native drivers retain the
touchpad index, send `touch_down`, hold `tap_start`, release `tap_end`, and
recognize single/double taps; native triple/long gestures are forwarded too.
The matching iOS driver now uses the existing variable-duration Opus decoder
instead of fixing every packet at 20 ms. Its Nimo parser-to-decoder regression
reproduced a failure on a valid 10 ms packet with the old code; malformed
packet recovery is also covered. Live microphone audio remains unverified.
Saved head-up angle is applied at connection. On iOS, notification lease
updates coalesce and refresh when ANCS authorization arrives.

## Verification

All six offline stages passed using:

```sh
python3 tests/run_tests.py --revision 11 --g2-source <pinned-G2-reference> --output <new-evidence-directory>
```

The G2 reference is pinned to `e889569fe77775ed5822af6f7e47210f2984f15d`.
Container round trips, stock hook witnesses, runtime size/ISA/alignment/stack
checks, portable ASan/UBSan suites, Nimo host suites and 14 compiled RV32
checks passed. The emulator replays all 37 hardware-fixture steps, including
input lease enable/disable. Source hashes were unchanged during the run.
The runner now fails if the available optional emulator stage fails.

Image and source hashes are in [the manifest](../analysis/cfw11-manifest.json).
The image is 1,959,132 bytes, SHA-256
`f2026e2126d043c0fe2aa14e96f6374b7d967a24c1d66e4b05553121f1965eaf`.
The runtime uses 43,575 of 83,488 bytes (39,913 free).

## Physical acceptance still required

Use `tests/hardware/steps-11.json` with the existing Mac harness, then the
matching Glassly App on iPhone. Confirm both-eye labels and spacing, brightness
and display position, automatic brightness without blanking, idle head-up,
right double-tap dashboard opening, left index 1 and right index 0 press/hold/
release, and a new notification after Share System Notifications is enabled.

Report `rep_01M7GZHD5VRCSZCSK8NN0C56QD` showed ANCS authorization arriving while
relay counters remained zero, plus overlapping app relay requests. The app
request collision is fixed and slave forwarding is covered offline, but the
report does not prove that slave routing caused the physical delivery failure.
An iPhone notification reaching the glasses remains an acceptance requirement.
