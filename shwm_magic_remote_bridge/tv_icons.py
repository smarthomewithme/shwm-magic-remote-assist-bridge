"""Generated 80x80 PNG status icons for LG webOS notification toast.

Pure stdlib; images are only written to the TV's temporary /tmp location
when the owner opts in. Nothing is installed in the system partitions.
"""
from __future__ import annotations

import math
import struct
import zlib

KINDS = ("listen", "processing", "done", "error")
RGB = {
    "listen": (37, 111, 195),
    "processing": (106, 78, 171),
    "done": (24, 139, 102),
    "error": (183, 76, 76),
}


def _segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _white(kind, x, y):
    if kind == "listen":
        cap = (32 <= x <= 48 and 24 <= y <= 45
               and ((27 <= y <= 42) or math.hypot(x - 40, y - 29) <= 8
                    or math.hypot(x - 40, y - 41) <= 8))
        sides = (_segment(x, y, 27, 39, 28, 48) < 2.2
                 or _segment(x, y, 53, 39, 52, 48) < 2.2
                 or _segment(x, y, 28, 48, 40, 54) < 2.2
                 or _segment(x, y, 40, 54, 52, 48) < 2.2
                 or _segment(x, y, 40, 54, 40, 62) < 2.3
                 or _segment(x, y, 32, 63, 48, 63) < 2.2)
        return cap or sides
    if kind == "processing":
        return any(math.hypot(x - px, y - 40) <= 4.5 for px in (26, 40, 54))
    if kind == "done":
        return (_segment(x, y, 23, 41, 35, 52) < 4
                or _segment(x, y, 35, 52, 58, 29) < 4)
    return (_segment(x, y, 29, 29, 51, 51) < 3.5
            or _segment(x, y, 51, 29, 29, 51) < 3.5)


def icon_png(kind):
    """Return a valid RGBA PNG, 80x80; no disk I/O and no dependencies."""
    if kind not in RGB:
        raise ValueError("Unknown icon kind")
    rows = bytearray()
    color = RGB[kind]
    for y in range(80):
        rows.append(0)
        for x in range(80):
            dx, dy = x - 39.5, y - 39.5
            if dx * dx + dy * dy <= 35 * 35:
                rgba = (*color, 255)
                if _white(kind, x, y):
                    rgba = (255, 255, 255, 255)
            else:
                rgba = (0, 0, 0, 0)
            rows.extend(rgba)

    def chunk(ctype, data):
        return (struct.pack(">I", len(data)) + ctype + data
                + struct.pack(">I", zlib.crc32(ctype + data) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 80, 80, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
            + chunk(b"IEND", b""))
