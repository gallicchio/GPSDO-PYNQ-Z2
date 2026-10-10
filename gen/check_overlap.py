#!/usr/bin/env python3
"""Does anything on a generated sheet land on top of anything else?

2026-10-10: power symbols are bodies too (a note had sat on a GND symbol,
unseen); only a power symbol's own name may sit on its own graphic.

Reads a .kicad_sch back with no knowledge of how it was written and reports

  A  text sitting on other text
  B  text sitting on a wire
  C  text sitting on a symbol body

KiCad's stroke font is proportional.  Measured against KiCad's own bounding
boxes on this project's PCB text, the average advance is 0.82 x the glyph
height, and a line's ink height is the glyph height plus the stroke; both are
used here.  A tolerance is applied so that text merely touching a wire's
endpoint -- which is how a label is supposed to attach -- is not reported.
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, kids, kid, val, num

ADV = 0.82          # glyph advance as a fraction of height
LEAD = 1.35         # line pitch for multi-line text
TOL = 0.3           # mm of overlap to ignore


_VJ = "center"      # the last _eff()'s vertical justification, for text_box


def _eff(node):
    """(height, justify, hidden) from an (effects ...) child; the vertical
    justification is left in _VJ for the text_box() that follows."""
    global _VJ
    e = kid(node, "effects")
    h, just, hidden = 1.27, "center", False
    _VJ = "center"
    if e:
        f = kid(e, "font")
        if f and kid(f, "size"):
            h = num(kid(f, "size"), 2)
        j = kid(e, "justify")
        if j:
            toks = [val(x) if isinstance(x, tuple) else str(x) for x in j[1:]]
            for t in toks:
                if t in ("left", "right"):
                    just = t
                if t in ("top", "bottom"):
                    _VJ = t
        hd = kid(e, "hide")
        if hd and val(hd[1]) in ("yes", "true"):
            hidden = True
    # KiCad 10 writes a property's (hide yes) beside (effects), not inside it
    # (REVB item 14: the build saves every sheet in KiCad 10's format)
    hd = kid(node, "hide")
    if hd and len(hd) > 1 and val(hd[1]) in ("yes", "true"):
        hidden = True
    return h, just, hidden


def _width(line):
    """A line's advance in glyph heights, by character class (2026-10-10).
    ADV's 0.82 is prose's average; capitals and digits run 0.87-0.99 in
    KiCad's own PDF (LMK1C1108PWR 0.99, U3005 0.97, HELPER_SQ 0.94), and the
    average had let a 15 mm value 2.5 mm into its own symbol's body."""
    n = 0.0
    for c in line:
        n += (0.98 if c.isupper() or c.isdigit() else
              0.80 if c.islower() else 0.55 if c == " " else 0.70)
    return n


def text_box(s, x, y, h, just, rot):
    lines = s.split("\n")
    w = max((_width(l) for l in lines), default=0) * h
    ht = (len(lines) - 1) * h * LEAD + h
    if just == "left":
        x0 = x
    elif just == "right":
        x0 = x - w
    else:
        x0 = x - w / 2.0
    # KiCad CENTRES a text on its anchor unless it says top or bottom; this
    # used to assume the baseline for all of them, which put every field's box
    # half a glyph too high -- and a GND's name 0.13 mm into the note beside
    # it, under the tolerance, where the eye saw it on top (2026-10-10)
    y0 = y - h if _VJ == "bottom" else (y if _VJ == "top" else y - h / 2.0)
    if rot in (90, 270):
        return (x - ht / 2.0, y0, x + ht / 2.0, y0 + w)
    return (x0, y0, x0 + w, y0 + ht)


def body_of(libsym):
    """Outer extent of a library symbol's graphics, in symbol units."""
    xs, ys = [], []
    for sub in kids(libsym, "symbol"):
        for r in kids(sub, "rectangle"):
            for k in ("start", "end"):
                n = kid(r, k)
                if n:
                    xs.append(num(n, 1)); ys.append(num(n, 2))
        for pl in kids(sub, "polyline"):
            for xy in kids(kid(pl, "pts"), "xy"):
                xs.append(num(xy, 1)); ys.append(num(xy, 2))
        for c in kids(sub, "circle"):
            n = kid(c, "center"); r = kid(c, "radius")
            if n and r:
                xs += [num(n, 1) - num(r, 1), num(n, 1) + num(r, 1)]
                ys += [num(n, 2) - num(r, 1), num(n, 2) + num(r, 1)]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def collect(path):
    doc = parse(open(path, encoding="utf-8").read())[0]
    libs = {val(s): s for s in kids(kid(doc, "lib_symbols"), "symbol")}
    texts, wires, bodies = [], [], []

    for t in kids(doc, "text"):
        s = val(t[1]); at = kid(t, "at")
        h, just, hidden = _eff(t)
        if hidden or not s.strip():
            continue
        texts.append((s, text_box(s, num(at, 1), num(at, 2), h, just, num(at, 3)), None))

    for tb in kids(doc, "text_box"):
        s = val(tb[1]); at = kid(tb, "at"); sz = kid(tb, "size")
        if sz:
            x, y = num(at, 1), num(at, 2)
            bodies.append(("[note] " + s.split("\n")[0][:26],
                           (x, y, x + num(sz, 1), y + num(sz, 2))))

    for kind in ("label", "global_label", "hierarchical_label"):
        for l in kids(doc, kind):
            s = val(l[1]); at = kid(l, "at")
            h, just, hidden = _eff(l)
            if hidden:
                continue
            rot = num(at, 3)
            pad = 1.6 * h if kind != "label" else 0.0   # flag graphics
            # The written justification wins over the angle: kigen writes a
            # left-pointing label as angle 0 with (justify right), and KiCad
            # draws it to the LEFT of its anchor (2026-10-10).
            side = just if just in ("left", "right") else (
                "left" if rot in (0, 90) else "right")
            b = text_box(s + "  ", num(at, 1), num(at, 2), h, side, rot)
            texts.append((s, b, None))

    for w in kids(doc, "wire"):
        p = kids(kid(w, "pts"), "xy")
        if len(p) >= 2:
            wires.append(((num(p[0], 1), num(p[0], 2)),
                          (num(p[1], 1), num(p[1], 2))))

    for sy in kids(doc, "symbol"):
        li = kid(sy, "lib_id")
        at = kid(sy, "at")
        if not li or not li_ok(li, libs):
            continue
        b = body_of(libs[val(li[1])])
        if not b:
            continue
        x, y, rot = num(at, 1), num(at, 2), num(at, 3)
        ref = "?"
        for pr in kids(sy, "property"):
            if val(pr[1]) == "Reference":
                ref = val(pr[2])
        for pr in kids(sy, "property"):
            h, just, hidden = _eff(pr)
            pat = kid(pr, "at")
            if not hidden and pat and val(pr[2]).strip():
                # KiCad ADDS the symbol's rotation to a field's own angle when
                # it draws it, which is why kigen stores fang = -rot: the two
                # cancel and the field comes out horizontal.  Reading the
                # stored angle alone says "vertical" for every field on a
                # rot-90 part and invents an overlap for each one.
                fang = (rot + num(pat, 3)) % 360
                texts.append((val(pr[2]),
                              text_box(val(pr[2]), num(pat, 1), num(pat, 2),
                                       h, just, fang), ref))
        c = [(b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3])]
        pts = []
        for (px, py) in c:
            a = math.radians(rot)
            rx = px * math.cos(a) - py * math.sin(a)
            ry = px * math.sin(a) + py * math.cos(a)
            pts.append((x + rx, y - ry))
        bodies.append((ref, (min(p[0] for p in pts), min(p[1] for p in pts),
                             max(p[0] for p in pts), max(p[1] for p in pts))))
    return texts, wires, bodies


def li_ok(li, libs):
    return len(li) > 1 and val(li[1]) in libs


def ov(a, b):
    x = min(a[2], b[2]) - max(a[0], b[0])
    y = min(a[3], b[3]) - max(a[1], b[1])
    return (x, y) if x > TOL and y > TOL else None


def seg_box(p, q, pad=0.2):
    return (min(p[0], q[0]) - pad, min(p[1], q[1]) - pad,
            max(p[0], q[0]) + pad, max(p[1], q[1]) + pad)


# Overlaps that were checked by eye in round 21 and are artefacts of the
# measurement, not of the drawing.  Each is a GND label belonging to a
# NEIGHBOURING power symbol that falls inside the BOUNDING BOX of a single-gate
# symbol -- and a gate's graphic is a triangle, so most of its bounding box is
# empty.  Rendered, the label sits in the clear corner above the slope.
#
# They stay in the report, but they do not fail the build, so that a NEW
# overlap still does.  Fixing them properly means testing against the polygon
# instead of the box, which is worth doing the day something else needs it.
KNOWN_OK = {("GND", "U3002"), ("GND", "U3003"), ("GND", "U3004"),
            ("GND", "U3005"), ("GND", "U3006"), ("GND", "U3007")}


def main(paths):
    total = 0
    known = 0
    for path in paths:
        texts, wires, bodies = collect(path)
        rows = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                o = ov(texts[i][1], texts[j][1])
                if o:
                    rows.append(("text/text", o[0] * o[1], texts[i][0], texts[j][0],
                                 texts[i][1]))
        for s, b, own in texts:
            for p, q in wires:
                if abs(p[0] - q[0]) > 1e-6 and abs(p[1] - q[1]) > 1e-6:
                    continue                      # diagonal: skip
                o = ov(b, seg_box(p, q))
                if o and o[0] > 0.6 and o[1] > 0.6:
                    rows.append(("text/wire", o[0] * o[1], s, "wire %s-%s" % (p, q), b))
            for ref, bb in bodies:
                if ref == own and own.startswith(("#PWR", "#FLG")):
                    continue        # a power symbol's name sits under its graphic
                o = ov(b, bb)
                if o and o[0] > 0.6 and o[1] > 0.6:
                    rows.append(("text/body", o[0] * o[1], s, ref, b))
        rows.sort(key=lambda r: -r[1])
        keep = []
        for r in rows:
            a, b = r[2].split("\n")[0], str(r[3])
            if (a, b) in KNOWN_OK or (b, a) in KNOWN_OK:
                known += 1
            else:
                keep.append(r)
        rows = keep
        if rows:
            print("=== %s : %d" % (os.path.basename(path), len(rows)))
            for kind, a, s1, s2, b in rows[:12]:
                print("   %-9s %6.1f mm^2  %-34r  vs  %-30r  @(%.1f,%.1f)"
                      % (kind, a, s1.split("\n")[0][:32], str(s2)[:28], b[0], b[1]))
            total += len(rows)
    if known:
        print("(%d known, verified false positives suppressed -- see KNOWN_OK)"
              % known)
    print("TOTAL UNEXPECTED OVERLAPS: %d" % total)
    return total


if __name__ == "__main__":
    import glob
    args = sys.argv[1:] or sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "*.kicad_sch")))
    sys.exit(1 if main(args) else 0)
