#!/usr/bin/env python3
"""No unit's silkscreen in another unit's box, read off the WRITTEN board.

    <kicad python> pcb/check_unit_labels.py [board.kicad_pcb]
    python3 pcb/check_unit_labels.py --stamps DIR      # pictures, from the last check

Round 41 found designators printed in the next unit's box, and the fix was to
give every tile part a home box (build_pcb.py home_of) and check what the
placer registered (check_owned, check_silk_boxes.py).  That only covers what
has a home.  Rev B's in-tile heaters belong to the power sheet, had none, and
on eight units their designators went into the next unit's box (2026-10-10).
So this reads EVERY text on F.SilkS with KiCad's own bounding box, finds its
owner -- a designator's own footprint; a free text by build_pcb.py's record of
who placed it (build/silk_owned.json); a unit's numeral `k` or `Pk` by its
words -- and fails when:

  * a unit's text reaches into another unit's box, or out of its own;
  * a text with no unit reaches into any unit's box.

KiCad's text box includes the font cell above the capitals, so a text has to
reach TOL into a box before it counts as being in it.

--stamps DIR draws one picture per unit from build/unit_labels.json (which
the check writes; KiCad's Python has no matplotlib, so this half runs under
the system's): the unit's boxes, and every text near them as a rectangle
coloured by owner -- green this unit, red another unit, blue no unit.  A red
or blue rectangle inside the black boxes is the thing to look for.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOL = 0.4                       # mm a text must reach into a box to be "in" it


def overlap(a, b):
    """How far rectangle a reaches into rectangle b (0 when it does not)."""
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return min(dx, dy) if dx > 0 and dy > 0 else 0.0


def outside_by(a, b):
    """How far rectangle a sticks out of rectangle b."""
    return max(b[0] - a[0], b[1] - a[1], a[2] - b[2], a[3] - b[3], 0.0)


OUT = os.path.join(ROOT, "build", "unit_labels.json")


def main():
    if "--stamps" in sys.argv:
        R = json.load(open(OUT))
        stamps(sys.argv[sys.argv.index("--stamps") + 1],
               [tuple(t) for t in R["texts"]],
               {tuple(k.split("|")): v for k, v in R["ubox"].items()})
        return 0
    import pcbnew
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pcbf = args[0] if args else os.path.join(ROOT, "GPSDO-PYNQ-Z2.kicad_pcb")
    D = json.load(open(os.path.join(ROOT, "build", "silk_owned.json")))
    ubox = {tuple(k.split("|")): v for k, v in D["ubox"].items()}
    mm = pcbnew.ToMM

    def unit_of_box(bx):
        for (u, _kind), v in ubox.items():
            if all(abs(p - q) < 1e-6 for p, q in zip(v, bx)):
                return u
        return None

    def owner_unit(ref):
        h = D["home"].get(ref)
        return unit_of_box(h) if h else None

    b = pcbnew.LoadBoard(pcbf)
    texts = []                  # (owner ref or None, string, box, unit or None)
    for f in b.GetFootprints():
        t = f.Reference()
        if t.GetLayer() == pcbnew.F_SilkS and t.IsVisible():
            bb = t.GetBoundingBox()
            box = (mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom()))
            texts.append((f.GetReference(), f.GetReference(), box,
                          owner_unit(f.GetReference())))
    for d in b.GetDrawings():
        if not (isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS):
            continue
        bb = d.GetBoundingBox()
        box = (mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom()))
        s = d.GetText()
        # A unit's numeral, or its pps box's "Pk", standing at its own box.
        # "1", "5", "P10" and "P11" are also pin names at the RPi socket and a
        # test point's letter, so the words alone do not make it a unit label.
        m = re.fullmatch(r"P?(\d+)", s)
        k = (m.group(1), "pps" if s.startswith("P") else "10m") if m else None
        if k in ubox and outside_by(box, ubox[k]) < 5.0:    # a heading stands on its edge
            texts.append((None, s, box, m.group(1)))
            continue
        cand = [(overlap(box, o[2]), o[0]) for o in D["owned"] if o[1] == s]
        cand = [c for c in cand if c[0] > 0]
        own = max(cand)[1] if cand else None
        texts.append((own, s, box, owner_unit(own) if own else None))

    bad = []
    for own, s, box, u in texts:
        into = [(uu, kind) for (uu, kind), v in ubox.items() if overlap(box, v) > TOL]
        if u:
            mine = [v for (uu, kind), v in ubox.items() if uu == u]
            if [k for k in into if k[0] != u]:
                bad.append("%r (%s, unit %s) reaches into unit %s's box"
                           % (s, own or "unit label", u,
                              ", ".join(sorted({k[0] for k in into if k[0] != u}))))
            elif own and min(outside_by(box, v) for v in mine) > TOL:
                bad.append("%r (%s, unit %s) is outside its own unit's boxes"
                           % (s, own or "unit label", u))
        elif into:
            bad.append("%r (%s, no unit) reaches into unit %s's box"
                       % (s, own or "free text", ", ".join(sorted({k[0] for k in into}))))
    print("unit labels: %d silkscreen texts read, %d in the wrong unit's box"
          % (len(texts), len(bad)))
    for x in bad:
        print("UNIT LABEL: " + x)
    json.dump({"texts": texts, "bad": bad,
               "ubox": {"%s|%s" % k: v for k, v in ubox.items()}}, open(OUT, "w"))
    return 1 if bad else 0


def stamps(outdir, texts, ubox):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    os.makedirs(outdir, exist_ok=True)
    units = sorted({u for u, _k in ubox}, key=int)
    for u in units:
        mine = [v for (uu, _k), v in ubox.items() if uu == u]
        x0 = min(v[0] for v in mine) - 4
        y0 = min(v[1] for v in mine) - 4
        x1 = max(v[2] for v in mine) + 4
        y1 = max(v[3] for v in mine) + 4
        fig, ax = plt.subplots(figsize=((x1 - x0) / 7.0, (y1 - y0) / 7.0))
        for (uu, _k), v in ubox.items():
            ax.add_patch(Rectangle((v[0], v[1]), v[2] - v[0], v[3] - v[1], fill=False,
                                   lw=2.0 if uu == u else 0.8,
                                   ec="black" if uu == u else "grey"))
        for own, s, box, tu in texts:
            if box[2] < x0 or box[0] > x1 or box[3] < y0 or box[1] > y1:
                continue
            col = ("tab:green" if tu == u else "tab:red" if tu else "tab:blue")
            ax.add_patch(Rectangle((box[0], box[1]), box[2] - box[0], box[3] - box[1],
                                   fill=True, alpha=0.25, fc=col, ec=col, lw=0.6))
            ax.text((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, s, fontsize=5.5,
                    ha="center", va="center", color="black")
        ax.set_xlim(x0, x1)
        ax.set_ylim(y1, y0)
        ax.set_aspect("equal")
        ax.set_title("unit %s: green = its own labels, red = another unit's, "
                     "blue = no unit's (board mm)" % u, fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "unit_%02d.png" % int(u)), dpi=110)
        plt.close(fig)
    print("stamps in", outdir)


if __name__ == "__main__":
    sys.exit(main())
