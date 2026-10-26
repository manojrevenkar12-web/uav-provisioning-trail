"""Appends the CRC-32 of the image, which the firmware checks at boot (src/main.c image_ok)."""

import sys
import zlib
from pathlib import Path

path = Path(sys.argv[1])
image = path.read_bytes()
path.write_bytes(image + zlib.crc32(image).to_bytes(4, "little"))
