"""Render the favicon rasters from mtg_collector/static/favicon.svg.

The SVG is the header's brand mark (collection.html's .brand-logo); the PNGs and
the ICO are derived from its <rect> elements, so nothing here draws its own art.
tests/test_favicon_derivation.py regenerates these bytes and compares.

    python3 scripts/build_favicons.py
"""
import math
import re
import struct
import zlib
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "mtg_collector" / "static"
ACCENT = (0xE9, 0x45, 0x60)
BG = (0x1A, 0x1A, 0x2E)
SS = 4


def parse_svg(text):
    """Return (viewBox size, stroke width, [(x, y, w, h, rx, angle, cx, cy)])."""
    vb = float(re.search(r'viewBox="0 0 (\d+) \1"', text).group(1))
    sw = float(re.search(r'stroke-width="([\d.]+)"', text).group(1))
    rects = []
    for m in re.finditer(r"<rect ([^>]*?)/>", text):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        ang, cx, cy = map(float, re.fullmatch(r"rotate\(([-\d.]+) ([-\d.]+) ([-\d.]+)\)", a["transform"]).groups())
        rects.append((float(a["x"]), float(a["y"]), float(a["width"]), float(a["height"]), float(a["rx"]), ang, cx, cy))
    return vb, sw, rects


def _covered(px, py, sw, rects):
    for x, y, w, h, rx, ang, cx, cy in rects:
        t = math.radians(-ang)
        dx, dy = px - cx, py - cy
        lx = cx + dx * math.cos(t) - dy * math.sin(t)
        ly = cy + dx * math.sin(t) + dy * math.cos(t)
        qx = abs(lx - (x + w / 2)) - (w / 2 - rx)
        qy = abs(ly - (y + h / 2)) - (h / 2 - rx)
        d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - rx
        if abs(d) <= sw / 2:
            return True
    return False


def render(svg_text, size, pad_frac=0.0, background=None):
    """RGBA bytes, the art centred on a square canvas, never stretched."""
    vb, sw, rects = parse_svg(svg_text)
    scale = size * (1 - 2 * pad_frac) / vb
    off = size * pad_frac
    rows = []
    for j in range(size):
        row = bytearray()
        for i in range(size):
            hits = 0
            for sj in range(SS):
                for si in range(SS):
                    ux = (i + (si + 0.5) / SS - off) / scale
                    uy = (j + (sj + 0.5) / SS - off) / scale
                    hits += _covered(ux, uy, sw, rects)
            cov = hits / (SS * SS)
            if background:
                row += bytes(round(b + (a - b) * cov) for a, b in zip(ACCENT, background)) + b"\xff"
            else:
                row += bytes(ACCENT) + bytes([round(255 * cov)])
        rows.append(bytes(row))
    return rows


def png(rows):
    size = len(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(png32):
    return struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(png32), 22) + png32


def build(svg_text):
    p32 = png(render(svg_text, 32))
    return {
        "favicon-32.png": p32,
        "favicon.ico": ico(p32),
        "apple-touch-icon.png": png(render(svg_text, 180, pad_frac=0.18, background=BG)),
    }


if __name__ == "__main__":
    for name, data in build((STATIC / "favicon.svg").read_text()).items():
        (STATIC / name).write_bytes(data)
        print(name, len(data))
