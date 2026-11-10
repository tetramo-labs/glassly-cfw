#!/usr/bin/env python3
"""Build G2 scene messages for hardware tests of the NIMO runtime (command 0x7E 0x20).

Immediate geometry (mode 36): [36][count][records], each record
[type][flags][color 0..15][width][p0..p7 signed LE16], 20 bytes. Types used here:
1 line (x0,y0,x1,y1), 2/3 rounded rect outline/filled (x,y,w,h,radius),
4/5 circle outline/filled (cx,cy,r). Coordinates are panel pixels (540x280).
"""
import argparse
from pathlib import Path
import struct

LINE, RECT, RECT_FILL, CIRCLE, CIRCLE_FILL = 1, 2, 3, 4, 5


def record(kind, color, width, *params):
    values = list(params) + [0] * (8 - len(params))
    return struct.pack("<BBBB8h", kind, 0, color & 0x0F, width, *values)


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", choices=["demo"])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = {"demo": demo}[args.scene]()
    args.output.write_bytes(data)
    print(f"{args.output}: {len(data)} bytes")


if __name__ == "__main__":
    main()
