"""Builds the Windows icon (PNG images inside an .ico container, which Windows Vista and later read) from the
app's PNG icons."""

import struct
import sys
from pathlib import Path

ICONS = Path(__file__).resolve().parents[1] / "src" / "bilge" / "app" / "resources"


def build(sources: list[Path], destination: Path) -> None:
    images = [path.read_bytes() for path in sources]
    sizes = [struct.unpack(">II", image[16:24]) for image in images]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for (width, height), image in zip(sizes, images, strict=True):
        # 256 is written as 0 in the directory.
        entries += struct.pack("<BBBBHHII", width % 256, height % 256, 0, 0, 1, 32, len(image), offset)
        offset += len(image)
    destination.write_bytes(header + entries + b"".join(images))


if __name__ == "__main__":
    build([ICONS / "bilge-64.png", ICONS / "bilge.png"], Path(sys.argv[1]))
