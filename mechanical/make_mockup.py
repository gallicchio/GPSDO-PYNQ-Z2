#!/usr/bin/env python3
"""
1:1 printable mechanical mockup for the GPSDO-PYNQ-Z2 front-end board.

Emits a two-page US-Letter LANDSCAPE PDF drawn at exactly 1:1 so it can be laid
over a real PYNQ-Z2.  Print at 100% / "Actual size" -- do NOT use "fit to page".
Check the 100 mm scale bar with a ruler before trusting anything else.

No external dependencies: writes raw PDF.

All coordinates are millimetres in a "global" frame whose origin is the
PYNQ-Z2's bottom-left corner, +X right, +Y up, viewed from above with the
Raspberry Pi header along the top edge.
"""
import math, os

MM = 72.0 / 25.4                      # PDF points per millimetre
PAGE_W, PAGE_H = 792.0, 612.0         # US Letter landscape, points

# ----------------------------------------------------------------------------
# PYNQ-Z2 geometry.  MEASURED with calipers, round 9 (prompt 9).  The two
# header numbers are reconciled rather than taken raw: the pin-1 and pin-39
# measurements span 48.10 mm where 19 pitches is exactly 48.26, so the row is
# anchored on their MIDPOINT (101.65) and stepped by the exact 2.54.  That is
# the only way to place a connector that has to mate.
# ----------------------------------------------------------------------------
PZ_W, PZ_H       = 137.0, 87.0        # measured
HDR_PIN1_X       = 125.78             # midpoint 101.65 + 19*2.54/2
HDR_ROW_ODD_DY   = 3.5                # measured, edge to pin centre
HDR_ROW_EVEN_DY  = 6.04               # 3.5 + exactly 2.54 (measured 6.1)
HDR_PITCH        = 2.54
HDR_PIN_H        = 8.0                # pin tops above the PYNQ, unshrouded
PZ_HOLE_TR       = (133.3, 4.3)       # measured, from top-LEFT
PZ_HOLE_TL       = (4.3, 4.3)         # measured
PZ_HOLE_D        = 3.0                # measured
# Tall things on the PYNQ.  Heights measured; X SPANS ARE STILL ESTIMATES and
# the only ones that matter are those under our board -- see round 9.
PZ_TALL = [(6.0, 19.0, 13.75, "ETHERNET"), (33.0, 50.0, 6.7, "USB-A"),
           (53.0, 69.5, 6.24, "HDMI OUT")]
PZ_TALL_OTHER = [("SD boot jumper (pull tab)", 13.0),
                 ("Arduino/shield headers", 8.3)]

HDR_ODD_Y  = PZ_H - HDR_ROW_ODD_DY    # y of odd pins  (pin 1,3,..39)
HDR_EVEN_Y = PZ_H - HDR_ROW_EVEN_DY   # y of even pins (pin 2,4,..40)

def header_pin_xy(n):
    """Global (x,y) of RPi header pin n, 1..40."""
    col = (n - 1) // 2                       # 0 at pin1/2 .. 19 at pin39/40
    x = HDR_PIN1_X - col * HDR_PITCH
    return (x, HDR_ODD_Y if n % 2 else HDR_EVEN_Y)

# ----------------------------------------------------------------------------
# Our board
# ----------------------------------------------------------------------------
BOARD_X0 = 72.0     # left edge: clears the measured HDMI right edge (69.5) by 2.5
BOARD_Y0 = 78.0     # bottom edge: 2.6 mm below the even pin row

SMA_PITCH   = 12.7  # 0.5 in, industry standard panel spacing
SMA_NUT_D   = 9.17  # SMA coupling nut, across corners
SMA_BODY_D  = 6.5   # jack body / footprint square

VARIANTS = {
 "A": dict(w=180.0, h=100.0, title="VARIANT A  --  two rows,  180 x 100 mm",
           rows=[(42.0, 13, 0.0), (80.0, 14, 0.0)]),
 "B": dict(w=120.0, h=115.0, title="VARIANT B  --  staggered,  120 x 115 mm",
           rows=[(34.0, 7, 0.0), (49.0, 7, SMA_PITCH/2),
                 (79.0, 7, 0.0), (94.0, 6, SMA_PITCH/2)]),
}

# Which unit each jack belongs to, in order, so the silkscreen story is visible
def jack_labels(total):
    lab = []
    u = 1
    while len(lab) < total - 3:
        lab += ["%d" % u, "P%d" % u]; u += 1
    lab = lab[:total - 3] + ["NUL", "HIN", "HO"]
    return lab[:total]

# ----------------------------------------------------------------------------
# Minimal PDF writer
# ----------------------------------------------------------------------------
class PDF:
    def __init__(self):
        self.pages = []
        self.buf = []
    def newpage(self):
        self.buf = []; self.pages.append(self.buf)
    def _c(self, s): self.buf.append(s)
    def rgb(self, r, g, b, stroke=True):
        self._c("%.3f %.3f %.3f %s" % (r, g, b, "RG" if stroke else "rg"))
    def lw(self, w): self._c("%.3f w" % w)
    def dash(self, on=0, off=0):
        self._c("[%g %g] 0 d" % (on, off) if on else "[] 0 d")
    def line(self, x0, y0, x1, y1):
        self._c("%.3f %.3f m %.3f %.3f l S" % (x0, y0, x1, y1))
    def rect(self, x, y, w, h, fill=False):
        self._c("%.3f %.3f %.3f %.3f re %s" % (x, y, w, h, "f" if fill else "S"))
    def circle(self, cx, cy, r, fill=False):
        k = 0.5522847498 * r
        self._c("%.3f %.3f m" % (cx + r, cy))
        self._c("%.3f %.3f %.3f %.3f %.3f %.3f c" % (cx+r, cy+k, cx+k, cy+r, cx, cy+r))
        self._c("%.3f %.3f %.3f %.3f %.3f %.3f c" % (cx-k, cy+r, cx-r, cy+k, cx-r, cy))
        self._c("%.3f %.3f %.3f %.3f %.3f %.3f c" % (cx-r, cy-k, cx-k, cy-r, cx, cy-r))
        self._c("%.3f %.3f %.3f %.3f %.3f %.3f c" % (cx+k, cy-r, cx+r, cy-k, cx+r, cy))
        self._c("f" if fill else "S")
    def text(self, x, y, s, size=7, font="F1"):
        s = s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        self._c("BT /%s %.2f Tf %.3f %.3f Td (%s) Tj ET" % (font, size, x, y, s))
    def textc(self, x, y, s, size=7):
        self.text(x - 0.28 * size * len(s) / 1.0 * 0.5 * 2 / 2, y, s, size)
    def save(self, path):
        objs = []
        def add(o): objs.append(o); return len(objs)
        font = None
        content_ids = []
        # placeholders; we build in order: catalog, pages, [page,content]*, font
        n_pages = len(self.pages)
        cat_id, pages_id = 1, 2
        ids = {}
        cur = 3
        page_ids, cont_ids = [], []
        for _ in range(n_pages):
            page_ids.append(cur); cont_ids.append(cur + 1); cur += 2
        font_id = cur
        out = []
        out.append((cat_id, "<< /Type /Catalog /Pages %d 0 R >>" % pages_id))
        kids = " ".join("%d 0 R" % p for p in page_ids)
        out.append((pages_id, "<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, n_pages)))
        for i in range(n_pages):
            out.append((page_ids[i],
                "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.0f %.0f] "
                "/Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> >> >>"
                % (pages_id, PAGE_W, PAGE_H, cont_ids[i], font_id)))
            body = "\n".join(self.pages[i]).encode("latin-1")
            out.append((cont_ids[i], b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"))
        out.append((font_id, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
        buf = bytearray(b"%PDF-1.4\n")
        offs = {}
        for num, body in out:
            offs[num] = len(buf)
            if isinstance(body, str): body = body.encode("latin-1")
            buf += b"%d 0 obj\n" % num + body + b"\nendobj\n"
        xref = len(buf)
        maxn = max(offs) + 1
        buf += b"xref\n0 %d\n" % maxn
        buf += b"0000000000 65535 f \n"
        for i in range(1, maxn):
            buf += b"%010d 00000 n \n" % offs.get(i, 0)
        buf += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (maxn, cat_id, xref)
        open(path, "wb").write(bytes(buf))

# ----------------------------------------------------------------------------
def draw_variant(p, key):
    v = VARIANTS[key]
    bw, bh = v["w"], v["h"]
    bx1, by1 = BOARD_X0 + bw, BOARD_Y0 + bh
    gx0, gy0 = -4.0, -4.0
    gx1, gy1 = max(PZ_W, bx1) + 4.0, by1 + 4.0
    # centre on page
    ox = (PAGE_W - (gx1 - gx0) * MM) / 2 - gx0 * MM
    oy = (PAGE_H - (gy1 - gy0) * MM) / 2 - gy0 * MM
    X = lambda mm_: ox + mm_ * MM
    Y = lambda mm_: oy + mm_ * MM

    p.newpage()
    # ---- title block
    p.rgb(0, 0, 0); p.lw(0.4)
    p.text(24, PAGE_H - 26, "GPSDO-PYNQ-Z2 front-end board  --  " + v["title"], 11)
    p.text(24, PAGE_H - 38,
           "PRINT AT 100 PERCENT / ACTUAL SIZE.  Verify the 100 mm scale bar with a ruler before using this.", 8)
    p.text(24, PAGE_H - 48,
           "PYNQ-Z2 outline and header position are ESTIMATED from a photo, +/-1 mm.  Lay this over the real board and mark corrections.", 8)

    # ---- scale bar
    sbx, sby = 24, 30
    p.lw(1.0); p.rgb(0, 0, 0)
    p.line(sbx, sby, sbx + 100 * MM, sby)
    for i in range(11):
        x = sbx + i * 10 * MM
        p.line(x, sby, x, sby + (7 if i % 5 == 0 else 4))
    p.text(sbx, sby + 10, "0", 7); p.text(sbx + 100 * MM - 8, sby + 10, "100 mm", 7)
    p.text(sbx, sby - 10, "This bar must measure exactly 100.0 mm.", 7)

    # ---- PYNQ-Z2 outline (grey, dashed)
    p.rgb(0.55, 0.55, 0.55); p.lw(0.9); p.dash(4, 3)
    p.rect(X(0), Y(0), PZ_W * MM, PZ_H * MM)
    p.dash()
    p.text(X(4), Y(PZ_H / 2), "PYNQ-Z2  (measured 137.0 x 87.0 mm)", 8)
    # tall connectors
    p.rgb(0.85, 0.35, 0.35); p.lw(0.8)
    for x0, x1, ht, nm in PZ_TALL:
        p.rect(X(x0), Y(PZ_H - 16), (x1 - x0) * MM, 16 * MM)
        p.text(X(x0) + 1, Y(PZ_H - 6), "%s %gmm" % (nm, ht), 5.5)
    # PYNQ mounting holes
    p.rgb(0.55, 0.55, 0.55)
    for hx, hy in (PZ_HOLE_TR, PZ_HOLE_TL):
        p.circle(X(hx), Y(PZ_H - hy), 1.6 * MM)
    # header pins
    p.rgb(0.1, 0.1, 0.7); p.lw(0.5)
    for n in range(1, 41):
        x, y = header_pin_xy(n)
        p.circle(X(x), Y(y), 0.5 * MM)
    p.text(X(HDR_PIN1_X) + 4, Y(HDR_ODD_Y) + 3, "pin 1", 6)
    p.text(X(header_pin_xy(39)[0]) - 16, Y(HDR_ODD_Y) + 3, "pin 39", 6)

    # ---- our board outline
    p.rgb(0, 0, 0); p.lw(1.4)
    p.rect(X(BOARD_X0), Y(BOARD_Y0), bw * MM, bh * MM)
    p.text(X(BOARD_X0) + 4, Y(by1) - 12, "GPSDO front-end board  %g x %g mm" % (bw, bh), 8)

    # ---- 2x20 socket on our board (same pin positions as the PYNQ header)
    p.rgb(0.1, 0.1, 0.7); p.lw(0.7)
    hx0 = header_pin_xy(39)[0] - 1.27; hx1 = HDR_PIN1_X + 1.27
    p.rect(X(hx0), Y(HDR_EVEN_Y - 1.27), (hx1 - hx0) * MM, 2 * HDR_PITCH * MM * 0.5 + 2.54 * MM * 0.5)
    p.text(X(hx0), Y(HDR_EVEN_Y) - 12, "2x20 socket, THT, 1.0 mm drill", 6)

    # ---- SMA jacks
    labels = jack_labels(sum(r[1] for r in v["rows"]))
    li = 0
    for ry, count, off in v["rows"]:
        span = (count - 1) * SMA_PITCH
        x0 = BOARD_X0 + (bw - span) / 2 + off
        for i in range(count):
            cx = x0 + i * SMA_PITCH; cy = BOARD_Y0 + ry
            p.rgb(0, 0, 0); p.lw(0.7)
            p.circle(X(cx), Y(cy), SMA_NUT_D / 2 * MM)          # nut, across corners
            p.rgb(0.6, 0.6, 0.6); p.lw(0.4)
            p.rect(X(cx - SMA_BODY_D/2), Y(cy - SMA_BODY_D/2), SMA_BODY_D*MM, SMA_BODY_D*MM)
            for dx in (-2.54, 2.54):
                for dy in (-2.54, 2.54):
                    p.circle(X(cx + dx), Y(cy + dy), 0.85 * MM)
            p.circle(X(cx), Y(cy), 0.75 * MM)
            p.rgb(0, 0, 0)
            s = labels[li]; li += 1
            p.text(X(cx) - 1.6 * len(s), Y(cy) - 2, s, 5.5)

    # ---- mounting holes on our board
    p.rgb(0.0, 0.5, 0.0); p.lw(0.9)
    # Bottom-left corner is occupied by the 2x20 socket, and anything there would
    # also sit over the PYNQ-Z2 rather than over the desk, so that hole moves up
    # above the socket.  Every desk standoff must be clear of the PYNQ-Z2 outline,
    # i.e. global y > PZ_H or global x > PZ_W.
    holes = [(BOARD_X0+5, BOARD_Y0+16), (bx1-5, BOARD_Y0+5),
             (BOARD_X0+5, by1-5), (bx1-5, by1-5),
             (BOARD_X0+bw/2, by1-5), (BOARD_X0+bw/2, BOARD_Y0+5)]
    for hx, hy in holes:
        assert not (hx > hx0-4 and hx < hx1+4 and hy < HDR_ODD_Y+4), \
            "mounting hole (%g,%g) collides with the 2x20 socket" % (hx, hy)
    for hx, hy in holes:
        p.circle(X(hx), Y(hy), 1.6 * MM)
        p.circle(X(hx), Y(hy), 3.25 * MM)
    # slot to the PYNQ-Z2 top-right hole
    sx, sy = PZ_HOLE_TR[0], PZ_H - PZ_HOLE_TR[1]
    p.rgb(0.0, 0.5, 0.0); p.lw(1.0)
    p.rect(X(sx-3.5), Y(sy-1.6), 7*MM, 3.2*MM)
    p.text(X(sx)+6, Y(sy)-2, "M3 slot -> PYNQ hole", 6)

    # ---- fiducials
    p.rgb(0.8, 0.5, 0.0)
    for fx, fy in [(BOARD_X0+10, by1-10), (bx1-10, by1-10), (bx1-10, BOARD_Y0+12)]:
        p.circle(X(fx), Y(fy), 0.5 * MM, fill=True)
        p.circle(X(fx), Y(fy), 1.5 * MM)

    # ---- dimension markers
    p.rgb(0, 0, 0); p.lw(0.5)
    dy = Y(by1) + 10
    p.line(X(BOARD_X0), dy, X(bx1), dy)
    p.line(X(BOARD_X0), dy-3, X(BOARD_X0), dy+3)
    p.line(X(bx1), dy-3, X(bx1), dy+3)
    p.text((X(BOARD_X0)+X(bx1))/2 - 12, dy+4, "%g mm" % bw, 7)
    dx = X(bx1) + 12
    p.line(dx, Y(BOARD_Y0), dx, Y(by1))
    p.line(dx-3, Y(BOARD_Y0), dx+3, Y(BOARD_Y0))
    p.line(dx-3, Y(by1), dx+3, Y(by1))
    p.text(dx+4, (Y(BOARD_Y0)+Y(by1))/2, "%g mm" % bh, 7)
    p.text(X(BOARD_X0), Y(BOARD_Y0)-10, "SMA pitch %g mm;  circles = nut across corners %g mm" % (SMA_PITCH, SMA_NUT_D), 7)

    # ---- legend
    lx, ly = PAGE_W - 210, 120
    p.rgb(0,0,0); p.text(lx, ly, "LEGEND", 8)
    items = [("black circle", "SMA coupling nut, 9.17 mm across corners"),
             ("grey square", "SMA jack body 6.5 mm + 5.08 mm leg pattern"),
             ("blue", "2x20 header / socket, 2.54 mm"),
             ("green", "M3 mounting hole (3.2 mm) + 6.5 mm keep-out"),
             ("orange", "fiducial, 1 mm copper / 3 mm mask"),
             ("red box", "PYNQ-Z2 tall connector -- do not overlap"),
             ("grey dashed", "PYNQ-Z2 outline (estimated)")]
    for i,(a,b) in enumerate(items):
        p.text(lx, ly-10-9*i, "%-12s  %s" % (a,b), 6.5)

def main():
    p = PDF()
    for k in ("A", "B"):
        draw_variant(p, k)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "GPSDO-PYNQ-Z2-mockup-1to1.pdf")
    p.save(out)
    print("wrote", out)

if __name__ == "__main__":
    main()
