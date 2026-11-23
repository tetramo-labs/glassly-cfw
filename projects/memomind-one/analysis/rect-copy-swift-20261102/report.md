# Swift rectangle-copy encoder

`RasterCommands.rectangleCopy(source:destination:)` returns the exact17-byte ordinary mode9 command: byte09, then source(x,y,width,height) and destination(x,y,width,height), each unsigned little-endian16. `RasterRectangle` accepts integer coordinates; the encoder validates before narrowing. Both rectangles must have positive, equal dimensions and fit600×350. Odd coordinates/sizes, overlaps and self-copy are valid. No clipping, RLE, zlib, transport or implicit display/session operations occur.

The pinned original `zlib_glue.c` mode9 branch is the format authority. Its89 variant contains first/left then second/right pairs; `FW_SIDE()==2` selectsfirst/left. Only that selected pair is checked. The MemoMind nativeadapter has declared first/left mapping; the Swift API emits09only and does not manufacture a second lens. Original09/89 consume minimum17/33bytes and ignore trailing bytes; Swift emits exactly17.

Five new Swift test methods and eight existing raster test methods passed. Six independent `struct.pack` wire fixtures were checked by compiling the entire original mode9 branch verbatim. All72 branch checks passed, covering ordinary selection,89left/right selection, ignored rightpair, trailing bytes, every truncated length, and invalid rectangles. Native dependency mocks only record chosen copy arguments; this is not framebuffer or hardware evidence. `reference.json` records source and branch hashes, and `report.json` records final Swift source hashes.

The original scalar implementation is MIT; source revision1a6db4fd75de202a96599cc8f9f12fa721e7c3ce. License reference: `LICENSE`. The generation script is an explicit developer fixture generator: it recompiles analysis-local reference code and rewrites the generated Swift fixture file. Normal Swift tests do not execute Python or C.

The prior mode3 documentation now correctly says to send a mode6 keyframe first to establish the intended base; it no longer claims receiver enforcement. No behavior changed in the mode3/6 implementation. No hardware, firmware catalog, CLI, keyboard or native-source edits were performed.
