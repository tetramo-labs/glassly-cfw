# Working instructions

Read `docs/findings.md` and `docs/plan.md` before continuing. On 2026-11-05 the
user explicitly authorized experimental firmware development and flashing,
including the risk of bricking controllers. Start with existing firmware or a
minimal change. This supersedes the earlier read-only scope. Preserve device
data locally and distinguish observed hardware results from offline emulation.

This is a new Zero 2 port. Gamebrick/Ananke patch offsets, Jieli toolchains,
partition maps, AE40/AE42 handles and physical key masks do not transfer here.
The v1.08 package has GD32 and Yichip sections; their selection/variant semantics
are unproven. Both sections must remain represented faithfully in analysis.

`build/button_stream.arm.o` is an unbound component, not a firmware image.
Do not describe it as ready to flash. Bind radio notification/CCC lifecycle,
input/debounce ownership, RAM, startup copies, stack and execution placement
before producing an image containing those components. The separately audited
name-only probe is a complete experimental image and has been flashed successfully;
it contains no custom GATT stream. Do not invent opcodes, firmware addresses,
physical mappings or successful hardware results.

The separate notification/idle probe has been flashed, fully read back and has
delivered four matching one-byte FF13 notifications on hardware with USB connected.
A battery subscribe-only session lasted 188.448 seconds without keepalives, followed
by four matching echoes after reconnect. Its narrow experimental tail placement is audited in
`docs/notification-probe.md`; this is not approval to place the unbound button
components there. It has no persistent RAM and no final CCC lifecycle binding.

Keep OEM firmware, device data, downloaded research repositories and generated
binary artifacts local and ignored. Preserve source revisions and exact hashes.
The vendor catalog MD5 mismatch is recorded in sources.lock.json; SHA256 pinning
provides reproducibility, not authenticated vendor verification.

Run `python3 tools/inspect_stock.py` after fetching the pinned stock image and
`python3 scripts/check.py` after firmware/tool changes. The latter builds an
unbound Thumb object and runs sanitized stream/model and Python checks.

The separate `buttons-probe` is flashed and fully read back; USB boot and a
valid BLE baseline are observed. All 12 physical buttons delivered press/release
packets in a user-confirmed ordered capture; A+B also worked. Evidence and masks
are in `docs/evidence/buttons-probe-mapping.json`.
Read `docs/buttons-probe.md` before changing or flashing it. It reserves one OEM
600-byte pool block (48 bytes used), uses 364 bytes of the audited tail, and has
its own sample-based filter/16-entry queue. It does not link the unbound C objects.
Its host contract requires FF13 subscription then A1; A0 before unsubscribe.
Battery A press/release and a 187.951-second connection without keepalives also
passed; see `docs/evidence/buttons-probe-battery.json`. No automatic radio CCC
callback or Glassly/iOS background delivery is claimed.
