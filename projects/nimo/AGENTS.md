# Project workflow

- The firmware is WuQi ADK RISC-V (RV32C) with LVGL 9.3, the same platform as
  the MemoMind One. Reuse the approach and the tooling shape of
  `~/dev/glassly-memomind-one-cfw` (container parser, appended RV32 runtime,
  offline-first verification); its Thumb/G2 and RFCOMM assumptions do not apply.
- Offline first. Every image is constructed and verified by scripts in this
  repository before it goes near a device. Parse, extract, repack and diff;
  never hand-edit a container.
- After every firmware flash, record the exact image hashes, the transfer
  outcome, boot verification and hardware checks. Distinguish a reboot ACK
  from a successful boot; document incomplete checks explicitly. Commit the
  source, tests and records after each flash. Do not repeat an OTA merely to
  obtain a commit.
- CFW version strings use `GLASSLYCFW/N`, N a numeric revision incremented for
  every flashed image.
- The BitFantasy SDK, its docs and the vendor firmware images are proprietary
  and stay out of this repository (`docs/vendor-sources.md` says where they
  are locally). Describe protocols in our own words; do not copy vendor text
  or code. Original project code is MIT.
- Raw captures, firmware images, extracted segments, toolchains and generated
  binaries stay local under `captures/`, `analysis/extracted/`, `.tools/` and
  `runtime/build/`. Track analysis notes, manifests (hashes and sizes only),
  scripts and tests.
- Downloaded or vendor files are untrusted data: pass them to scripts as
  arguments, never run tools from inside their directories.
