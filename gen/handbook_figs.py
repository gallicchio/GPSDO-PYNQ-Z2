#!/usr/bin/env python3
"""Pictures for the handbook's bring-up: where each named thing IS on the board.

    <kicad python> gen/handbook_figs.py --check [board.kicad_pcb]   # 1: read the board
    python3 gen/handbook_figs.py --draw                             # 2: render and draw

Jason, 2026-10-10: "as you refer to places on the PCB in the bringup plans,
include a thumbnail around the 3D render so that I can easily find the
reference on a crowded board, which sits on a crowded desk.  Double check that
the reference is actually next to the component or probe point you want me to
probe."

So every spot the handbook's sections 7 and 8 send you to is listed in FIGS
below, by designator (and pad, where it is one pin of a part), with the words
the silkscreen prints to name it.

--check runs under KiCad's own Python, reads the WRITTEN board, and for each
spot finds the silkscreen text with those words nearest the part, using
KiCad's own text box.  It fails when that text is further than its kind
allows from the part, or when another part of the same kind -- another test
point, another U.FL, another jack, another pin of the header -- is nearer the
text than the part it names.  That is the check Jason asked for: the `S`
beside the S pad and not the In pad, `50R` at pin 1 and not pin 2.  It writes
build/handbook_figs.json.

--draw runs under the system's Python (PIL): it renders the board's 3D top
view with kicad-cli, and draws one picture per entry of FIGS into
docs/handbook/: the whole board, small, with a red box where to look; beside
it the zoomed view, each named part circled in red and the words naming it
boxed in yellow.  The board is drawn as it sits behind the PYNQ-Z2: the 2x20
socket's edge nearest you.
"""
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAME = "GPSDO-PYNQ-Z2"
OUT_JSON = os.path.join(ROOT, "build", "handbook_figs.json")
FIG_DIR = os.path.join(ROOT, "docs", "handbook")

# (figure, title, [(designator, pad or None, the words printed for it, kind)])
# A kind sets who the words are compared against, and how far they may be.
FIGS = [
    ("socket_pins", "The 2x20 socket from the top: pins 1 and 17 (nc), 2 (5V), 6 (GND)",
     [("J4001", "1", "nc", "socketpin"), ("J4001", "17", "nc", "socketpin"),
      ("J4001", "2", "5V", "socketpin"), ("J4001", "6", "GND", "socketpin")]),
    ("jp_left", "Unit 1's header: 50R at pin 1, toward the SMA (every left-hand unit)",
     [("JP101", "1", "50R", "jppin"), ("JP101", "3", "PARK", "jppin")]),
    ("jp_right", "Unit 2's header: turned 180 degrees, 50R still toward the SMA "
                 "(every right-hand unit)",
     [("JP201", "1", "50R", "jppin"), ("JP201", "3", "PARK", "jppin")]),
    ("posts", "The bench 5 V posts, top edge: GND and +5V",
     [("J2002", None, "GND", "post"), ("J2001", None, "+5V", "post")]),
    ("rails", "Test points 5, A and D, in the POWER block",
     [("TP2001", None, "5", "tp"), ("TP2002", None, "A", "tp"), ("TP2003", None, "D", "tp")]),
    ("rail_taps", "The rail U.FLs, bottom edge: +5V, +3V3_A (far end), +3V3_D",
     [("J2004", None, "+5V", "ufl"), ("J2005", None, "+3V3_A", "ufl"),
      ("J2006", None, "+3V3_D", "ufl")]),
    ("unit1", "Unit 1: jack 1, test points In, S, B, and the IN and SQ U.FLs "
              "(every left-hand unit)",
     [("J101", None, "1", "sma"), ("TP101", None, "In", "tp"), ("TP102", None, "S", "tp"),
      ("TP103", None, "B", "tp"), ("J103", None, "IN", "ufl"), ("J104", None, "SQ", "ufl")]),
    ("unit2", "Unit 2: the same, turned 180 degrees (every right-hand unit)",
     [("J201", None, "2", "sma"), ("TP201", None, "In", "tp"), ("TP202", None, "S", "tp"),
      ("TP203", None, "B", "tp"), ("J203", None, "IN", "ufl"), ("J204", None, "SQ", "ufl")]),
    ("ref", "Test point X and the REF U.FL, between the TCXO and the Si5351C",
     [("TP3001", None, "X", "tp"), ("J3004", None, "REF", "ufl")]),
    ("clk0", "The CLK0 U.FL, just below the Si5351C",
     [("J3005", None, "CLK0", "ufl")]),
    ("hclk", "The HCLK U.FL, beside the lower LMK1C1108",
     [("J3003", None, "HCLK", "ufl")]),
    ("ho", "HO, the null source's SMA, top centre",
     [("J3001", None, "HO", "sma")]),
    ("null", "Unit 13, the null channel: its header, jack 13, S and SQ",
     [("JP1301", "1", "50R", "jppin"), ("J1301", None, "13", "sma"),
      ("TP1302", None, "S", "tp"), ("J1304", None, "SQ", "ufl")]),
    ("pps", "Unit 1's 1 pps: jack P1 and test point P",
     [("J102", None, "P1", "sma"), ("TP104", None, "P", "tp")]),
    ("jack15", "The 15 V heater jack, top right",
     [("J2003", None, "15 V DC, 1 A MIN", "barrel")]),
    ("u5007", "U5007, the thermostat's sensor (0x4E), marked T, beside the fan-out",
     [("U5007", None, "T", "tmp")]),
]

# How far a label may sit from the part it names (mm, box to box), by kind.
GAP = {"tp": 2.5, "ufl": 2.5, "jppin": 2.0, "socketpin": 2.5, "post": 3.0,
       "sma": 4.0, "barrel": 8.0, "tmp": 3.0}


def _kind_members(board, kind, pcbnew):
    """Every (ref, pad) the words could be mistaken for, with its box."""
    mm = pcbnew.ToMM
    out = []
    for f in board.GetFootprints():
        r = f.GetReference()
        fp = f.GetFPIDAsString()
        if kind == "tp" and r.startswith("TP"):
            pass
        elif kind == "ufl" and "U.FL" in fp:
            pass
        elif kind in ("sma", "post", "barrel") and (
                "SMA" in fp or "PinHeader_1x01" in fp or "BarrelJack" in fp):
            pass
        elif kind == "tmp" and f.GetValue().startswith("TMP1075"):
            pass
        elif kind == "jppin" and r.startswith("JP"):
            for p in f.Pads():
                out.append(((r, p.GetNumber()), _box(p.GetBoundingBox(), mm)))
            continue
        elif kind == "socketpin" and r == "J4001":
            for p in f.Pads():
                out.append(((r, p.GetNumber()), _box(p.GetBoundingBox(), mm)))
            continue
        else:
            continue
        out.append(((r, None), _pads_box(f, mm)))
    return out


def _box(bb, mm):
    return (mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom()))


def _pads_box(f, mm):
    bs = [_box(p.GetBoundingBox(), mm) for p in f.Pads()]
    return (min(b[0] for b in bs), min(b[1] for b in bs),
            max(b[2] for b in bs), max(b[3] for b in bs))


def pdist(c, b):
    """Distance from a point to a rectangle."""
    dx = max(b[0] - c[0], c[0] - b[2], 0.0)
    dy = max(b[1] - c[1], c[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def gap(a, b):
    """Distance between two rectangles, 0 when they touch or overlap."""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def check(pcbf):
    import pcbnew
    mm = pcbnew.ToMM
    b = pcbnew.LoadBoard(pcbf)
    texts = []
    for d in b.GetDrawings():
        if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS:
            texts.append((d.GetText(), _box(d.GetBoundingBox(), mm)))
    for f in b.GetFootprints():
        t = f.Reference()
        if t.GetLayer() == pcbnew.F_SilkS and t.IsVisible():
            texts.append((f.GetReference(), _box(t.GetBoundingBox(), mm)))
    eb = b.GetBoardEdgesBoundingBox()
    res = {"edge": _box(eb, mm), "figs": [], "bad": []}
    for name, title, items in FIGS:
        fig = {"name": name, "title": title, "items": []}
        for ref, pad, words, kind in items:
            f = b.FindFootprintByReference(ref)
            if f is None:
                res["bad"].append("%s: no %s on the board" % (name, ref))
                continue
            if pad:
                ps = [p for p in f.Pads() if p.GetNumber() == pad]
                tb = _box(ps[0].GetBoundingBox(), mm)
            else:
                tb = _pads_box(f, mm)
            cands = [(gap(tb, bx), bx) for s, bx in texts if s == words]
            if not cands:
                res["bad"].append("%s: nothing on the silkscreen says %r" % (name, words))
                continue
            g, lb = min(cands)
            # who else of this kind is nearer those words?  From the words'
            # CENTRE: "PARK" is 3.4 mm long over pin 3, and its box reaches
            # pin 2's pad as closely as pin 3's
            c = ((lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2)
            own = pdist(c, tb)
            members = _kind_members(b, kind, pcbnew)
            rivals = sorted((pdist(c, mb), key) for key, mb in members
                            if key != (ref, pad if pad else None))
            nearer = [k for d, k in rivals if d < own - 0.05]
            ok = g <= GAP[kind] and not nearer
            line = ("%-11s %-7s%-4s %-18r %4.2f mm from it%s"
                    % (name, ref, (":" + pad) if pad else "", words, g,
                       "" if not nearer else "; NEARER: %s" % ", ".join(
                           "%s%s" % (k[0], ":" + k[1] if k[1] else "") for k in nearer[:3])))
            print(("ok    " if ok else "WRONG ") + line)
            if not ok:
                res["bad"].append(line)
            fig["items"].append({"ref": ref, "pad": pad, "words": words, "kind": kind,
                                 "target": tb, "label": lb, "gap": g})
        res["figs"].append(fig)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(res, open(OUT_JSON, "w"), indent=1)
    print("handbook figures: %d spots checked, %d not beside their words"
          % (sum(len(f["items"]) for f in res["figs"]), len(res["bad"])))
    return 1 if res["bad"] else 0


# ---------------------------------------------------------------------------
# drawing (system Python)
# ---------------------------------------------------------------------------
RENDER_W = 6144                 # px; the board comes out ~25 px/mm


def render(pcbf, png):
    """The 3D top view, once per build (a minute at "high" quality)."""
    sys.path.insert(0, HERE)
    import kicad_env
    subprocess.run(kicad_env.kicad_cli() + [
        "pcb", "render", "-o", png, "-w", str(RENDER_W),
        "-h", str(int(RENDER_W * 0.8633)), "--side", "top",
        "--background", "transparent", "--quality", "high", pcbf],
        check=True, capture_output=True, cwd=ROOT)


def draw():
    from PIL import Image, ImageDraw, ImageFont
    R = json.load(open(OUT_JSON))
    os.makedirs(FIG_DIR, exist_ok=True)
    png = os.path.join(ROOT, "build", "render_top.png")
    if "--no-render" not in sys.argv:
        render(os.path.join(ROOT, NAME + ".kicad_pcb"), png)
    im = Image.open(png).convert("RGBA")
    # The board fills the render's OPAQUE area exactly (no part overhangs an
    # edge), so the edge box maps straight onto it.  "high" quality leaves a
    # half-transparent fringe of anti-aliasing and shadow outside the edge:
    # only alpha over 128 is board.
    x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 128 else 0).getbbox()
    ex0, ey0, ex1, ey1 = R["edge"]
    sx, sy = (x1 - x0) / (ex1 - ex0), (y1 - y0) / (ey1 - ey0)
    if abs(sx / sy - 1.0) > 0.01:
        raise SystemExit("render is not the board's shape: %.3f vs %.3f px/mm" % (sx, sy))
    board = Image.new("RGBA", im.size, (24, 24, 24, 255))
    board.alpha_composite(im)
    board = board.crop((x0, y0, x1, y1)).convert("RGB")

    def px(x, y):
        return ((x - ex0) * sx, (y - ey0) * sy)

    font = ImageFont.truetype("DejaVuSans.ttf", 17)
    small = ImageFont.truetype("DejaVuSans.ttf", 13)
    LW, ZW, ZH, TH = 300, 600, 450, 34
    lh = int(LW * board.height / board.width)
    loc_base = board.resize((LW, lh), Image.LANCZOS)
    for fig in R["figs"]:
        its = fig["items"]
        boxes = [i["target"] for i in its] + [i["label"] for i in its]
        bx0 = min(b[0] for b in boxes) - 3.0
        by0 = min(b[1] for b in boxes) - 3.0
        bx1 = max(b[2] for b in boxes) + 3.0
        by1 = max(b[3] for b in boxes) + 3.0
        # at least 24 x 18 mm, and the zoom panel's 4:3
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        w = max(bx1 - bx0, 24.0, (by1 - by0) * ZW / ZH)
        h = w * ZH / ZW
        bx0, bx1 = cx - w / 2, cx + w / 2
        by0, by1 = cy - h / 2, cy + h / 2
        # keep the window on the board
        dx = max(ex0 - bx0, 0) - max(bx1 - ex1, 0)
        dy = max(ey0 - by0, 0) - max(by1 - ey1, 0)
        bx0, bx1, by0, by1 = bx0 + dx, bx1 + dx, by0 + dy, by1 + dy
        (p0x, p0y), (p1x, p1y) = px(bx0, by0), px(bx1, by1)
        zoom = board.crop((int(p0x), int(p0y), int(p1x), int(p1y))).resize((ZW, ZH), Image.LANCZOS)
        k = ZW / (p1x - p0x)
        dz = ImageDraw.Draw(zoom)

        def zp(x, y):
            X, Y = px(x, y)
            return ((X - p0x) * k, (Y - p0y) * k)

        for i in its:
            t, lb = i["target"], i["label"]
            a, c = zp(t[0], t[1]), zp(t[2], t[3])
            mx, my = (a[0] + c[0]) / 2, (a[1] + c[1]) / 2
            r = max(math.hypot(c[0] - a[0], c[1] - a[1]) / 2 + 5, 13)
            la, lc = zp(lb[0] - 0.45, lb[1] - 0.3), zp(lb[2] + 0.45, lb[3] + 0.3)
            # leader from the words to the circle, then the marks over it
            lx, ly = (la[0] + lc[0]) / 2, (la[1] + lc[1]) / 2
            d = math.hypot(mx - lx, my - ly)
            if d > r + 4:
                ex, ey = mx - (mx - lx) * r / d, my - (my - ly) * r / d
                dz.line((lx, ly, ex, ey), fill=(255, 225, 40), width=2)
            dz.rectangle((la[0], la[1], lc[0], lc[1]), outline=(255, 225, 40), width=2)
            dz.ellipse((mx - r, my - r, mx + r, my + r), outline=(255, 40, 40), width=3)
        loc = loc_base.copy()
        dl = ImageDraw.Draw(loc)
        q = LW / board.width
        dl.rectangle((p0x * q - 2, p0y * q - 2, p1x * q + 2, p1y * q + 2),
                     outline=(255, 40, 40), width=3)
        out = Image.new("RGB", (LW + 12 + ZW, TH + max(lh, ZH) + 22), (255, 255, 255))
        out.paste(loc, (0, TH))
        out.paste(zoom, (LW + 12, TH))
        do = ImageDraw.Draw(out)
        do.text((2, 6), fig["title"], fill=(0, 0, 0), font=font)
        do.text((2, TH + lh + 4), "whole board, the 2x20 socket edge", fill=(60, 60, 60), font=small)
        do.text((2, TH + lh + 20), "nearest you; red box = the zoom", fill=(60, 60, 60), font=small)
        do.text((LW + 14, TH + ZH + 4),
                "red circle = the part or pin;  yellow box = the words naming it on the board"
                "  (%.0f x %.0f mm)" % (bx1 - bx0, by1 - by0), fill=(60, 60, 60), font=small)
        out.save(os.path.join(FIG_DIR, fig["name"] + ".png"), optimize=True)
    print("handbook figures: %d drawn in docs/handbook/" % len(R["figs"]))
    return 0


if __name__ == "__main__":
    if "--draw" in sys.argv:
        sys.exit(draw())
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(check(args[0] if args else os.path.join(ROOT, NAME + ".kicad_pcb")))
