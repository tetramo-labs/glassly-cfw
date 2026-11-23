# Compiled Ananke patch

`payload.bin` is our 562-byte pi32v2/r3 patch, not an OEM application or device dump.
`payload.json` records the compiler output's symbols, edits, instruction audit and source hashes.
The public flasher checks both the payload and final application hashes before USB access.

Rebuild from the sources using `scripts/build-candidate.sh` with the pinned toolchain and private research inputs described in `docs/custom-firmware.md`. Do not commit the generated complete application or full-flash image.
