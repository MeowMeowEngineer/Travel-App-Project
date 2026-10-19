"""The site's brand kit, redrawn as SVG geometry from the raster logo the operator chose (2026-10-19: concept A, a
cable-stayed bridge pylon in a bookmark — incoming/brand/logo-a-bridge.png, with its mono and reverse renderings).

    pip install shapely fonttools brotli          # this tool only (boolean geometry, Pretendard outlines)
    python tools/brand_kit.py --data data/incheon --out templates/assets/brand [--png]

Names and colours come from site.json: site_name (the Korean name), city.intl.en.site_name (the English name),
brand_symbol (the files' prefix: '<prefix>-symbol.svg'), brand_colors {sea, coral, ink}; the emphasised end of each
name ('…각', '…gak') is pipeline/present.wordmark's (city.brand_em, else BRAND_EM).

The symbol is measured on the 1254 px raster (the bookmark spans x 291–963, y 226–1026 there) and drawn in a box 100
units wide (k = 100 / 672): the bookmark (rounded top corners, rounded bottom corners, the notch), the pylon (two
posts with a closing slit, the window, the legs), three stay cables a side, the deck and the wave are cut out of it as
one path (shapely: bookmark minus the union of the cut-outs, even-odd fill), so the ground shows through as on the
raster — white on the site's light bar, the app icon's blue in the app icon; the sun is a coral circle on the plain
symbol and a cut-out on the reverse and mono ones (as the operator's mono and reverse renderings show it).

Writes <prefix>-symbol.svg (decorative, inlined beside the site name in the header and footer: site.json brand_symbol),
<prefix>-symbol-reverse.svg (white, for dark grounds), <prefix>-symbol-mono.svg (ink), <prefix>-logo.svg (the
horizontal logo: the symbol, the Korean name over the English one, outlined from Pretendard Bold — the vendored woff2
subsets, templates/assets/vendor/pretendard — head in ink, emphasised end in the sea blue) and <prefix>-app-icon.svg
(the reverse symbol on a sea-blue rounded square). With --png also icon-48/96/180/192/512.png (the app icon full bleed:
the platforms round it) and favicon.ico (16/32/48, rounded), screenshots made with Playwright's Chromium."""
from __future__ import annotations

import argparse
import glob
import io
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "templates" / "assets" / "vendor" / "pretendard"

# ---------------------------------------------------------------- the raster's geometry (px on the 1254 px image)
LEFT, RIGHT, TOP, BOTTOM = 291.0, 963.0, 226.0, 1026.0
CX = (LEFT + RIGHT) / 2                       # 627: everything is drawn symmetric about it
K = 100.0 / (RIGHT - LEFT)                    # px -> symbol units
TOP_R = 54.0                                  # the top corners
FOOT_R = 43.5                                 # the bottom corners (tangent to the side and to the notch's edge)
NOTCH_SLOPE = 0.4676                          # the bottom edge rises this much per px towards the middle
NOTCH_Y = 1006.0 + NOTCH_SLOPE * (387 - CX)   # where the two bottom edges would meet (893.8)
NOTCH_R = 12.0                                # the notch's rounded apex
# the pylon's left half (the right half mirrors it): its outer edge, top to the foot of the leg
PYLON_OUTER = [(592, 354), (576, 510), (570, 540), (557, 600), (544, 650), (531, 700), (519, 742), (503, 799)]
SLIT = ((620, 354), (CX, 458))                # the slit between the two posts closes at the middle
WINDOW_TOP = 512.5                            # the window between the legs, its inner edge from (620, 512.5) …
INNER_FOOT = (564, 799)                       # … to the inside of the foot
LEG_FOOT_Y = 799.0
# the stay cables of the left side: (a point on the centre line, dx/dy) and how far each runs (y from, y to)
CABLES = [((568.0, 430.0), -1.413, 409.0, 700.0),
          ((565.0, 480.0), -1.233, 460.0, 760.0),
          ((553.5, 540.0), -0.997, 509.0, 730.0)]
CABLE_W = 13.2
DECK = (711.0, 742.0)                         # the deck: a band across the whole bookmark
WAVE_Y, WAVE_A, WAVE_L, WAVE_X0, WAVE_W = 846.2, 13.0, 176.0, 450.5, 27.5   # centre line y = Y + A cos(2π(x-X0)/L), fitted
SUN = (766.0, 363.0, 61.5)


def u(x: float, y: float) -> tuple[float, float]:
    return ((x - LEFT) * K, (y - TOP) * K)


H = (BOTTOM - TOP) * K                         # the symbol's height in units (119.05)


def mirror(pts):
    return [(2 * CX - x, y) for x, y in pts]


def arc(cx, cy, r, a0, a1, n=24):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def notch_apex():
    """The rounded apex of the notch, left tangent point to right tangent point (y down)."""
    k = math.hypot(1, NOTCH_SLOPE)
    ay = NOTCH_Y + NOTCH_R * k
    s = math.atan(NOTCH_SLOPE)
    lt = (CX - NOTCH_R * math.sin(s), ay - NOTCH_R * math.cos(s))
    a0 = math.atan2(lt[1] - ay, lt[0] - CX)
    a1 = math.atan2(lt[1] - ay, CX - lt[0])   # the mirror point
    # from the left tangent point over the top (angles go through -π/2) to the right one
    return [(CX + NOTCH_R * math.cos(a0 + (a1 - a0) * i / 10), ay + NOTCH_R * math.sin(a0 + (a1 - a0) * i / 10))
            for i in range(11)]


def outline():
    from shapely.geometry import Polygon
    k = math.hypot(1, NOTCH_SLOPE)
    yc = 1006.0 + NOTCH_SLOPE * 387 - NOTCH_SLOPE * (LEFT + FOOT_R) - FOOT_R * k
    s = math.atan(NOTCH_SLOPE)
    # bottom-left corner: from the side (angle π) down round to the notch edge's tangent point (angle π/2 - s)
    foot_l = arc(LEFT + FOOT_R, yc, FOOT_R, math.pi, math.pi / 2 - s, 20)
    foot_r = [(2 * CX - x, y) for x, y in foot_l]          # the right side down round to its notch edge
    top_l = arc(LEFT + TOP_R, TOP + TOP_R, TOP_R, math.pi, 1.5 * math.pi, 20)
    top_r = arc(RIGHT - TOP_R, TOP + TOP_R, TOP_R, 1.5 * math.pi, 2 * math.pi, 20)
    apex = notch_apex()                       # left → right; on the ring we go right → left (clockwise in y-down)
    ring = top_l + top_r + foot_r + apex[::-1] + foot_l[::-1]
    return Polygon(ring).buffer(0)


def pylon():
    from shapely.geometry import Polygon
    (sx, sy), (ax, ay) = SLIT
    left_outer = [(float(x), float(y)) for x, y in PYLON_OUTER]
    # one ring: the left post's top, the slit down to the middle and up to the right post, down the right outer edge
    # to its foot, up the window's right edge, across its top, down its left edge to the left foot, up the left edge
    inner_top = (620.0, WINDOW_TOP)
    right_outer = [(2 * CX - x, y) for x, y in left_outer]
    ring = ([left_outer[0], (sx, sy), (ax, ay), (2 * CX - sx, sy)] + right_outer
            + [(2 * CX - INNER_FOOT[0], LEG_FOOT_Y), (2 * CX - inner_top[0], WINDOW_TOP), inner_top,
               (INNER_FOOT[0], LEG_FOOT_Y)] + left_outer[::-1][:-1])
    return Polygon(ring).buffer(0)


def cables():
    from shapely.geometry import LineString
    out = []
    for (x0, y0), slope, ya, yb in CABLES:
        pts = [(x0 + slope * (y - y0), y) for y in (ya, yb)]
        for p in (pts, mirror(pts)):
            out.append(LineString(p).buffer(CABLE_W / 2, cap_style=2))
    return out


def wave():
    from shapely.geometry import LineString
    xs = [LEFT - 40 + i * 2.0 for i in range(int((RIGHT - LEFT + 80) / 2) + 1)]
    line = LineString([(x, WAVE_Y + WAVE_A * math.cos(2 * math.pi * (x - WAVE_X0) / WAVE_L)) for x in xs])
    return line.buffer(WAVE_W / 2, cap_style=2, resolution=12)


def deck():
    from shapely.geometry import box
    return box(LEFT - 20, DECK[0], RIGHT + 20, DECK[1])


def sun():
    from shapely.geometry import Point
    x, y, r = SUN
    return Point(x, y).buffer(r, resolution=32)


def symbol_shape(sun_hole: bool):
    from shapely.ops import unary_union
    cuts = unary_union([pylon(), deck(), wave(), *cables(), *([sun()] if sun_hole else [])])
    return outline().difference(cuts)


def fmt(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def path_d(geom, tol: float = 0.03) -> str:
    """SVG path data (symbol units) of a shapely (multi)polygon: every ring as M…L…Z, holes included (even-odd)."""
    from shapely import affinity
    g = affinity.affine_transform(geom, [K, 0, 0, K, -LEFT * K, -TOP * K]).simplify(tol, preserve_topology=True)
    polys = getattr(g, "geoms", [g])
    parts = []
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            pts = list(ring.coords)[:-1]
            parts.append("M" + "L".join(f"{fmt(x)} {fmt(y)}" for x, y in pts) + "Z")
    return "".join(parts)


def sun_circle(fill: str) -> str:
    x, y = u(SUN[0], SUN[1])
    return f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="{fmt(SUN[2] * K)}" fill="{fill}"/>'


def symbol_body(fill: str, sun_fill: str | None) -> str:
    """The symbol in its 100 × H box: the bookmark with its cut-outs, the sun drawn (sun_fill) or cut out (None)."""
    body = f'<path fill="{fill}" fill-rule="evenodd" d="{path_d(symbol_shape(sun_fill is None))}"/>'
    return body + (sun_circle(sun_fill) if sun_fill else "")


# ---------------------------------------------------------------- the names, outlined from Pretendard Bold
class Font:
    def __init__(self, text: str):
        from fontTools.ttLib import TTFont
        self.faces = []
        for f in sorted(glob.glob(str(FONT_DIR / "Pretendard-Bold.*.woff2"))):
            t = TTFont(f)
            cmap = t.getBestCmap()
            if any(ord(c) in cmap for c in text):
                self.faces.append((t, cmap))
        missing = [c for c in text if not any(ord(c) in cm for _, cm in self.faces)]
        if missing:
            raise SystemExit(f"Pretendard Bold 조각에 없는 글자: {''.join(missing)}")

    def glyph(self, ch: str):
        for t, cm in self.faces:
            if ord(ch) in cm:
                return t, cm[ord(ch)]
        raise KeyError(ch)

    def path(self, text: str, size: float, x0: float, base: float, tracking: float = 0.0) -> tuple[list[str], float]:
        """Path data per character at font size `size`, left edge x0, baseline `base`; and the right edge."""
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.pens.transformPen import TransformPen
        out, x = [], x0
        for ch in text:
            t, g = self.glyph(ch)
            upm = t["head"].unitsPerEm
            sc = size / upm
            gs = t.getGlyphSet()
            pen = SVGPathPen(gs, ntos=lambda v: fmt(v))
            gs[g].draw(TransformPen(pen, (sc, 0, 0, -sc, x, base)))
            out.append(pen.getCommands())
            x += t["hmtx"][g][0] * sc + tracking * size
        return out, x - tracking * size

    def ink(self, text: str, size: float, tracking: float = 0.0) -> tuple[float, float, float, float]:
        """(xmin, ymin, xmax, ymax) of the ink, x from the pen start, y from the baseline (negative = above)."""
        from fontTools.pens.boundsPen import BoundsPen
        x, b = 0.0, [1e9, 1e9, -1e9, -1e9]
        for ch in text:
            t, g = self.glyph(ch)
            sc = size / t["head"].unitsPerEm
            bp = BoundsPen(t.getGlyphSet())
            t.getGlyphSet()[g].draw(bp)
            if bp.bounds:
                a, c, d, e = bp.bounds
                b = [min(b[0], x + a * sc), min(b[1], -e * sc), max(b[2], x + d * sc), max(b[3], -c * sc)]
            x += t["hmtx"][g][0] * sc + tracking * size
        return tuple(b)


def split_em(name: str, ems) -> tuple[str, str]:
    for em in ems:
        if name.endswith(em) and len(name) > len(em):
            return name[: -len(em)], em
    return name, ""


def words(font: Font, text: str, em_ends, size, x0, base, tracking, fill, em_fill) -> str:
    head, tail = split_em(text, em_ends)
    parts, _ = font.path(text, size, x0, base, tracking)
    n = len(head)
    d_head, d_tail = " ".join(parts[:n]), " ".join(parts[n:])
    if not d_tail or em_fill == fill:
        return f'<path fill="{fill}" d="{(d_head + " " + d_tail).strip()}"/>'
    return f'<path fill="{fill}" d="{d_head}"/><path fill="{em_fill}" d="{d_tail}"/>'


def logo(ko: str, en: str, ems, colors: dict) -> str:
    """The horizontal logo: the symbol (100 × H) and, beside it, the Korean name over the English one."""
    font = Font(ko + en)
    ks, es, kt, et = 60.0, 25.5, -0.03, -0.01
    kb, eb = font.ink(ko, ks, kt), font.ink(en, es, et)
    x0 = 100 + 20
    ko_base = 9 - kb[1]                        # the Korean ink's top near the bookmark's top
    en_base = ko_base + kb[3] + 13 - eb[1]     # the English ink 13 units under it
    body = symbol_body(colors["sea"], colors["coral"])
    body += words(font, ko, ems, ks, x0 - kb[0], ko_base, kt, colors["ink"], colors["sea"])
    body += words(font, en, ems, es, x0 - eb[0] + 1.5, en_base, et, colors["ink"], colors["sea"])
    w = max(x0 + kb[2] - kb[0], x0 + 1.5 + eb[2] - eb[0]) + 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {fmt(w)} {fmt(H)}" role="img" '
            f'aria-label="{ko} {en}">{body}</svg>\n')


def app_icon(colors: dict, size: int = 512, rounded: bool = True) -> str:
    """The reverse symbol (white, the sun and the bridge cut out) on a sea-blue square — rounded (22 %) for the SVG and
    the favicon, full bleed for the platform icons (they round it themselves); the symbol is 64 % of the side high."""
    s = float(size)
    h = 0.64 * s
    sc = h / H
    w = 100 * sc
    tx, ty = (s - w) / 2, (s - h) / 2
    rx = f' rx="{fmt(0.22 * s)}"' if rounded else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" role="img" aria-label="{{name}}">'
            f'<rect width="{size}" height="{size}"{rx} fill="{colors["sea"]}"/>'
            f'<g transform="translate({fmt(tx)} {fmt(ty)}) scale({sc:.4f})">{symbol_body("#FFFFFF", None)}</g></svg>\n')


def symbol_svg(fill: str, sun_fill: str | None) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 {fmt(H)}" aria-hidden="true" focusable="false">'
            f'{symbol_body(fill, sun_fill)}</svg>\n')


# ---------------------------------------------------------------- PNG icons (Playwright's Chromium)
def screenshot(svgs: dict[int, str]) -> dict[int, bytes]:
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(device_scale_factor=1)
        for px, svg in svgs.items():
            page.set_viewport_size({"width": px, "height": px})
            page.set_content(f'<html><body style="margin:0;background:transparent">'
                             f'<div style="width:{px}px;height:{px}px">{svg.replace("<svg ", f"<svg width=\"{px}\" height=\"{px}\" ", 1)}</div>'
                             f'</body></html>')
            out[px] = page.screenshot(clip={"x": 0, "y": 0, "width": px, "height": px}, omit_background=True)
        b.close()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "incheon")
    ap.add_argument("--out", type=Path, default=ROOT / "templates" / "assets" / "brand")
    ap.add_argument("--png", action="store_true", help="icon-*.png와 favicon.ico도 만든다(Playwright Chromium)")
    a = ap.parse_args(argv)
    site = json.loads((a.data / "site.json").read_text("utf-8"))
    sys.path.insert(0, str(ROOT))
    from pipeline import city, present
    city.activate(site)
    ko = site["site_name"]
    en = (((site.get("city") or {}).get("intl") or {}).get("en") or {}).get("site_name") or ""
    prefix = str(site.get("brand_symbol") or "").removesuffix("-symbol.svg")
    colors = site.get("brand_colors") or {}
    if not (ko and en and prefix and all(colors.get(k) for k in ("sea", "coral", "ink"))):
        ap.error("site.json에 site_name, city.intl.en.site_name, brand_symbol('<이름>-symbol.svg'), "
                 "brand_colors{sea, coral, ink}가 있어야 합니다")
    ems = city.current().get("brand_em") or present.BRAND_EM
    a.out.mkdir(parents=True, exist_ok=True)
    files = {
        f"{prefix}-symbol.svg": symbol_svg(colors["sea"], colors["coral"]),
        f"{prefix}-symbol-reverse.svg": symbol_svg("#FFFFFF", None),
        f"{prefix}-symbol-mono.svg": symbol_svg(colors["ink"], None),
        f"{prefix}-logo.svg": logo(ko, en, ems, colors),
        f"{prefix}-app-icon.svg": app_icon(colors).replace("{name}", ko),
    }
    for name, svg in files.items():
        (a.out / name).write_text(svg, "utf-8")
        print(f"{a.out / name} ({len(svg.encode())} B)")
    if a.png:
        from PIL import Image
        full = screenshot({px: app_icon(colors, px, rounded=False).replace("{name}", ko) for px in (48, 96, 180, 192, 512)})
        for px, png in full.items():
            im = Image.open(io.BytesIO(png)).convert("RGBA")
            im.save(a.out / f"icon-{px}.png", optimize=True)
            print(a.out / f"icon-{px}.png")
        ico = screenshot({px: app_icon(colors, px, rounded=True).replace("{name}", ko) for px in (16, 32, 48)})
        imgs = [Image.open(io.BytesIO(ico[px])).convert("RGBA") for px in (16, 32, 48)]
        imgs[-1].save(a.out / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=imgs[:-1])
        print(a.out / "favicon.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
