"""Emit the board: outline, mounting, the PYNQ it plugs into, and the
mechanically-fixed connectors.

Only the parts whose position is a MECHANICAL constraint are placed here -- the
header socket, the 27 SMA jacks, the barrel jack, the probe terminals and the
bench posts.  Everything else is placed by routing judgement and arrives from
the schematic; this file fixes the frame those decisions have to live inside.
"""
import os, sys, math, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom as G

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KFP = os.path.join(os.environ["HOME"], ".local/kicad9/squashfs-root/usr/share/kicad/footprints")
LOCAL_FP = os.path.join(ROOT, "library", "GPSDO-PYNQ-Z2.pretty")

LAYERS = [(0, "F.Cu", "signal"), (1, "In1.Cu", "signal"), (2, "In2.Cu", "signal"),
          (31, "B.Cu", "signal"), (32, "B.Adhes", "user", "B.Adhesive"),
          (33, "F.Adhes", "user", "F.Adhesive"), (34, "B.Paste", "user"),
          (35, "F.Paste", "user"), (36, "B.SilkS", "user", "B.Silkscreen"),
          (37, "F.SilkS", "user", "F.Silkscreen"), (38, "B.Mask", "user"),
          (39, "F.Mask", "user"), (40, "Dwgs.User", "user", "User.Drawings"),
          (41, "Cmts.User", "user", "User.Comments"), (42, "Eco1.User", "user", "User.Eco1"),
          (43, "Eco2.User", "user", "User.Eco2"), (44, "Edge.Cuts", "user"),
          (45, "Margin", "user"), (46, "B.CrtYd", "user", "B.Courtyard"),
          (47, "F.CrtYd", "user", "F.Courtyard"), (48, "B.Fab", "user"),
          (49, "F.Fab", "user")]

_n = [0]
def uid(*parts):
    h = hashlib.sha1(("gpsdo-pcb|" + "|".join(map(str, parts))).encode()).hexdigest()
    return "%s-%s-4%s-8%s-%s" % (h[0:8], h[8:12], h[13:16], h[17:20], h[20:32])


def line(x0, y0, x1, y1, layer, w=0.15):
    return ('\t(gr_line (start %g %g) (end %g %g)\n'
            '\t\t(stroke (width %g) (type solid)) (layer "%s") (uuid "%s"))'
            % (x0, y0, x1, y1, w, layer, uid("l", x0, y0, x1, y1, layer)))


def rect(x0, y0, x1, y1, layer, w=0.15):
    return "\n".join(line(*a, layer=layer, w=w) for a in
                     ((x0, y0, x1, y0), (x1, y0, x1, y1),
                      (x1, y1, x0, y1), (x0, y1, x0, y0)))


def text(x, y, s, layer, size=1.5, thick=0.25, just="left", angle=0, mirror=False):
    # KiCAD has no "center" justify token -- centred IS the default, and
    # emitting one makes the whole board fail to load with no useful message.
    toks = ([] if just in (None, "center") else [just]) + (["mirror"] if mirror else [])
    j = ("(justify %s)" % " ".join(toks)) if toks else ""
    return ('\t(gr_text "%s" (at %g %g %g) (layer "%s") (uuid "%s")\n'
            '\t\t(effects (font (size %g %g) (thickness %g)) %s))'
            % (s, x, y, angle, layer, uid("t", x, y, s, layer), size, size, thick, j))


def circle(cx, cy, r, layer, w=0.15):
    return ('\t(gr_circle (center %g %g) (end %g %g)\n'
            '\t\t(stroke (width %g) (type solid)) (fill no) (layer "%s") (uuid "%s"))'
            % (cx, cy, cx + r, cy, w, layer, uid("c", cx, cy, r, layer)))


def load_fp(libdir, name):
    txt = open(os.path.join(libdir, name + ".kicad_mod"), encoding="utf-8").read()
    i = txt.index("\n")                      # drop the (footprint "NAME" line
    return txt[i + 1:].rstrip().rstrip(")").rstrip()


def place(libdir, name, ref, value, x, y, layer="F.Cu", rot=0):
    body = load_fp(libdir, name)
    u = uid("fp", ref, x, y)
    # keep the reference readable on silk, value on fab
    body = body.replace('(property "Reference" "REF**"', '(property "Reference" "%s"' % ref, 1)
    body = body.replace('(layer "F.SilkS")', '(layer "F.Fab")', 1)   # ref to Fab
    body = body.replace('(property "Value" "', '(property "Value" "%s" (at 0 0 0) (layer "F.Fab") (uuid "%s") (effects (font (size 1 1) (thickness 0.15)))) (property "OldValue" "' % (value, uid("v", ref)), 1)
    return ('\t(footprint "%s"\n\t\t(layer "%s")\n\t\t(uuid "%s")\n\t\t(at %g %g%s)\n%s\n\t)'
            % (name, layer, u, x, y, (" %g" % rot) if rot else "", body))


def build():
    out = []
    W, H = G.BW, G.BH

    # ---- outline ----------------------------------------------------------
    out.append(rect(0, 0, W, H, "Edge.Cuts", 0.1))

    # ---- the PYNQ underneath, as documentation ----------------------------
    p0, p1 = G.B(0, G.PZ_H), G.B(G.PZ_W, 0)
    out.append(rect(p0[0], p0[1], p1[0], p1[1], "Dwgs.User", 0.2))
    out.append(text(2, 99.0, "PYNQ-Z2 outline (measured 137.0 x 87.0) - only this 9 mm strip is over it",
                    "Dwgs.User", 1.2, 0.2))
    for x0, x1, h, nm in G.PZ_TALL:
        a, b = G.B(x0, G.PZ_H), G.B(x1, 0)
        if b[0] < 0:                            # entirely left of our left edge
            continue
        out.append(rect(max(a[0], 0), a[1], b[0], b[1], "Dwgs.User", 0.15))
    out.append(text(70.0, 91.0, "left edge clears the measured HDMI right edge (69.5) by 2.5 mm",
                    "Dwgs.User", 1.2, 0.2))

    # header pin grid, so the socket has something to land on
    for n in range(1, 41):
        x, y = G.hdr_pin(n)
        out.append(circle(x, y, 0.5, "Dwgs.User", 0.1))
    x1, y1 = G.hdr_pin(1)
    out.append(text(x1 + 3.0, y1 - 1.5, "pin 1", "Dwgs.User", 1.0, 0.15))

    # ---- mounting ---------------------------------------------------------
    for i, ((mx, my), note) in enumerate(G.MOUNT):
        out.append(place(KFP + "/MountingHole.pretty", "MountingHole_3.2mm_M3",
                         "H%d" % (i + 1), "M3", mx, my))
    out.append(text(2, 6.0, "H1 shares the PYNQ's own top-right hole.  H2-H5 carry the "
                    "cantilever: 130 mm of board with 27 coax tails will flex on the "
                    "header alone.", "Cmts.User", 1.2, 0.2))

    # ---- the socket that makes this a HAT ---------------------------------
    px, py = G.hdr_pin(1)
    out.append(place(LOCAL_FP, "RPiHeader_2x20_Socket_Underside", "J4001",
                     "2x20 socket", px, py, layer="B.Cu"))
    out.append(text(px + 3.5, py - 2.6, "PIN 1", "F.SilkS", 1.4, 0.25))
    out.append(text(62.0, 96.0, "RPi 40-PIN SOCKET, UNDERSIDE", "F.SilkS", 2.0, 0.3))

    # ---- SMA jacks --------------------------------------------------------
    rows = G.sma_rows()
    for row in rows:
        for x, y, tag, desc in row:
            out.append(place(LOCAL_FP, "SMA_Vertical_THT_Universal",
                             "J_%s" % tag, desc, x, y))
            out.append(text(x, y - 6.6, tag, "F.SilkS", 2.2, 0.35, just="center"))
    out.append(text(6.0, 30.0, "n = 10 MHz IN        Pn = 1 pps IN", "F.SilkS", 1.8, 0.3))
    out.append(text(6.0, 34.5, "13 = NULL      HIN = EXT HELPER IN      HO = CLK1 OUT",
                    "F.SilkS", 1.8, 0.3))

    # ---- what a good reading looks like, on the board itself --------------
    L = ["TEST POINTS - GOOD RANGES (ranges, not per-channel values)",
         "TP_IN    at the SMA          1.0 - 8.0 Vpp",
         "TP_SQ    at the squarer      0.6 - 3.3 Vpp, crossing mid-rail",
         "TP_BEAT  channel out         0/3.3 V square, 1.1 - 1.4 kHz",
         "TP_PPS   channel out         0/3.3 V, 1 Hz",
         "TP_XA    Si5351 drive        0.5 - 1.0 Vpp at 25 MHz",
         "TP_5V    after the fuse      4.6 - 5.3 V",
         "TP_3V3_A / TP_3V3_D          3.25 - 3.35 V"]
    for i, t in enumerate(L):
        out.append(text(6.0, 68.0 + i * 3.2, t, "F.SilkS", 1.5 if i else 1.8,
                        0.25 if i else 0.3))

    out.append(text(42.0, 44.0, "GPSDO DDMTD FRONT END   -   rev A", "F.SilkS", 3.4, 0.6))
    return out, W, H


def render():
    out, W, H = build()
    lay = "\n".join('\t\t(%d "%s" %s%s)' % (l[0], l[1], l[2],
                                            (' "%s"' % l[3]) if len(l) > 3 else "")
                    for l in LAYERS)
    body = "\n".join(o for o in out if o)
    return ('(kicad_pcb\n\t(version 20241229)\n\t(generator "gpsdo-pynq-z2")\n'
            '\t(generator_version "9.0")\n'
            '\t(general (thickness 1.6) (legacy_teardrops no))\n'
            '\t(paper "A2")\n\t(layers\n%s\n\t)\n'
            '\t(setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))\n'
            '\t(net 0 "")\n%s\n)\n' % (lay, body))


if __name__ == "__main__":
    open(os.path.join(ROOT, "GPSDO-PYNQ-Z2.kicad_pcb"), "w", encoding="utf-8").write(render())
    print("wrote GPSDO-PYNQ-Z2.kicad_pcb")
