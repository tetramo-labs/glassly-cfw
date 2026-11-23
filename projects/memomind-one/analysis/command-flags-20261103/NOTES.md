# Revision 5: command high-bit parity

G2 masks the high bit before dispatching cached images/fonts, shapes and cache
commands. The native standalone path previously rejected those aliases although
the bundle path already normalized them. Revision5 normalizes admission,
standalone scene dispatch, immediate drawing and cache-response selection while
preserving lens-specific raster/copy interpretation and rejecting nested carriers.
Capabilities advertise `modeHighBit: true`.

Build uses the full revision4 command with `--cfw-revision 5`; output `build-05`,
image `image-05`. Runtime is 96,128 bytes within the existing 98,304-byte RX
allocation. Only the metadata/app streams differ from the source OTA.

Native tests compare ordinary/high-bit RESET, PUT, SHOW, STATE, HIDE, immediate
shapes and keepalive, including reply bytes, scene pixels and owner disposal.
The first test fixture used truncated STATE/HIDE commands; it failed equally on
the ordinary path and was corrected to the upstream lengths. No firmware change
was needed for that fixture correction. The catalog test initially retained two
revision4 size constants; corrected to independently inspected revision5 sizes.
All other 135 Swift tests passed unchanged; the corrected new test also passes.
Text/diagnostic sanitizer tests, native compressed transport, wake ownership,
service gates and image reconstruction pass. No hardware result is inferred.

Glassly now requires revision5's capability contract and sends compressed records
on both platforms. The original Swift sender is copied unchanged; the Android
adapter uses the same persistent RFC1950/CRC/ACK protocol. Dashboard eligibility
requires revision5 or later. Earlier raw graphics fallback is removed.
