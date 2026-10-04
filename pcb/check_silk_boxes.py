#!/usr/bin/env python3
"""Everything that belongs to a silkscreen box must be inside that box.

    python3 pcb/check_silk_boxes.py [board.kicad_pcb]

Each channel unit prints two boxes: its 10 MHz box and, for units 1-12, its
1 pps box -- fixed rectangles about the unit's own SMAs (pcb/tile.py).  A part
belongs to a box by its slot in the tile (PARTS_10M or PARTS_PPS), and so does
its reference designator: a designator that lands in the NEXT unit's box names
a part the reader will look for in the wrong place.  Round 41: on rev A,
FB401's designator printed in unit 6's box, R203/C203/C207's in unit 4's, and
FB204/C209/R208's outside the P2 box altogether -- and the same, mirrored, on
the odd side.  The unit tiles are rotated 90 (left column) or 270 (right), so a
label pushed out of a tile's power gutter lands in the neighbouring unit.

Checked, per part in a unit tile:
  * its pads lie inside its own box;
  * its reference designator, if printed (F.SilkS), lies inside its own box.
Other silkscreen that belongs to a box -- test-point letters, the 50R jumper
note -- is placed by build_pcb.py, which knows whose it is, and checks it there
with the same function (`contained`).

Exit status 1 if anything is out of its box.
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
import geom as G          # noqa: E402
import tile as T          # noqa: E402

REF_SIZE, REF_THICK = 0.8, 0.16


def text_box(cx, cy, s, size=REF_SIZE, thick=REF_THICK):
    """The ink of a centre-justified, horizontal string (build_pcb.adv())."""
    adv = size * (1.0 if len(s) <= 5 else 0.9)
    w = len(s) * adv + thick
    h = size + thick
    return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def contained(inner, outer, margin=0.0):
    return (inner[0] >= outer[0] + margin and inner[1] >= outer[1] + margin
            and inner[2] <= outer[2] - margin and inner[3] <= outer[3] - margin)


def unit_of(ref):
    """(unit, slot) for a reference in a channel tile, e.g. FB401 -> (4, FB01)."""
    m = re.match(r"^([A-Za-z]+)(\d+)$", ref)
    if not m:
        return None, None
    pre, n = m.group(1), m.group(2)
    for u in range(13, 0, -1):
        s = str(u)
        if n.startswith(s) and len(n) == len(s) + 2:
            return u, pre + n[len(s):]
    return None, None


def unit_boxes(u):
    """{'10m': (x0, y0, x1, y1), 'pps': ...} in board coordinates."""
    ox, oy, urot = G.unit_origin(u)
    a = math.radians(-urot)
    ca, sa = int(round(math.cos(a))), int(round(math.sin(a)))

    def f(lx, ly):
        return (ox + lx * ca - ly * sa, oy + lx * sa + ly * ca)

    out = {}
    for kind, b in (("10m", T.BOX_10M), ("pps", T.pps_box())):
        cs = [f(b[0], b[1]), f(b[2], b[1]), f(b[2], b[3]), f(b[0], b[3])]
        out[kind] = (min(c[0] for c in cs), min(c[1] for c in cs),
                     max(c[0] for c in cs), max(c[1] for c in cs))
    return out


def box_kind(slot):
    if slot in T.PARTS_10M:
        return "10m"
    if slot in T.PARTS_PPS:
        return "pps"
    return None


def _blocks(txt, tag):
    i = 0
    key = "\n\t(%s " % tag
    while True:
        i = txt.find(key, i)
        if i < 0:
            return
        d, j = 0, i + 1
        while True:
            c = txt[j]
            if c == "(":
                d += 1
            elif c == ")":
                d -= 1
                if d == 0:
                    break
            j += 1
        yield txt[i + 1:j + 1]
        i = j


def to_board(fx, fy, frot, lx, ly):
    r = math.radians(frot)
    return (fx + lx * math.cos(r) + ly * math.sin(r),
            fy - lx * math.sin(r) + ly * math.cos(r))


def _children(block, tag):
    """The balanced (tag ...) sub-blocks of `block`, in order.  Works on both
    pcbnew's one-item-per-line layout and build_pcb.py's compact one."""
    out, i = [], 0
    key = "(%s " % tag
    while True:
        i = block.find(key, i)
        if i < 0:
            return out
        d, j = 0, i
        while True:
            c = block[j]
            if c == "(":
                d += 1
            elif c == ")":
                d -= 1
                if d == 0:
                    break
            j += 1
        out.append(block[i:j + 1])
        i = j + 1


def footprints(path):
    """[(ref, (x, y, rot), ref_xy or None if not on F.SilkS, pad boxes)]"""
    txt = open(path, encoding="utf-8").read()
    out = []
    for b in _blocks(txt, "footprint"):
        props = [p for p in _children(b, "property") if p.startswith('(property "Reference"')]
        if not props:
            continue
        prop = props[0]
        ref = re.match(r'\(property "Reference" "([^"]+)"', prop).group(1)
        # the footprint's own (at) is the first one in its block: it precedes
        # every property and pad in both layouts
        at = re.search(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', b)
        fx, fy, fr = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        pa = re.search(r'\(at ([-\d.]+) ([-\d.]+)', prop)
        lay = re.search(r'\(layer "([^"]+)"\)', prop).group(1)
        hidden = re.search(r'\(hide yes\)', prop)
        ref_xy = (to_board(fx, fy, fr, float(pa.group(1)), float(pa.group(2)))
                  if lay == "F.SilkS" and not hidden else None)
        pads = []
        for pb in _children(b, "pad"):
            pm = re.search(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', pb)
            sm = re.search(r'\(size ([\d.]+) ([\d.]+)\)', pb)
            if not (pm and sm):
                continue
            px, py = to_board(fx, fy, fr, float(pm.group(1)), float(pm.group(2)))
            w, h = float(sm.group(1)), float(sm.group(2))
            if round(float(pm.group(3) or 0)) % 180:
                w, h = h, w
            pads.append((px - w / 2, py - h / 2, px + w / 2, py + h / 2))
        out.append((ref, (fx, fy, fr), ref_xy, pads))
    return out


def check(path, verbose=True):
    """[(ref, what, detail)] for everything outside its own box."""
    boxes = {}
    bad = []
    for ref, (fx, fy, fr), ref_xy, pads in footprints(path):
        u, slot = unit_of(ref)
        if not u:
            continue
        kind = box_kind(slot)
        if kind is None or (kind == "pps" and u == 13):
            continue
        if u not in boxes:
            boxes[u] = unit_boxes(u)
        home = boxes[u][kind]
        name = "%s box %d" % ("10 MHz" if kind == "10m" else "pps", u)
        for pb in pads:
            if not contained(pb, home):
                bad.append((ref, "part", "a pad of %s is outside the %s" % (ref, name)))
                break
        if ref_xy is not None:
            tb = text_box(ref_xy[0], ref_xy[1], ref)
            if not contained(tb, home):
                where = "outside every box"
                for v in range(1, 14):
                    bv = boxes.setdefault(v, unit_boxes(v))
                    for k2, b2 in bv.items():
                        if (k2 == "pps" and v == 13) or (v == u and k2 == kind):
                            continue
                        if not (tb[2] < b2[0] or b2[2] < tb[0] or tb[3] < b2[1] or b2[3] < tb[1]):
                            where = "in the %s box of unit %d" % (
                                "10 MHz" if k2 == "10m" else "pps", v)
                bad.append((ref, "label", "designator %s is not inside the %s: %s"
                            % (ref, name, where)))
    if verbose:
        for ref, what, detail in sorted(bad, key=lambda b: (unit_of(b[0])[0], b[0])):
            print("   %s" % detail)
        print("%s: %d item(s) outside their own box" % (os.path.basename(path), len(bad)))
    return bad


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(HERE), "GPSDO-PYNQ-Z2.kicad_pcb")
    sys.exit(1 if check(p) else 0)
