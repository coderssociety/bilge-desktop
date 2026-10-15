"""Pixels to PNG and to the Windows clipboard's bitmap format (DIB) and back, so screenshots need no image library."""

import struct
import zlib
from dataclasses import dataclass

_HEADER = struct.Struct("<IiiHHIIiiII")
_BI_RGB, _BI_BITFIELDS = 0, 3


@dataclass(frozen=True)
class Pixels:
    """Top-down rows of blue, green, red, alpha bytes, as Windows' GDI hands them over."""

    width: int
    height: int
    bgra: bytes


def png(pixels: Pixels) -> bytes:
    rows = bytearray()
    stride = pixels.width * 4
    for y in range(pixels.height):
        row = pixels.bgra[y * stride : (y + 1) * stride]
        rgb = bytearray(pixels.width * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = row[2::4], row[1::4], row[0::4]
        rows += b"\0" + rgb

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", pixels.width, pixels.height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )


def dib(pixels: Pixels) -> bytes:
    """A 32-bit bottom-up DIB, which every Windows app pastes."""
    stride = pixels.width * 4
    rows = [pixels.bgra[y * stride : (y + 1) * stride] for y in range(pixels.height)]
    header = _HEADER.pack(_HEADER.size, pixels.width, pixels.height, 1, 32, _BI_RGB, stride * pixels.height, 0, 0, 0, 0)
    return header + b"".join(reversed(rows))


def from_dib(data: bytes) -> Pixels:
    """What the Snipping Tool leaves on the clipboard: 24- or 32-bit, either row order."""
    if len(data) < _HEADER.size:
        raise ValueError("Not a bitmap")
    size, width, height, _, bits, compression, *_ = _HEADER.unpack_from(data)
    if bits not in (24, 32) or compression not in (_BI_RGB, _BI_BITFIELDS) or width <= 0 or height == 0:
        raise ValueError(f"Unsupported bitmap: {bits} bits, compression {compression}")
    offset = size + (12 if compression == _BI_BITFIELDS and size == _HEADER.size else 0)
    stride = (width * bits // 8 + 3) & ~3
    rows = abs(height)
    if len(data) < offset + stride * rows:
        raise ValueError("Bitmap is cut short")
    out = bytearray()
    order = range(rows - 1, -1, -1) if height > 0 else range(rows)
    for y in order:
        row = data[offset + y * stride : offset + y * stride + width * bits // 8]
        if bits == 32:
            out += row
        else:
            converted = bytearray(width * 4)
            converted[0::4], converted[1::4], converted[2::4] = row[0::3], row[1::3], row[2::3]
            converted[3::4] = b"\xff" * width
            out += converted
    return Pixels(width, rows, bytes(out))
