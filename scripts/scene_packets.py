#!/usr/bin/env python3
"""Build G2 scene messages for hardware tests of the NIMO runtime (command 0x7E 0x20).

Immediate geometry (mode 36): [36][count][records], each record
[type][flags][color 0..15][width][p0..p7 signed LE16], 20 bytes. Types used here:
1 line (x0,y0,x1,y1), 2/3 rounded rect outline/filled (x,y,w,h,radius),
4/5 circle outline/filled (cx,cy,r). Coordinates are panel pixels (540x280).

  demo OUT        one mode-36 frame (border, diagonals, gray circles)
  cues DIR        mode-36 frames that ask the wearer for a touch, for the input
                  steps (no text yet): a filled circle on the side to tap, a
                  bar for a long press
  retained DIR    retained-scene messages that replay in order after an acquire,
                  using a fixed epoch (adopted by the RESET in the first file)
                  and distinct request ids, so no reply has to be read:
    scene-retained.bin    bundle: RESET, PUT border/circle/line/box, SHOW + glide
    scene-eyes.bin        bundle: PUT a left-only and a right-only block, SHOW all
    scene-show-right.bin  SHOW naming the right eye: only the circle
    scene-show-left.bin   SHOW naming the left eye: only the border
    scene-show-both.bin   SHOW for both eyes: the retained scene again

Offline only; writes files, never talks to a device.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

LINE, RECT, RECT_FILL, CIRCLE, CIRCLE_FILL = 1, 2, 3, 4, 5
W, H = 540, 280
EPOCH = 0x4E35
PRESENT, KEEP, TAG = 0x01, 0x02, 0x04
LEFT_EYE, RIGHT_EYE = 0x10, 0x20             # SHOW flag bits 4-5
LEFT_ONLY, RIGHT_ONLY = 0x80000000, 0xC0000000  # object id bit 31 (+ bit 30 right)
VISIBLE = 0x01
LINEAR = bytes([0, 0, 255, 255])


def record(kind, color, width, *params, flags=0):
    values = list(params) + [0] * (8 - len(params))
    return struct.pack("<BBBB8h", kind, flags, color & 0x0F, width, *values)


def geometry(records):
    return bytes([36, len(records)]) + b"".join(records)


def demo():
    records = [
        record(RECT, 15, 3, 2, 2, 536, 276, 16),
        record(LINE, 8, 2, 20, 20, 520, 260),
        record(LINE, 8, 2, 20, 260, 520, 20),
    ]
    for i in range(8):
        records.append(record(CIRCLE_FILL, 2 + i * 2, 0, 70 + i * 57, 140, 22))
    records.append(record(CIRCLE, 15, 2, 270, 140, 110))
    return geometry(records)


def cues():
    def frame(*shapes):
        # Mode 36 draws over whatever the canvas holds: black first.
        return geometry([record(RECT_FILL, 0, 0, 0, 0, W, H, 0), record(RECT, 6, 2, 2, 2, 536, 276, 16), *shapes])
    return {
        "cue-tap-right.bin": frame(record(CIRCLE_FILL, 15, 0, 420, 140, 60)),
        "cue-tap-left.bin": frame(record(CIRCLE_FILL, 15, 0, 120, 140, 60)),
        "cue-long-right.bin": frame(record(RECT_FILL, 15, 0, 320, 115, 200, 50, 20)),
    }


def header(mode, request):
    return struct.pack("<BHH", mode, EPOCH, request)


def reset(request):
    return header(41, request) + bytes([0])


def put_objects(request, objects):
    return header(37, request) + b"".join(struct.pack("<BII", 1, oid, 1) + rec for oid, rec in objects)


def show(request, ids, flags, ops=b"", bg=0):
    refs = b"".join(struct.pack("<II", oid, 1) for oid in ids)
    return header(38, request) + struct.pack("<BBBH", flags, bg, 0, len(ids)) + refs + ops


def glide(oid, dx, dy, frames):
    return struct.pack("<BIhhB", 4, oid, dx, dy, frames) + LINEAR


def bundle(*segments):
    return bytes([8, len(segments)]) + b"".join(struct.pack("<H", len(s)) + s for s in segments)


SCENE = [
    (1, record(RECT, 15, 2, 8, 8, W - 16, H - 16, 12, flags=VISIBLE)),
    (2, record(CIRCLE_FILL, 11, 0, W // 2, H // 2, 70, flags=VISIBLE)),
    (3, record(LINE, 7, 3, 40, H - 40, W - 40, 40, flags=VISIBLE)),
    (4, record(RECT_FILL, 15, 0, 40, 40, 70, 50, 6, flags=VISIBLE)),
]
EYES = [
    (LEFT_ONLY | 0x10, record(RECT_FILL, 15, 0, 40, 180, 90, 60, 8, flags=VISIBLE)),
    (RIGHT_ONLY | 0x11, record(RECT_FILL, 15, 0, W - 130, 180, 90, 60, 8, flags=VISIBLE)),
]


def retained():
    ids = [oid for oid, _ in SCENE]
    return {
        "scene-retained.bin": bundle(reset(1), put_objects(2, SCENE),
                                     show(3, ids, PRESENT | TAG, glide(4, W - 150, 0, 60))),
        "scene-eyes.bin": bundle(put_objects(4, EYES), show(5, ids + [oid for oid, _ in EYES], PRESENT)),
        "scene-show-right.bin": show(6, [2], PRESENT | RIGHT_EYE),
        "scene-show-left.bin": show(7, [1], PRESENT | LEFT_EYE),
        "scene-show-both.bin": show(8, ids, PRESENT),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scene", choices=["demo", "retained", "cues"])
    parser.add_argument("output", type=Path, help="file for demo, directory for retained")
    args = parser.parse_args()
    if args.scene == "demo":
        data = demo()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
        print(f"{args.output}: {len(data)} bytes")
        return
    args.output.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, data in (retained() if args.scene == "retained" else cues()).items():
        (args.output / name).write_bytes(data)
        files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        print(f"{args.output / name}: {len(data)} bytes")
    (args.output / f"{args.scene}.json").write_text(json.dumps({"epoch": EPOCH, "files": files}, indent=2) + "\n")


if __name__ == "__main__":
    main()
