# Original manual notes

Reviewed 2026-11-01 from the user-supplied L1254/L1255 bilingual manual. One PDF sheet has 18 numbered panels per language; all were inspected visually. Preserved file: `research/manual-l1254-l1255.pdf` (ignored). See [hash and provenance](evidence/manual.json).

## Firmware backup implications

Neither language documents update-mode entry, firmware backup or recovery. Panel 18 in English points to `discord.gg/iine` for firmware/update tools; Chinese support information includes product upgrades. Pair + B is explicitly mouse pairing, not a documented firmware-update shortcut. The manual does not rule out a separate wired behavior.

Wired PC connection defaults to XInput (panel 8), consistent with the captured `Xbox 360 Controller` USB identity. The Pair button is on the bottom edge near the lanyard hole and LEDs; it is not HOME or Turbo.

## Pairing modes

Hold Pair with the indicated button until the corresponding LEDs flash quickly, then release.

| Mode | Button with Pair | Bluetooth name / additional step | LEDs |
| --- | --- | --- | --- |
| Switch | Up | Switch Controllers → Change Grip/Order | Pattern not numbered in text |
| Joy-Con | Down | Then press L + ZL; standalone right Joy-Con | Pattern not numbered in text |
| XInput | Left | Xbox wireless controller | 1–2 |
| HID | Right | wireless controller | 2–3 |
| Keyboard | A | IINE-Keyboard | 1–4 |
| Mouse | B | IINE-Mouse | 1–3 |
| Touch | X | IINE-control | 2–4 |
| Multimedia | Y | IINE-phone | 3–4 |

## Controls relevant to the port

The controller has D-pad, A/B/X/Y, L/ZL/ZR/R, minus/plus, Screenshot, HOME, Turbo and a separate Pair button. Face labels shown in mode diagrams may follow different console layouts; confirm physical-to-firmware mapping from this unit instead of transferring Gamebrick labels.

- Keyboard defaults: D-pad sends arrow keys; A/B/X/Y send those keyboard letters; L sends L, ZL sends Alt, R sends R, ZR sends Enter.
- Mouse defaults: D-pad moves the pointer, A left-clicks and B right-clicks.
- Multimedia: Up/Down changes volume; Left/Right selects previous/next track; A/B/X/Y controls play/pause/stop/mute.
- Turbo + minus swaps D-pad and emulated-stick behavior; setting is remembered.
- HOME + L + R for two seconds calibrates the gyroscope (LED 3 blinks three times).
- HOME + ZL + ZR for two seconds toggles air mouse (LED 4 blinks three times).
- Idle shutoff: five minutes. HOME held for two seconds reconnects to the last device.
- The Chinese panel specifies Pair held about two seconds for manual power-off; the English panel says press Pair without giving the duration.

These are manufacturer-documented defaults, not observed button/standby behavior on this particular unit.
