"""Emit the whole board: 4-layer stackup, every part placed, ground planes.

Stackup, and why:

    L1  F.Cu      every component, and each channel's own short front-end runs
    L2  In1.Cu    solid GND, unbroken
    L3  In2.Cu    the fourteen helper-clock branches, and NOTHING else
    L4  B.Cu      solid GND

The helper branches are the only fast signals that go anywhere, and a helper
edge coupling into a 10 MHz front end would move the very threshold crossing we
are trying to measure.  Burying them on L3 between two ground planes makes them
stripline: they cannot couple to anything on L1 at all.  The 10 MHz front ends
stay on L1 as short microstrip over the L2 plane, local to their own tile.

There is no power plane.  The whole board draws about 100 mA, and the rail is
deliberately shared, so +3V3_A and +3V3_D are poured on L1 in the space between
tiles.  Trading a power plane for a second ground reference is the right way
round for a board whose product is timing, not current.
"""
import os, sys, math, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
import geom as G
import place as P
import tile as T
import helper as H
import power as PW
import maze as MZ
import netmap
from sexp import parse, kids, kid, val, head

ROOT = os.path.dirname(HERE)
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


def uid(*p):
    h = hashlib.sha1(("gpsdo|" + "|".join(map(str, p))).encode()).hexdigest()
    return "%s-%s-4%s-8%s-%s" % (h[:8], h[8:12], h[13:16], h[17:20], h[20:32])


def ser(node, ind=0):
    pad = "\t" * ind
    if isinstance(node, tuple):
        if node[0] == "str":
            return '"%s"' % node[1].replace("\\", "\\\\").replace('"', '\\"')
        return node[1]
    if all(not isinstance(c, list) for c in node):
        return "(" + " ".join(ser(c) for c in node) + ")"
    out = [pad + "(" + ser(node[0])]
    inline = []
    for c in node[1:]:
        if isinstance(c, list):
            if inline:
                out[-1] += " " + " ".join(inline); inline = []
            out.append(ser(c, ind + 1))
        else:
            inline.append(ser(c))
    if inline:
        out[-1] += " " + " ".join(inline)
    out.append(pad + ")")
    return "\n".join(out)


def A(*items):
    """Build an s-expression node from python bits."""
    out = []
    for i in items:
        if isinstance(i, list):
            out.append(i)
        elif isinstance(i, str):
            out.append(("atom", i))
        elif isinstance(i, tuple):
            out.append(i)
        else:
            out.append(("atom", ("%g" % i) if isinstance(i, float) else str(i)))
    return out


def S(s):
    return ("str", s)


_fpcache = {}
def footprint(libdir, name, ref, value, x, y, rot, layer, pads, numof):
    key = (libdir, name)
    if key not in _fpcache:
        _fpcache[key] = open(os.path.join(libdir, name + ".kicad_mod"),
                             encoding="utf-8").read()
    node = parse(_fpcache[key])[0]
    node[1] = S(name)
    # strip anything we are about to set, then set it
    node[:] = [c for c in node
               if not (isinstance(c, list) and head(c) in ("at", "uuid", "layer", "path"))]
    node.insert(2, A("layer", S(layer)))
    node.insert(3, A("uuid", S(uid("fp", ref))))
    node.insert(4, A("at", x, y, rot) if rot else A("at", x, y))
    for prop in kids(node, "property"):
        if val(prop) == "Reference":
            prop[2] = S(ref)
            # 1 mm is wider than an 0805; shrink so the silkscreen reads at 1:1
            for eff in kids(prop, "effects"):
                for fnt in kids(eff, "font"):
                    for sz in kids(fnt, "size"):
                        sz[1] = ("atom", "0.6")
                        sz[2] = ("atom", "0.6")
        elif val(prop) == "Value":
            prop[2] = S(value)
    for p in kids(node, "pad"):
        pn = val(p)
        # A pad's POSITION is rotated by the footprint angle, but its SHAPE is
        # not: KiCad takes that from the pad's own (at x y angle).  A .kicad_mod
        # leaves the angle off, so a rotated SOT-23-5 came out with its pads
        # still 1.325 mm wide across a 0.95 mm pitch -- five pads shorted to
        # each other, thirteen times over.  Carry the rotation into every pad.
        if rot:
            for a in kids(p, "at"):
                cur = float(val(a, 3) or 0.0) if len(a) > 3 else 0.0
                ang = (cur + rot) % 360.0
                if len(a) > 3:
                    a[3] = ("atom", "%g" % ang)
                else:
                    a.append(("atom", "%g" % ang))
        net = pads.get(pn)
        if net and not net.startswith("unconnected-"):
            p.append(A("net", numof[net], S(net)))
    return ser(node, 1)


def gr(kind, *items):
    return ser(A(kind, *items), 1)


def line(x0, y0, x1, y1, layer, w=0.15):
    return gr("gr_line", A("start", x0, y0), A("end", x1, y1),
              A("stroke", A("width", w), A("type", "solid")), A("layer", S(layer)),
              A("uuid", S(uid("l", x0, y0, x1, y1, layer))))


def rect(x0, y0, x1, y1, layer, w=0.15):
    return "\n".join(line(*a, layer=layer, w=w) for a in
                     ((x0, y0, x1, y0), (x1, y0, x1, y1),
                      (x1, y1, x0, y1), (x0, y1, x0, y0)))


def text(x, y, s, layer, size=1.5, thick=0.25, just="left", angle=0):
    eff = A("effects", A("font", A("size", size, size), A("thickness", thick)))
    if just not in (None, "center"):
        eff.append(A("justify", just))
    return gr("gr_text", S(s), A("at", x, y, angle), A("layer", S(layer)),
              A("uuid", S(uid("t", x, y, s, layer))), eff)


def via(x, y, net_no, tag):
    return ser(A("via", A("at", round(x, 3), round(y, 3)), A("size", 0.6),
                 A("drill", 0.3), A("layers", S("F.Cu"), S("B.Cu")),
                 A("net", net_no), A("uuid", S(uid("v", tag, x, y)))), 1)


def track(x0, y0, x1, y1, layer, net_no, tag, w=0.4):
    return ser(A("segment", A("start", round(x0, 3), round(y0, 3)),
                 A("end", round(x1, 3), round(y1, 3)), A("width", w),
                 A("layer", S(layer)), A("net", net_no),
                 A("uuid", S(uid("t", tag, x0, y0, x1, y1, layer)))), 1)


def zone(net_no, net_name, layer, poly, tag):
    pts = A("pts", *[A("xy", px, py) for px, py in poly])
    return ser(A("zone", A("net", net_no), A("net_name", S(net_name)),
                 A("layers", S(layer)) if isinstance(layer, str) else layer,
                 A("uuid", S(uid("z", tag, layer))), A("name", S(tag)),
                 A("hatch", "edge", 0.5),
                 A("connect_pads", A("clearance", 0.25)),
                 A("min_thickness", 0.25), A("filled_areas_thickness", "no"),
                 A("fill", "yes", A("thermal_gap", 0.5), A("thermal_bridge_width", 0.5)),
                 A("polygon", pts)), 1)


# ---------------------------------------------------------------------------
# Blocks that are not channel tiles: laid out in the free band between the
# lower tile row and the header socket.
# ---------------------------------------------------------------------------
def blocks(G):
    """Expressed against the board edges, so widening the board carries the
    blocks and the edge connectors with it instead of stranding them inboard."""
    return {
        "probes": (G.BW - 30.0, 100.0, G.BW - 4.0, 132.0, "1-WIRE"),
        # Moved out of the band under row B: that band is the only place the
        # twenty-five beat/pulse returns can fan into the header, and they need
        # F.Cu there as well as In2.
        "house":  (166.0, 68.0, 238.0, 96.0, "HOUSEKEEPING"),
    }

# Parts whose position is about USING the board, not about routing it.
# Cabled connectors go on an EDGE; thermometers go where the heat is.
def hand_placed(G):
    # Barrel jack at rot 0: its body reaches 14 mm in -x from pin 1, so the
    # opening already faces the left board edge.  Terminal blocks at rot 90 so
    # their wire entry faces the RIGHT edge instead of down the board.
    # The barrel jack and the two bench posts are placed by pcb/power.py, which
    # owns that block's positions and its tracks together.
    d = {"J5001": (258.0, 134.0)}                            # debug header
    for i in range(5):
        d["J600%d" % (i + 1)] = (G.BW - 8.0, 30.0 + i * 17.0, 90)
    # Eight thermometers, spread to map the gradient rather than lumped in a
    # block: four corners, the fan-out, the LDOs, and each end of the channels.
    # Each lives in one of the four horizontal bands the tiles leave free:
    # above row A (0..10), between row A and the fan-out (58.6..64), between
    # the fan-out and row B (98..102) and between row B and the header.
    temps = {"U5001": (24.0, 5.2, +1),   "U5002": (248.0, 5.2, -1),
             "U5003": (24.0, 156.0, +1), "U5004": (248.0, 156.0, -1),
             "U5005": (141.0, 93.5, +1),                   # under the fan-out
             "U5006": (12.0, 120.0, +1),                   # beside the LDOs
             "U5007": (30.0, 62.0, +1),                    # under unit 1
             "U5008": (213.0, 128.0, +1)}                  # beside unit 13
    for ref, (sx, sy, side) in temps.items():
        d[ref] = (sx, sy)
    # A thermometer's bead and capacitors have to travel WITH it.  Spreading the
    # sensors while leaving their decoupling in the housekeeping block left one
    # Vcc node spanning 310 mm, which is not decoupling at all.  They sit in a
    # row beside the sensor, on whichever side has board left.
    for i, (ref, (sx, sy, side)) in enumerate(sorted(temps.items())):
        d["FB500%d" % (i + 1)] = (sx - 5.6 * side, sy)
        d["C50%02d" % (2 * i + 1)] = (sx + 5.6 * side, sy)
        d["C50%02d" % (2 * i + 2)] = (sx + 9.4 * side, sy)

    # The twenty-four heaters, spread on a ~37 x 50 mm grid over the channel
    # rows.  Lumping them in the power block would defeat the entire point: the
    # copper only spreads heat about 40 mm, so the heaters have to BE where the
    # channels are.  The rows sit in the same four free bands as the sensors.
    hx = [46.0 + i * 37.0 for i in range(6)]
    for i in range(24):
        d["R20%02d" % (i + 1)] = (hx[i % 6], (5.0, 61.5, 100.0, 155.0)[i // 6])

    # X3001, U3001-U3007 and the rest of the helper chain are NOT here: they
    # are placed together by pcb/helper.py, which owns both their positions and
    # their tracks.
    return d


def block_of(ref):
    """Which block a reference belongs to, from its numbering scheme."""
    import re
    m = re.match(r"^([A-Za-z#]+)(\d+)$", ref)
    if not m:
        return None
    pre, n = m.group(1), m.group(2)
    if pre in ("H",):
        return None
    if len(n) >= 4 and n[0] in "123456" and n[1] == "0":
        return {"2": "power", "3": "helper", "5": "house", "6": "probes"}.get(n[0])
    return None          # channel tiles are handled separately


def unit_of(ref):
    import re
    m = re.match(r"^([A-Za-z]+)(\d+)$", ref)
    if not m:
        return None, None
    pre, n = m.group(1), m.group(2)
    for u in range(13, 0, -1):
        s = str(u)
        if n.startswith(s) and len(n) == len(s) + 2:
            return u, pre + n[len(s):]
    return None, None


def build():
    S_ = os.environ.get("NLDIR", "/tmp")
    fps, vals, nets, numof = netmap.load(os.path.join(S_, "nl.net"))
    out, placed, boxes = [], {}, {}

    def put(ref, x, y, rot=0, layer="F.Cu"):
        fp = fps.get(ref)
        if not fp:
            return
        lib, name = fp.split(":", 1)
        d = LOCAL_FP if lib == "GPSDO-PYNQ-Z2" else os.path.join(KFP, lib + ".pretty")
        out.append(footprint(d, name, ref, vals.get(ref, ""), round(x, 3), round(y, 3),
                             rot, layer, nets.get(ref, {}), numof))
        placed[ref] = (x, y, rot)
        boxes[ref] = P.box_at(d, name, x, y, rot)

    def free(ref, x, y, rot=0):
        """Would this land on something already placed?  Only the CANDIDATE is
        tested: checking every existing pair meant one pre-existing overlap
        anywhere made every position look occupied, and nothing got placed."""
        lib, name = fps[ref].split(":", 1)
        d = LOCAL_FP if lib == "GPSDO-PYNQ-Z2" else os.path.join(KFP, lib + ".pretty")
        n0, n1, n2, n3 = P.box_at(d, name, x, y, rot)
        for r, (b0, b1, b2, b3) in boxes.items():
            if r != ref and n0 < b2 and b0 < n2 and n1 < b3 and b1 < n3:
                return False
        return True

    # ---- outline, PYNQ, mounting -----------------------------------------
    out.append(rect(0, 0, G.BW, G.BH, "Edge.Cuts", 0.1))
    p0, p1 = G.B(0, G.PZ_H), G.B(G.PZ_W, 0)
    out.append(rect(p0[0], p0[1], p1[0], p1[1], "Dwgs.User", 0.2))
    out.append(text(84.0, G.BH - 1.5, "PYNQ-Z2 outline (137.0 x 87.0).  Our bottom edge is "
                    "11.0 mm from its top edge, clear of the HDMI at 11.5 and the Arduino "
                    "header at 20.", "Dwgs.User", 1.3, 0.2))
    for n in range(1, 41):
        hx, hy = G.hdr_pin(n)
        out.append(gr("gr_circle", A("center", hx, hy), A("end", hx + 0.5, hy),
                      A("stroke", A("width", 0.1), A("type", "solid")),
                      A("fill", "no"), A("layer", S("Dwgs.User")),
                      A("uuid", S(uid("hp", n)))))
    for i, ((mx, my), note) in enumerate(G.MOUNT):
        put("H%d" % (i + 1), mx, my)
        out.append(text(mx + 4.0, my + 4.5, note, "Cmts.User", 1.0, 0.15))

    # ---- the socket -------------------------------------------------------
    px, py = G.hdr_pin(1)
    put("J4001", px, py, 0, "B.Cu")
    out.append(text(178.0, 168.0, "RPi 40-PIN SOCKET, UNDERSIDE", "F.SilkS", 1.6, 0.28))
    out.append(text(px + 2.5, py + 1.0, "1", "F.SilkS", 1.6, 0.3))
    # Every header pin named on the silk.  Rotated 90 so a three-character name
    # fits in the 2.54 mm pitch; odd row reads above the connector, even below.
    import design as _D
    def _short(net):
        if net.startswith("+3V3"):
            return "3V3"
        if net.startswith("+5V"):
            return "5V"
        if net == "GND":
            return "GND"
        if net.startswith("I2C_"):
            return net[4:]
        if net.startswith("HELPER"):
            return "HCK"
        if net.startswith("BEAT_"):
            return "B" + net[5:]
        if net.startswith("PPS_"):
            return "P" + net[4:]
        return net[:3]
    for pinno in range(1, 41):
        gx, gy = G.hdr_pin(pinno)
        nm = _short(_D.HEADER[pinno][0])
        if pinno % 2:
            out.append(text(gx, gy - 3.4, nm, "F.SilkS", 1.0, 0.16, angle=90))
        else:
            out.append(text(gx, gy + 3.4, nm, "F.SilkS", 1.0, 0.16, angle=90,
                            just="right"))

    # ---- SMA jacks --------------------------------------------------------
    smaxy = {}
    for row in G.sma_rows():
        for x, y, tag, desc in row:
            smaxy[tag] = (x, y)
            out.append(text(x, y - 6.8, tag, "F.SilkS", 2.4, 0.4))
    for tag, ref in (("HIN", "J3002"), ("HO", "J3001")):
        put(ref, *smaxy[tag])

    # ---- the thirteen channel tiles ---------------------------------------
    byunit = {}
    for ref in fps:
        u, slot = unit_of(ref)
        if u:
            byunit.setdefault(u, {})[slot] = ref
    TILE = T.tile(G.SMA_PITCH)
    for u in sorted(byunit):
        ox, oy = G.unit_origin(u)
        for slot, ref in byunit[u].items():
            if slot not in TILE:
                out.append(text(4, 2, "UNPLACED %s" % ref, "Cmts.User", 1.0))
                continue
            dx, dy, rot = TILE[slot]
            put(ref, ox + dx, oy + dy, rot)

    # ---- the tile's own tracks, stamped out thirteen times ----------------
    tracks = []          # (x0, y0, x1, y1, layer, netname, width)

    def netof(u, slot, pad):
        r = byunit.get(u, {}).get(slot)
        return nets.get(r, {}).get(pad) if r else None

    def run(u, ox, oy, spec, xoff=0.0):
        (slot, pad), w, pts = spec
        nm = netof(u, slot, pad)
        if not nm or nm.startswith("unconnected-"):
            return
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            if (x0, y0) == (x1, y1):
                continue
            tracks.append((ox + xoff + x0, oy + y0, ox + xoff + x1, oy + y1,
                           "F.Cu", nm, w))

    tile_vias = []       # (x, y, netname)
    in2_term = {}        # net -> [(x, y)] where the maze router may start

    def escape(vx, vy, ey, nm, ex=None):
        """Take an In2 via out of the crowded tile to a clear approach line.

        The far end is snapped to the router's 0.5 mm grid: leaving it on the
        via's own x put the hand-off segment off-grid, and two of those landed
        0.13 mm apart against a 0.15 mm rule."""
        tile_vias.append((vx, vy, nm))
        ex = vx if ex is None else ex
        sx = round(ex / MZ.PITCH) * MZ.PITCH
        sy = round(ey / MZ.PITCH) * MZ.PITCH
        if ex != vx:
            tracks.append((vx, vy, ex, vy, "In2.Cu", nm, T.W_SIG))
        tracks.append((ex, vy, ex, sy, "In2.Cu", nm, T.W_SIG))
        if sx != ex:
            tracks.append((ex, sy, sx, sy, "In2.Cu", nm, T.W_SIG))
        in2_term.setdefault(nm, []).append((sx, sy))

    # Both rails of every tile stop on the same line, 1.4 mm under the taller
    # of the two boxes, so one horizontal spine per row picks all of them up
    # without ever entering a box.
    def spine(row_y, xs, nm):
        xs = sorted(xs)
        tracks.append((xs[0], row_y + T.RAIL_FOOT, xs[-1], row_y + T.RAIL_FOOT,
                       "F.Cu", nm, T.W_PWR))
    railxs = {}
    for u in sorted(byunit):
        ox, oy = G.unit_origin(u)
        for spec in T.routes_10m():
            run(u, ox, oy, spec)
        if byunit[u].get("U04"):
            for spec in T.routes_pps():
                run(u, ox, oy, spec, G.SMA_PITCH)
        railxs.setdefault(oy, []).extend(
            [ox + T.RAIL_10M] + ([ox + T.RAIL_PPS] if byunit[u].get("U04") else []))
        for slot, pad, vx, vy in T.VIAS_10M:
            nm = netof(u, slot, pad)
            if nm:
                up = nm.startswith("HCLK") and oy > 60
                escape(ox + vx, oy + vy, oy - 8.0 if up else oy + 45.5, nm,
                       ox - 7.6 if up else None)
        if byunit[u].get("U04"):
            for slot, pad, vx, vy in T.VIAS_PPS:
                nm = netof(u, slot, pad)
                if nm:
                    escape(ox + G.SMA_PITCH + vx, oy + vy, oy + 45.5, nm)

    for oy, xs in railxs.items():
        spine(oy, xs, "+3V3_A")

    # ---- the helper oscillator and its fan-out ---------------------------
    # Placed so the four second-stage buffers straddle the board centre line,
    # which is only cosmetic -- round 10 killed branch-length matching -- but
    # keeps the fourteen In2.Cu branches roughly symmetric about the middle.
    HX, HY = G.BW / 2.0 - 88.5, 80.0
    for ref, (dx, dy, rot) in sorted(H.PARTS.items()):
        put(ref, HX + dx, HY + dy, rot)

    def hnet(slot, pad):
        return nets.get(slot, {}).get(pad)

    for (slot, pad), w, pts in H.routes():
        nm = hnet(slot, pad)
        if not nm or nm.startswith("unconnected-"):
            continue
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            if (x0, y0) != (x1, y1):
                tracks.append((HX + x0, HY + y0, HX + x1, HY + y1,
                               "F.Cu", nm, w))
    for (slot, pad), w, pts in H.IN2_ROUTES:
        nm = hnet(slot, pad)
        if nm:
            for i in range(len(pts) - 1):
                (x0, y0), (x1, y1) = pts[i], pts[i + 1]
                tracks.append((HX + x0, HY + y0, HX + x1, HY + y1,
                               "In2.Cu", nm, w))
    # ---- the power input block -------------------------------------------
    for ref, (px, py, prot) in sorted(PW.PARTS.items()):
        put(ref, px, py, prot)
    for (slot, pad), w, pts in PW.routes():
        nm = nets.get(slot, {}).get(pad)
        if not nm or nm.startswith("unconnected-"):
            continue
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            if (x0, y0) != (x1, y1):
                tracks.append((x0, y0, x1, y1, "F.Cu", nm, w))
    out.append(text(4.0, 20.0, "POWER", "F.SilkS", 2.0, 0.34))

    LOCAL = {"HELPER_SRC"}          # hand-routed above, inside the block
    for slot, pad, vx, vy in H.VIAS:
        nm = hnet(slot, pad)
        if not nm:
            continue
        if nm in LOCAL:
            tile_vias.append((HX + vx, HY + vy, nm))
        else:
            escape(HX + vx, HY + vy, HY + 12.0, nm,
                   None)
    out.append(text(HX - 4.0, HY + H.RAIL_Y - 2.5,
                    "HELPER OSCILLATOR AND FAN-OUT", "F.SilkS", 2.0, 0.34))

    # ---- hand-placed: edges and hot spots ---------------------------------
    for ref, xy in sorted(hand_placed(G).items()):
        put(ref, xy[0], xy[1], xy[2] if len(xy) > 2 else 0)
    for i, tx in enumerate(("15 V DC, 1 A MIN", "HEATER ONLY", "CENTRE POSITIVE")):
        out.append(text(3.0, 14.0 + i * 3.2, tx, "F.SilkS", 1.5, 0.26))
    out.append(text(3.0, 59.0, "BENCH SUPPLY  5 V, 0.5 A MIN", "F.SilkS", 1.4, 0.24))
    out.append(text(3.0, 61.8, "NOT 15 V - THAT GOES TO THE JACK", "F.SilkS", 1.2, 0.2))
    out.append(text(2.5, 64.6, "+5V", "F.SilkS", 1.5, 0.28))
    out.append(text(2.5, 72.6, "GND", "F.SilkS", 1.5, 0.28))
    for i in range(5):
        out.append(text(206.0, 26.0 + i * 16.0, "P%d" % (i + 1), "F.SilkS", 1.8, 0.3))
    out.append(text(212.0, 132.0, "DEBUG", "F.SilkS", 1.8, 0.3))
    for r in ("U5001", "U5002", "U5003", "U5004", "U5005", "U5006", "U5007", "U5008"):
        if r in placed:
            out.append(text(placed[r][0] - 0.7, placed[r][1] + 5.2, "T", "F.SilkS", 1.8, 0.32))

    # ---- a silkscreen box around each input circuit ------------------------
    # One per 10 MHz chain and one per pps chain, so each unit reads as two
    # separate modules.  These are also where the via fences go.
    TPLETTER = {"TP_IN": "I", "TP_SQ": "S", "TP_BEAT": "B", "TP_PPS": "P",
                "TP_5V": "5", "TP_3V3_A": "A", "TP_3V3_D": "D",
                "TP_XA": "X", "TP_1W": "W"}
    # Each box is a FIXED rectangle centred on its own SMA rather than the
    # bounding box of its contents.  Sizing to contents is exactly what put the
    # 1 pps jack off to one side of its own rectangle: the pps half has parts
    # out to +5.5 mm and only -4.4 mm, so its box drifted right by half a
    # millimetre per part.  A fixed rectangle also makes the two boxes of a
    # unit read as a pair, and gives the gutter a constant width for the rail.
    for u in sorted(byunit):
        ox, oy = G.unit_origin(u)
        groups = [(T.BOX_10M, 0.0)]
        if byunit[u].get("U04"):
            groups.append((T.BOX_PPS, G.SMA_PITCH))
        for (bx0, by0, bx1, by1), xoff in groups:
            out.append(rect(ox + xoff + bx0, oy + by0, ox + xoff + bx1, oy + by1,
                            "F.SilkS", 0.15))

    # ---- test point letters, next to the pad ------------------------------
    for r, xy in placed.items():
        if not r.startswith("TP"):
            continue
        L = TPLETTER.get(vals.get(r, ""))
        if L:
            out.append(text(xy[0] + 1.5, xy[1] - 1.4, L, "F.SilkS", 1.5, 0.3))

    # ---- debug header, a name against every pin ---------------------------
    if "J5001" in placed:
        hx, hy, _ = placed["J5001"]
        sigs = ["+3V3_A", "+3V3_D", "+5V_HDR", "HELPER_CLK", "HCLK_00",
                "BEAT_00", "BEAT_12", "PPS_00", "I2C_SDA", "I2C_SCL"]
        for i, s in enumerate(sigs):
            out.append(text(hx - 2.6, hy + i * 2.54 + 0.5, s, "F.SilkS", 1.1, 0.18,
                            just="right"))
            out.append(text(hx + 5.2, hy + i * 2.54 + 0.5, "GND", "F.SilkS", 1.1, 0.18))

    # ---- everything else, in blocks ---------------------------------------
    byblock = {}
    for ref in fps:
        b = block_of(ref)
        if b and ref not in placed:
            byblock.setdefault(b, []).append(ref)
    overflow = []
    BL = blocks(G)
    for b, refs in sorted(byblock.items()):
        if b not in BL:                  # the block places itself now
            continue
        bx, by, bx1, by1, label = BL[b]
        refs = [r for r in refs if r not in placed]
        # ICs and connectors first so they anchor the block, then passives
        def rank(r):
            f = fps[r]
            return (0 if ("SO:" in f or "SOT" in f or "Oscillator" in f) else
                    1 if ("Connector" in f or "Terminal" in f or "BarrelJack" in f) else 2, r)
        refs.sort(key=rank)
        cx, cy, rowh = bx, by, 0.0
        for r in refs:
            w, h = P.SIZE.get(fps[r], P.DEFAULT_SIZE)
            # Step past anything already sitting there.  The grid does not know
            # about the hand-placed parts, and skipping them by REFERENCE is not
            # the same as skipping their AREA.
            for _ in range(600):
                if cx + w > bx1:
                    cx, cy, rowh = bx, cy + rowh + 1.6, 0.0
                if cy + h > by1:
                    break
                if free(r, cx + w / 2.0, cy + h / 2.0):
                    break
                cx += 1.27
            if cy + h > by1:
                overflow.append((b, r))
                continue
            put(r, cx + w / 2.0, cy + h / 2.0)
            cx += w + 1.6
            rowh = max(rowh, h)
        out.append(text(bx, by - 2.0, label, "F.SilkS", 2.0, 0.3))
        out.append(rect(bx - 1.5, by - 4.5, bx1 + 1.5, by1 + 1.5, "Cmts.User", 0.12))
    if overflow:
        out.append(text(4.0, 99.0, "OVERFLOW: %d parts did not fit their block"
                        % len(overflow), "Cmts.User", 2.0, 0.3))
        import sys as _s
        print("OVERFLOW:", overflow, file=_s.stderr)

    # ---- probe terminal legend, on the board where the wires get screwed in
    for i in range(5):
        pr = "J600%d" % (i + 1)
        if pr not in placed:
            continue
        lib, nm = fps[pr].split(":", 1)
        dd = LOCAL_FP if lib == "GPSDO-PYNQ-Z2" else os.path.join(KFP, lib + ".pretty")
        for pn, ax, ay, _t, _h in P.pads(dd, nm, *placed[pr]):
            lab = {"1": "DAT yel", "2": "VCC red", "3": "GND blk"}.get(pn)
            if lab:
                out.append(text(ax - 7.5, ay + 0.5, lab, "F.SilkS", 1.25, 0.2,
                                just="right"))
    out.append(text(112.0, 97.5, "1-WIRE PROBES: STANDARD SPEED ONLY, no 4k7 pullup "
                    "(the DS2482 has its own)", "F.SilkS", 1.3, 0.22))

    # ---- every SMD GND pad gets a stub and a via down to the plane ---------
    # This is what makes the ratsnest readable: with ground already connected,
    # what is left on screen is only the signals.  Through-hole GND pads are
    # skipped -- their own barrel already reaches every layer.
    import math as _m
    allpads = []
    for ref, (px, py, prot) in sorted(placed.items()):
        lib, name = fps[ref].split(":", 1)
        d = LOCAL_FP if lib == "GPSDO-PYNQ-Z2" else os.path.join(KFP, lib + ".pretty")
        for pn, ax, ay, tht, hd in P.pads(d, name, px, py, prot):
            allpads.append((ref, pn, ax, ay, tht, nets.get(ref, {}).get(pn), hd))

    gnd_no = numof["GND"]

    # ---- lay the tile tracks and their In2 vias ---------------------------
    # Done before the ground vias so the ground-via search can see them: a via
    # dropped on top of a signal track is the one failure mode that a pad-only
    # collision test cannot catch.
    for x0, y0, x1, y1, lyr, nm, w in tracks:
        out.append(track(x0, y0, x1, y1, lyr, numof[nm], "tile", w))
    for vx, vy, nm in tile_vias:
        out.append(via(vx, vy, numof[nm], "tv%s" % nm))

    def seg_clear(px, py, rad):
        """Is a disc of radius rad at (px, py) clear of every signal track?"""
        for x0, y0, x1, y1, _l, _n, w in tracks:
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy
            u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x0) * dx +
                                                       (py - y0) * dy) / L2))
            qx, qy = x0 + u * dx, y0 + u * dy
            if (px - qx) ** 2 + (py - qy) ** 2 < (rad + w / 2.0 + 0.15) ** 2:
                return False
        for tx, ty, _n in tile_vias:
            if (px - tx) ** 2 + (py - ty) ** 2 < (rad + 0.45) ** 2:
                return False
        return True

    vias, nvia, skipped = [], 0, 0
    for ref, pn, ax, ay, tht, net, _hd in allpads:
        if net != "GND" or tht:
            continue
        best = None
        for rad in (1.35, 1.8, 2.3, 2.8):
            for k in range(8):
                th = k * _m.pi / 4.0
                vx, vy = ax + rad * _m.cos(th), ay + rad * _m.sin(th)
                # 0.3 via radius + that pad's OWN half-diagonal + 0.25 clearance.
                # A constant was fine for 0805s and far too small for the
                # SOT-223 tab and the SMA diodes.
                ok = all((vx - qx) ** 2 + (vy - qy) ** 2 > (0.55 + qh) ** 2
                         for _r, _p, qx, qy, _t, _n, qh in allpads
                         if not (_r == ref and _p == pn))
                ok = ok and all((vx - wx) ** 2 + (vy - wy) ** 2 > 1.5 ** 2
                                for wx, wy in vias)
                # the STUB has to clear other pads too, not just the via:
                # checking only the endpoint left tracks running over pads
                if ok:
                    for f in (0.35, 0.6, 0.85):
                        sx, sy = ax + (vx - ax) * f, ay + (vy - ay) * f
                        if not all((sx - qx) ** 2 + (sy - qy) ** 2 > (0.43 + qh) ** 2
                                   for _r, _p, qx, qy, _t, _n, qh in allpads
                                   if not (_r == ref and _p == pn)):
                            ok = False
                            break
                ok = ok and seg_clear(vx, vy, 0.3)
                if ok:
                    for f in (0.3, 0.5, 0.7, 0.9):
                        if not seg_clear(ax + (vx - ax) * f,
                                         ay + (vy - ay) * f, 0.175):
                            ok = False
                            break
                if ok:
                    best = (vx, vy)
                    break
            if best:
                break
        if not best:
            skipped += 1
            continue
        vx, vy = best
        vias.append((vx, vy))
        out.append(track(ax, ay, vx, vy, "F.Cu", gnd_no, ref + pn, 0.35))
        out.append(via(vx, vy, gnd_no, ref + pn))
        nvia += 1
    out.append(text(4.0, G.BH - 2.0, "%d ground vias (%d pads had no room)"
                    % (nvia, skipped), "Cmts.User", 1.2, 0.2))

    # ---- In2.Cu: helper branches, beat/pulse returns, helper SMAs ---------
    # Routed by a maze router (pcb/maze.py) rather than by hand-assigned lanes.
    # Twenty-five returns converge on a 48 mm connector from sources spread
    # over 200 mm; that is a single-layer planarity problem, and a router that
    # only ever walks free cells cannot produce a crossing.
    _ntracks0, _nvias0 = len(tracks), len(tile_vias)
    grid = MZ.Grid(G.BW, G.BH)
    IN2, FCU = 0, 1
    for ref, pn, ax, ay, tht, net, hd in allpads:
        if tht:
            grid.block_disc(ax, ay, hd + 0.35)          # both layers
        else:
            grid.block_disc(ax, ay, hd + 0.85, FCU)
    for vx, vy in vias:                                 # the ground vias
        grid.block_disc(vx, vy, 0.62)
    for vx, vy, _nm in tile_vias:
        grid.block_disc(vx, vy, 0.62)
    for x0, y0, x1, y1, lyr, nm, w in tracks:
        grid.block_seg(x0, y0, x1, y1, w / 2.0 + 0.3,
                       IN2 if lyr == "In2.Cu" else FCU)

    # Each header pin gets a stub up to a common y = 160.5 approach line.  The
    # two rows share an x, so an even-row (far) pin cannot be entered from
    # above: its stub steps 1.27 mm sideways first, which lands exactly midway
    # between two odd-row pads -- 1.27 mm from each, against a 1.125 mm
    # requirement -- and then runs up past them.
    # The two rows stop on DIFFERENT approach lines.  Sharing one line put
    # every target 1.27 mm from its neighbour, which on a 0.5 mm grid leaves a
    # target with no free neighbour at all once two of them are used -- most
    # early routing failures were simply a boxed-in destination.  Staggering
    # the rows makes the spacing 2.54 mm within each line, at the price of a
    # 3 mm-deep comb instead of a single row.
    ODD_Y, EVEN_Y = 160.0, 157.0
    hdrnets = nets.get("J4001", {})
    targets = {}
    for n in range(1, 41):
        nm = hdrnets.get(str(n))
        if not nm or nm in ("GND", "+5V_HDR") or nm.startswith("unconnected-"):
            continue
        hx, hy = G.hdr_pin(n)
        if n % 2:
            tx, ty = hx, ODD_Y
            tracks.append((hx, hy, tx, ty, "In2.Cu", nm, T.W_SIG))
        else:
            # The far row shares its x with the near row, so it cannot be
            # entered from above: step 1.27 mm sideways first, exactly midway
            # between two near-row pads (1.27 mm from each, against 1.125).
            tx, ty = hx - 1.27, EVEN_Y
            tracks.append((hx, hy, tx, hy, "In2.Cu", nm, T.W_SIG))
            tracks.append((tx, hy, tx, ty, "In2.Cu", nm, T.W_SIG))
        grid.block_seg(tx, hy, tx, G.BH - 1.0, 0.4, IN2)
        grid.block_seg(tx, hy, tx, ty, 0.4, IN2)
        grid.block_seg(hx, hy, tx, hy, 0.4, IN2)
        sx = round(tx / MZ.PITCH) * MZ.PITCH
        if sx != tx:
            tracks.append((tx, ty, sx, ty, "In2.Cu", nm, T.W_SIG))
            grid.block_seg(tx, ty, sx, ty, 0.4, IN2)
        targets[nm] = (sx, ty)

    # Everything that has to be joined, as (net, endA, endB, stage).
    jobs = []
    src = in2_term
    for nm, pts in sorted(src.items()):
        if nm in targets and len(pts) == 1:
            # The helper clock to the FPGA goes with the branches, before the
            # fan-in: it starts in the middle of the fan-out and would be
            # walled in by the time the returns are done.
            jobs.append((nm, pts[0], targets[nm],
                         -1 if nm == "HELPER_CLK" else 0))
    for nm in sorted(src):
        if nm.startswith("HCLK_") and len(src[nm]) == 2:
            aa, bb = sorted(src[nm], key=lambda q: q[1])
            jobs.append((nm, aa, bb, -1))
    for nm in ("Net-(J3001-In)", "Net-(J3002-In)"):
        pts = list(src.get(nm, []))
        for ref, pn, ax, ay, tht, net, _hd in allpads:
            if net == nm and tht:
                # A vertical SMA's centre pin sits inside a ring of four
                # ground pins 2.54 mm away, so nothing can start next to it:
                # give it a stub straight up the 1.14 mm gutter between them.
                ey = round((ay - 12.0) / MZ.PITCH) * MZ.PITCH
                tracks.append((ax, ay, ax, ey, "In2.Cu", nm, T.W_SIG))
                grid.block_seg(ax, ay, ax, ey, 0.4, IN2)
                pts.append((ax, ey))
        if len(pts) == 2:
            jobs.append((nm, pts[0], pts[1], -2))

    # Order matters to a maze router: a finished route is a wall.  The helper
    # SMAs and the branches go first because their corridors are narrow, then
    # the header fan-in from the OUTSIDE in, so the long runs claim the outer
    # lanes and the short ones nest inside them.
    ctr = (144.02 + 192.28) / 2.0
    ORD = int(os.environ.get("RTORDER", "2"))
    CAP = int(os.environ.get("RTCAP", "2000000"))
    _k = {0: lambda j: -abs(j[1][0] - ctr),
          1: lambda j: abs(j[1][0] - ctr),
          # 2: left to right by target pin, but anything that barely has to
          #    travel goes first -- a net whose source is already under its own
          #    pin has no room to manoeuvre and gets boxed in otherwise.
          2: lambda j: (0 if abs(j[1][0] - j[2][0]) < 15.0 else 1, j[2][0]),
          3: lambda j: -j[2][0],
          4: lambda j: (j[1][1], -abs(j[1][0] - ctr)),
          5: lambda j: (-j[1][1], -abs(j[1][0] - ctr)),
          # 6: the nets that travel LEFT first (they are few and live at the
          #    right-hand end), then everything else left to right.  A maze
          #    router's finished route is a wall, so the long runs have to
          #    claim their lanes before the short ones box them in.
          6: lambda j: (0 if j[1][0] > j[2][0] else 1, j[2][0]),
          7: lambda j: -abs(j[1][0] - j[2][0]),
          8: lambda j: (0 if j[1][0] > j[2][0] else 1, -j[2][0])}[ORD]
    jobs.sort(key=lambda j: (j[3], _k(j)))
    # Rip-up and retry.  A maze router's finished route is a wall, so the
    # order decides who gets boxed in; the standard cure is to put whoever
    # failed at the FRONT of the next attempt and start over from a clean
    # layer.  Three passes is enough here -- it goes 37, 40, 41.
    def one_pass(order, base_tracks, base_vias):
        g = MZ.Grid(G.BW, G.BH)
        for ref, pn, ax, ay, tht, net, hd in allpads:
            if tht:
                g.block_disc(ax, ay, hd + 0.35)
            else:
                g.block_disc(ax, ay, hd + 0.85, FCU)
        for vx, vy in vias:
            g.block_disc(vx, vy, 0.62)
        for vx, vy, _nm in base_vias:
            g.block_disc(vx, vy, 0.62)
        for x0, y0, x1, y1, lyr, nm, w in base_tracks:
            g.block_seg(x0, y0, x1, y1, w / 2.0 + 0.3,
                        IN2 if lyr == "In2.Cu" else FCU)
        newt, newv, fail = [], [], []
        for nm, aa, bb, _k in order:
            g.free_disc(aa[0], aa[1], 0.3, IN2)
            g.free_disc(bb[0], bb[1], 0.3, IN2)
            path = g.route(aa, bb, layers=(IN2, FCU), start_layer=IN2, cap=CAP)
            if not path:
                path = g.route(aa, bb, layers=(IN2, FCU), start_layer=IN2,
                               turn=0.4, cap=CAP)
            if not path and g._via_ok(*g.cell(*bb)):
                path = g.route(aa, bb, layers=(IN2, FCU), start_layer=IN2,
                               end_layer=FCU, turn=0.4, cap=CAP)
                if path:
                    path = path + [(bb[0], bb[1], IN2)]
            if path:
                pts = ([(aa[0], aa[1], IN2)] + path[1:-1] +
                       [(bb[0], bb[1], path[-1][2])])
                if path[-1][2] != IN2:
                    pts.append((bb[0], bb[1], IN2))
                for i in range(len(pts) - 1):
                    x0, y0, l0 = pts[i]
                    x1, y1, l1 = pts[i + 1]
                    if l0 != l1:
                        newv.append((x0, y0, nm))
                        g.block_disc(x0, y0, 0.62)
                    elif (x0, y0) != (x1, y1):
                        newt.append((x0, y0, x1, y1,
                                     "In2.Cu" if l0 == IN2 else "F.Cu", nm,
                                     T.W_SIG))
                        g.block_seg(x0, y0, x1, y1, 0.4, l0)
            else:
                fail.append(nm)
                if os.environ.get("RTDEBUG"):
                    import sys as _dbg
                    for lbl, q in (("A", aa), ("B", bb)):
                        ci, cj = g.cell(*q)
                        row = []
                        for L in (IN2, FCU):
                            free = sum(0 if g.blocked[L][(cj+dj)*g.nx+ci+di] else 1
                                       for di, dj in ((1,0),(-1,0),(0,1),(0,-1)))
                            row.append(free)
                        print("  %s %s %s free-neighbours In2=%d F.Cu=%d"
                              % (nm, lbl, q, row[0], row[1]), file=_dbg.stderr)
            g.block_disc(aa[0], aa[1], 0.62, IN2)
            g.block_disc(bb[0], bb[1], 0.62, IN2)
        return newt, newv, fail

    base_t, base_v = list(tracks), list(tile_vias)
    order = list(jobs)
    best = None
    for attempt in range(3):
        nt, nv, nfail = one_pass(order, base_t, base_v)
        if best is None or len(nfail) < len(best[2]):
            best = (nt, nv, nfail)
        if not nfail:
            break
        bad = set(nfail)
        order = ([j for j in order if j[0] in bad] +
                 [j for j in order if j[0] not in bad])
    nt, nv, nfail = best
    tracks.extend(nt)
    tile_vias.extend(nv)
    import sys as _s
    print("routed %d of %d off-block nets" % (len(jobs) - len(nfail), len(jobs)),
          file=_s.stderr)
    if nfail:
        print("  FAILED:", nfail, file=_s.stderr)
        out.append(text(4.0, 103.0, "UNROUTED: %s" % ", ".join(nfail),
                        "Cmts.User", 2.0, 0.3))
    for x0, y0, x1, y1, lyr, nm, w in tracks[_ntracks0:]:
        out.append(track(x0, y0, x1, y1, lyr, numof[nm], "rt", w))
    for vx, vy, nm in tile_vias[_nvias0:]:
        out.append(via(vx, vy, numof[nm], "rv%s%g%g" % (nm, vx, vy)))

    # ---- ground planes on both inner-adjacent layers ----------------------
    poly = [(0.3, 0.3), (G.BW - 0.3, 0.3), (G.BW - 0.3, G.BH - 0.3), (0.3, G.BH - 0.3)]
    for lyr in ("In1.Cu", "B.Cu"):
        out.append(zone(numof["GND"], "GND", lyr, poly, "GND-" + lyr))

    # ---- silkscreen -------------------------------------------------------
    out.append(text(6.0, 164.0, "GPSDO DDMTD FRONT END   rev A", "F.SilkS", 2.4, 0.4))
    out.append(text(6.0, 168.0, "Jason Gallicchio   jason@hmc.edu   2026-09-09",
                    "F.SilkS", 1.8, 0.3))
    out.append(text(58.0, 8.0, "n = 10 MHz IN    Pn = 1 pps IN    13 = NULL    "
                    "HIN = EXT HELPER IN    HO = CLK1 OUT", "F.SilkS", 1.5, 0.26))
    # Two columns as two text objects at fixed x.  Padding one string with
    # spaces cannot align them: KiCad's stroke font is not fixed-width, so an
    # "I" and a "W" advance by different amounts.
    out.append(text(124.0, 149.0, "TEST POINTS - the letter beside each pad.  "
                    "Ranges, not per-channel values", "F.SilkS", 1.5, 0.24))
    LC = ["I  at the SMA        1.0-8.0 Vpp",
          "B  beat out          0/3.3 V, 1.1-1.4 kHz",
          "X  Si5351 drive      0.5-1.0 Vpp, 25 MHz",
          "A  +3V3_A            3.25-3.35 V"]
    RC = ["S  at the squarer   0.6-3.3 Vpp, mid-rail",
          "P  pps out          0/3.3 V, 1 Hz",
          "W  1-Wire bus        5  5 V rail 4.6-5.3 V",
          "D  +3V3_D           3.25-3.35 V"]
    for i, (a, c) in enumerate(zip(LC, RC)):
        out.append(text(124.0, 152.6 + i * 3.0, a, "F.SilkS", 1.35, 0.22))
        out.append(text(196.0, 152.6 + i * 3.0, c, "F.SilkS", 1.35, 0.22))

    return out, placed, fps, boxes


def render():
    out, placed, fps, boxes = build()
    bad = P.overlaps_boxes(boxes)
    lay = "\n".join('\t\t(%d "%s" %s%s)' % (l[0], l[1], l[2],
                                            (' "%s"' % l[3]) if len(l) > 3 else "")
                    for l in LAYERS)
    _, _, _, numof = netmap.load(os.path.join(os.environ.get("NLDIR", "/tmp"), "nl.net"))
    nets = "\n".join('\t(net %d "%s")' % (n, nm) for nm, n in
                     sorted(numof.items(), key=lambda kv: kv[1]))
    stack = ('\t\t(stackup\n'
             '\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))\n'
             '\t\t\t(layer "dielectric 1" (type "prepreg") (thickness 0.2104))\n'
             '\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.0175))\n'
             '\t\t\t(layer "dielectric 2" (type "core") (thickness 1.065))\n'
             '\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.0175))\n'
             '\t\t\t(layer "dielectric 3" (type "prepreg") (thickness 0.2104))\n'
             '\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))\n'
             '\t\t\t(copper_finish "ENIG")\n\t\t)')
    body = "\n".join(o for o in out if o)
    txt = ('(kicad_pcb\n\t(version 20241229)\n\t(generator "gpsdo-pynq-z2")\n'
           '\t(generator_version "9.0")\n'
           '\t(general (thickness 1.6) (legacy_teardrops no))\n'
           '\t(paper "A2")\n\t(layers\n%s\n\t)\n'
           # NOTE: a (rules ...) block is NOT legal inside a .kicad_pcb setup --
           # it makes KiCad fail to load the board with no useful message.  The
           # numeric design rules live in GPSDO-PYNQ-Z2.kicad_pro instead (see
           # gen/project.py), where 0.15 mm clearance is set because the
           # Si5351's MSOP-10 has 0.2 mm between its own pads and KiCad's 0.2 mm
           # default therefore fails on the part itself.  JLC does 0.127 mm.
           '\t(setup\n%s\n\t\t(pad_to_mask_clearance 0)\n'
           '\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n'
           '\t(net 0 "")\n%s\n%s\n)\n' % (lay, stack, nets, body))
    return txt, placed, bad


if __name__ == "__main__":
    txt, placed, bad = render()
    open(os.path.join(ROOT, "GPSDO-PYNQ-Z2.kicad_pcb"), "w", encoding="utf-8").write(txt)
    print("placed %d parts" % len(placed))
    if bad:
        print("OVERLAPS: %d" % len(bad))
        for a, b in bad[:25]:
            print("   %s <-> %s" % (a, b))
    else:
        print("no courtyard overlaps")
