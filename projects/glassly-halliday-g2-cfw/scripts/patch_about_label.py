"""Build the Halliday G2 build 2279 About-label experiment from a stock OTA."""

import argparse
import hashlib
from pathlib import Path
from zipfile import ZipFile


STOCK_SHA256 = "76b7c0785d4487c5c20ab675d46bb1fc2d35a5a2a86c5596d40e0752c824bc3b"
OFFSET = 0x184D24
OLD_LABEL = b"Halliday Glasses"
NEW_LABEL = b"Glassly G2 (CFW)"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_ota", type=Path)
    parser.add_argument("output_image", type=Path)
    args = parser.parse_args()

    with ZipFile(args.stock_ota) as archive:
        image = bytearray(archive.read("nuttx_ap.bin"))
    if hashlib.sha256(image).hexdigest() != STOCK_SHA256:
        parser.exit(1, "Unexpected AP image. Use the stock Halliday G2 build 2279 OTA.\n")

    end = OFFSET + len(OLD_LABEL)
    if len(NEW_LABEL) != len(OLD_LABEL) or image[OFFSET:end + 1] != OLD_LABEL + b"\0":
        parser.exit(1, "Label layout mismatch. Check the build 2279 label before editing.\n")
    image[OFFSET:end] = NEW_LABEL
    with args.output_image.open("xb") as output:
        output.write(image)
    print(hashlib.sha256(image).hexdigest(), args.output_image)


if __name__ == "__main__":
    main()
