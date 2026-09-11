"""Render a region of the board to PNG, so the layout can be LOOKED at.

Not a substitute for KiCad; a way to check a tile or a block without opening
the GUI.  Usage:  python3 pcb/plot.py out.png x0 y0 x1 y1 [--refs]
"""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from sexp import parse, kids, kid, val, head, num

COL = {"F.Cu": "#c83232", "In1.Cu": "#2f6f2f", "In2.Cu": "#c8a000",
       "B.Cu": "#3232c8", "F.SilkS": "#d8d8d8", "Edge.Cuts": "#f0f000",
       "F.CrtYd": "#606060"}


def rot(x, y, a):
    r = math.radians(-a)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


def render(path, png, x0, y0, x1, y1, show_refs=True):
    doc = parse(open(path, encoding="utf-8").read())[0]
    scale = min(1400.0 / (x1 - x0), 1400.0 / (y1 - y0))    # px per mm
    fig = plt.figure(figsize=((x1 - x0) * scale / 100.0,
                              (y1 - y0) * scale / 100.0), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#101010")

    def seg(ax_, a, b, c, w, scale=scale):
        ax_.plot([a[0], b[0]], [a[1], b[1]], color=c, lw=max(0.5, w * scale / 25.4 * 2.834),
                 solid_capstyle="round", zorder=2)

    for node in doc:
        if not isinstance(node, list):
            continue
        h = head(node)
        if h == "segment":
            s, e = kid(node, "start"), kid(node, "end")
            lyr = val(kid(node, "layer"))
            seg(ax, (num(s, 1), num(s, 2)), (num(e, 1), num(e, 2)),
                COL.get(lyr, "#888"), num(kid(node, "width"), 1))
        elif h == "via":
            a = kid(node, "at")
            ax.add_patch(Circle((num(a, 1), num(a, 2)), 0.3, color="#e0e0e0",
                                zorder=3))
        elif h in ("gr_line",):
            s, e = kid(node, "start"), kid(node, "end")
            lyr = val(kid(node, "layer"))
            if lyr in ("F.SilkS", "Edge.Cuts"):
                seg(ax, (num(s, 1), num(s, 2)), (num(e, 1), num(e, 2)),
                    COL[lyr], 0.04)
        elif h == "footprint":
            a = kid(node, "at")
            fx, fy = num(a, 1), num(a, 2)
            fa = num(a, 3) if len(a) > 3 else 0.0
            if not (x0 - 12 < fx < x1 + 12 and y0 - 12 < fy < y1 + 12):
                continue
            ref = ""
            for pr in kids(node, "property"):
                if val(pr) == "Reference":
                    ref = val(pr, 2)
            for ln in kids(node, "fp_line"):
                if val(kid(ln, "layer")) != "F.CrtYd":
                    continue
                s, e = kid(ln, "start"), kid(ln, "end")
                p = rot(num(s, 1), num(s, 2), fa)
                q = rot(num(e, 1), num(e, 2), fa)
                seg(ax, (fx + p[0], fy + p[1]), (fx + q[0], fy + q[1]),
                    "#505050", 0.03)
            for p in kids(node, "pad"):
                pa = kid(p, "at")
                px, py = rot(num(pa, 1), num(pa, 2), fa)
                pr_ = num(pa, 3) if len(pa) > 3 else 0.0
                sz = kid(p, "size")
                w, hh = num(sz, 1), num(sz, 2)
                if abs(pr_ % 180 - 90) < 1:
                    w, hh = hh, w
                tht = val(p, 2) == "thru_hole"
                ax.add_patch(Rectangle((fx + px - w / 2, fy + py - hh / 2), w, hh,
                                       color="#e08a2a" if tht else "#d85050",
                                       zorder=4, alpha=0.9))
            if show_refs and ref:
                ax.text(fx, fy, ref, color="#ffffff", fontsize=max(2.0, min(7.0, scale * 0.22)), ha="center",
                        va="center", zorder=6)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_xticks([]); ax.set_yticks([])
    fig.savefig(png, facecolor="#101010")
    print("wrote", png)


if __name__ == "__main__":
    a = sys.argv[1:]
    refs = "--refs" in a
    a = [z for z in a if z != "--refs"]
    render(os.path.join(os.path.dirname(HERE), "GPSDO-PYNQ-Z2.kicad_pcb"),
           a[0], *[float(z) for z in a[1:5]], show_refs=refs)
