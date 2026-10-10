"""Emit the whole board: 4-layer stackup, every part placed, ground planes.

Stackup, and why:

    L1  F.Cu      every component, and each channel's own short front-end runs
    L2  In1.Cu    solid GND, unbroken
    L3  In2.Cu    the fourteen helper-clock branches, the twenty-five beat and
                  pps returns to the socket, and the board-level buses that
                  the margins carry (I2C, +3V3_D, +15V_HTR, the three heater
                  drains, HTR_DRIVE, ONEWIRE, +5V_HDR)
    L4  B.Cu      solid GND

Round 15 wrote "the helper branches and NOTHING else" for L3, and round 18 let
the maze router onto it because the returns would not fit on L1; the docstring
was not updated and three reviews in round 28 caught it.  What is still true:
the helper branches are the only fast signals that go anywhere; burying them on
L3 between two ground planes makes them stripline, so they cannot couple into a
10 MHz front end on L1; and the front ends stay on L1 as short microstrip over
the L2 plane, local to their own tile.  What is not: L3 is not a private layer.
The nets that share it with the helper are DC (rails, HTR_DRIVE), slow (I2C,
1-Wire), or edges that are CAUSED by the helper (a beat is FF2's output, so it
moves a few ns after a helper edge and ~95 ns before the next one) or arrive
once a second (pps).  Round 28 scanned the finished copper: the closest
parallel runs are HCLK_07 beside BEAT_09 for 14.5 mm at 0.25 mm, and
HELPER_CLK beside HTR_DRIVE for 33 mm at 0.73 mm.  Neither can move a sampling
edge.  A keep-out that gives the helper branches their own corridor is the
right thing for a Rev B router and is not attempted here.

Rev B (REVB_CHANGES item 5, decided 2026-10-09): B.Cu is a +3V3_A PLANE.
Rev A had none -- "trading a power plane for a second ground reference is the
right way round for a board whose product is timing" -- and rev A then showed
the cost: 109 mV lost in the rail's tracks, and one channel's state moving its
neighbours 1-3 ps through the shared rail (r45 T1, O7).  Rev A's B.Cu carried
no tracks, only that second GND pour, so the plane costs no routing room.
In1 stays a solid GND plane under F.Cu.  Every +3V3_A pad reaches the plane
through its own via (the same search that gives every GND pad its via), the
gutter rails and the two margin spines are gone, and the router leaves
+3V3_A alone as it leaves GND.
"""
import os, sys, math, re, hashlib
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
import labels as LB         # every word the board prints on itself
import design as D          # REV and DATE for the silkscreen
import jlc as J             # the design rules, and JLCPCB's own minimums
from sexp import parse, kids, kid, val, head

ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "gen"))
import kicad_env                                    # noqa: E402
KFP = kicad_env.FOOTPRINTS                          # KiCad 10 (REVB item 14)
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


SILK_GFX = ("fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly")


def _fatten_silk(node):
    """Raise every silkscreen stroke in a footprint to JLCPCB's minimum.

    Round 29.  KiCad's stock footprints draw their outlines at 0.12 mm.
    JLCPCB's published minimum silkscreen width is 6 mil = 0.1524, and no
    KiCad DRC rule looks at a GRAPHIC line's width -- `min_text_thickness`
    only covers text -- so 458 footprints' worth of under-width ink passed
    every check this project runs and would have been either thinned or
    dropped on the panel.  Fixing it here rather than in the library means it
    applies to the stock footprints too, which are not ours to edit.
    """
    for c in node:
        if not isinstance(c, list):
            continue
        if head(c) in SILK_GFX:
            lyr = kid(c, "layer")
            if lyr and val(lyr).endswith(".SilkS"):
                for st in kids(c, "stroke"):
                    for w in kids(st, "width"):
                        if float(val(w, 1)) < J.SILK_LINE_MIN:
                            w[1] = ("atom", "%g" % J.SILK_LINE_MIN)
        _fatten_silk(c)


_fpcache = {}
def footprint(libdir, name, ref, value, x, y, rot, layer, pads, numof,
              refat=None, refsize=None, reflayer=None):
    """refat: (lx, ly) for the reference designator in the FOOTPRINT's own
    frame -- KiCad rotates it with the footprint, which is exactly what makes
    a tile's labels come out the same way round on both sides of the board.
    reflayer: move the reference off the silkscreen entirely (to F.Fab) when
    nothing on the board has room for it."""
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
    # Every item INSIDE the footprint gets its own uuid too.  The library's
    # are the same in every copy (97 of them, on 1491 items), and KiCad 10's
    # solder-mask check keys apertures by uuid: with all nineteen U.FL mask
    # rectangles sharing one, it reported J3004's as bridging a track of
    # J2005's tap 125 mm away (2026-10-09).  Rev A's board had the same 65.
    def _reuid(n):
        for c in n:
            if isinstance(c, list):
                if head(c) == "uuid":
                    c[1] = S(uid("fpi", ref, val(c)))
                else:
                    _reuid(c)
    for c in node[5:]:
        if isinstance(c, list):
            _reuid(c)
    _fatten_silk(node)
    for prop in kids(node, "property"):
        if val(prop) == "Reference":
            prop[2] = S(ref)
            # Round 28 shrank this to 0.6 mm so a five-character designator
            # would fit across an 0805.  0.6 is below JLCPCB's 0.8 mm minimum
            # printable height, and the DRC said so 199 times (its per-rule
            # report limit -- the real count was every reference on the
            # board).  0.8 it is, and the designators are placed rather than
            # left wherever the library happened to put them; see refpos().
            sz = refsize if refsize else 0.8
            for eff in kids(prop, "effects"):
                for fnt in kids(eff, "font"):
                    for s in kids(fnt, "size"):
                        s[1] = s[2] = ("atom", "%g" % sz)
                    for th in kids(fnt, "thickness"):
                        th[1] = ("atom", "0.16")
            if refat is not None:
                for a in kids(prop, "at"):
                    a[1] = ("atom", "%g" % round(refat[0], 3))
                    a[2] = ("atom", "%g" % round(refat[1], 3))
                    if len(a) > 3:
                        a[3] = ("atom", "0")
            if reflayer:
                for l in kids(prop, "layer"):
                    l[1] = S(reflayer)
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


def pour_keepout(layer, poly, tag):
    """A rule area that keeps the copper POUR out and nothing else."""
    pts = A("pts", *[A("xy", round(px, 3), round(py, 3)) for px, py in poly])
    return ser(A("zone", A("net", 0), A("net_name", S("")),
                 A("layers", S(layer)), A("uuid", S(uid("k", tag, layer))),
                 A("name", S(tag)), A("hatch", "edge", 0.5),
                 A("connect_pads", A("clearance", 0)),
                 A("min_thickness", 0.25), A("filled_areas_thickness", "no"),
                 A("keepout", A("tracks", "allowed"), A("vias", "allowed"),
                   A("pads", "allowed"), A("copperpour", "not_allowed"),
                   A("footprints", "allowed")),
                 A("fill", A("thermal_gap", 0.5), A("thermal_bridge_width", 0.5)),
                 A("polygon", pts)), 1)


def zone(net_no, net_name, layer, poly, tag, solid=False):
    pts = A("pts", *[A("xy", px, py) for px, py in poly])
    return ser(A("zone", A("net", net_no), A("net_name", S(net_name)),
                 A("layers", S(layer)) if isinstance(layer, str) else layer,
                 A("uuid", S(uid("z", tag, layer))), A("name", S(tag)),
                 A("hatch", "edge", 0.5),
                 (A("connect_pads", "yes", A("clearance", 0.25)) if solid
                  else A("connect_pads", A("clearance", 0.25))),
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
        # right behind the five screw terminals it serves
        # Starts at y = 21 now: the five probe cells and their two buses
        # occupy y 8..19 and the auto-placer must not sit on them.
        # 21, and NOT the 23 round 29 first tried to make silkscreen room.
        # Only three parts land here -- D6001, R6001 and TP6001, the other
        # nineteen 6xxx references being hand-placed -- and moving those three
        # down by 2 mm changed which way the router took U6001's I2C_SDA pin
        # out.  In the working board it leaves EAST, one straight 75 mm run at
        # y = 27 that also carries the helper's I2C_SDA to the left margin
        # lane; with the parts 2 mm lower the short way west opened up, U6001
        # took it, and the helper's own piece was left with no corridor and no
        # connection.  Two millimetres of silkscreen is not worth that.
        "probes": (12.0, 21.0, 78.0, 34.0, "1-WIRE"),
        # Round 15 leaves only the bottom band for these two: the channel
        # array now fills everything between the top band and the fan-in.
        "house":  (40.0, 169.0, 104.0, 178.0, "HOUSEKEEPING"),
    }

# Parts whose position is about USING the board, not about routing it.
# Cabled connectors go on an EDGE; thermometers go where the heat is.
def hand_placed(G):
    """Parts whose position is about USING the board, not routing it.

    Round 15 leaves two 10 mm margins outside the 1 pps jacks and a band across
    the top; between them they hold every cabled connector, the eight
    thermometers and eleven of the twenty-four heaters.  The other thirteen
    heaters go INSIDE the tiles -- see build(), which has the tile transform.
    """
    d = {}
    # Five 1-Wire screw terminals along the top edge, entry facing outward,
    # each with its own two 47R series resistors directly underneath it.
    #
    # They used to be auto-gridded with the rest of the 1-Wire block, which put
    # all ten in one row alternating ONEWIRE, +3V3_D, ONEWIRE, +3V3_D...: two
    # buses interleaved pad by pad, so neither could run straight without
    # crossing the other's pads, and eight of round 18's remaining twenty
    # connections were that.  A probe is a cell, like a channel is a cell.
    #
    # Both resistors at rot 90, which puts pad 1 -- the bus end -- at the TOP
    # and pad 2 -- the screw-terminal end -- at the bottom, so each one drops
    # straight down its own pin with nothing in the way.  The two buses then
    # run on different layers at different heights and never meet: ONEWIRE
    # along the data pads on F.Cu, +3V3_D along the power pads on In2.
    # G.PROBE_X, not a literal: the hand-routed spurs out of these five
    # terminals are written from the same list.  Round 29 moved the row 3 mm
    # right, to clear the top-left M3 hole it was the first round to drill.
    for i, jx in enumerate(G.PROBE_X):
        d["J600%d" % (i + 1)] = (jx, 8.0, 180)
        # Clear of the terminal block, which is 12 x 10 mm and therefore
        # reaches down to y = 13 even though its pins are at 8.
        d["R60%02d" % (2 * i + 2)] = (jx - 3.5, 14.6, 90)    # +3V3_D, 1206
        d["R60%02d" % (2 * i + 3)] = (jx, 18.0, 90)          # ONEWIRE, 0805
    # Debug header lies down in the bottom-left corner, clear of the socket.
    # Debug header at rot 270, not 90, and shifted so pin 1 sits at the far
    # (east) end.  At rot 90 its GROUND row sat at y = 171.46 -- between the
    # signal row and the rest of the board -- so all seven signals had to be
    # reached from the 6 mm strip between the connector and the bottom edge,
    # and three of them could not be.  Turned round, the ground row faces the
    # edge and the signal row is open to the whole band above it.
    d["J5001"] = (36.86, G.BH - 6.0, 270)

    # The DS2482 and the heater DAC, placed rather than auto-gridded.  Each is
    # an eight- or six-pin part whose supply pin, ferrite bead and two
    # capacitors are one 4 mm net, and the auto-grid scattered those four
    # terminals round three sides of the package -- the same failure the eight
    # thermometer stacks had.  Laid out with every V+ pad in one column, the
    # net is two straight tracks; see build().
    d["U6001"] = (16.0, 25.0, 0)          # DS2482-100, SOIC-8
    d["R6051"] = (13.53, 20.3, 270)       # rev B: R6051 (4R7) where FB6001 was      # bead above pin 1
    d["C6001"] = (10.5, 25.635, 180)      # both caps to the left, V+ inward,
    d["C6002"] = (10.5, 28.2, 180)        # below R2014's 2010 footprint
    d["U5009"] = (46.0, 173.0, 0)         # MCP4725, SOT-23-6
    d["R5059"] = (44.86, 177.0, 90)       # rev B: R5059 (4R7) where FB5009 was      # bead below pin 3
    d["C5017"] = (41.5, 173.95, 180)
    d["C5018"] = (41.5, 171.0, 180)
    # The three heater pass FETs, each at the centroid of the eight heaters it
    # drives.  Round 18 regrouped the heaters geographically -- left column,
    # right column, the ring -- so a FET beside its own group turns a drain net
    # that crossed the whole board three times into a local one.  They are also
    # about as far apart as this board allows, which is the other reason there
    # are three of them: 0.8 W each instead of 2.4 W in one package, and out in
    # the margins that 0.8 W is heat where the ring heaters want it anyway.
    # Each sits at the end of its own group's trunk: the two column FETs in the
    # clear band under the last tile row, at the foot of the column of heaters
    # they drive, and the ring FET in the right-hand margin on the ring's own
    # lane.  Three corners of the board, which is the other half of the reason
    # there are three of them.
    # Q2001 cannot do the same: unit 13's own heater sits at y = 158.4, 1.7 mm
    # above where its tab would have to go.  Its gate keeps a 1.7 mm stub, which
    # costs nothing because the trunk is already on F.Cu at that x.
    d["Q2001"] = (70.9, 163.3 if os.environ.get("R13UP") else 165.0)
    # Q2002 sits 1.7 mm higher than the obvious place, so that its GATE pad
    # lands exactly on the y = 161 gate trunk.  Everything here is inside the
    # band where twenty-five returns fan into the socket, and every extra
    # millimetre of copper in that band costs a return: reaching a gate 1.7 mm
    # BELOW the trunk cost five of them, and moving the FET to the head of its
    # column instead -- where the gate faces the empty top band -- cost four.
    # On the trunk line the connection costs one via and no new lane at all,
    # because the last 2.5 mm of the trunk simply changes layer.  Round 19.
    d["Q2002"] = (134.1, 163.3)          # foot of the right tile column
    d["Q2003"] = (G.BW - 6.5, 33.0)      # right margin, on the ring lane

    # Eight thermometers, four down each 10 mm margin.  Spread is the whole
    # point -- a sensor tells you about the copper it sits on, and what we care
    # about is the gradient across the array, not its mean.
    # The right-hand three are MIRRORED, not copied: rot 180, and their support
    # stack flipped with them.  Round 19 -- the left margin routed and the
    # right one did not, and the reason was that the two were never mirror
    # images at all.  A TMP1075 has SDA and SCL on pins 1-2 and V+ and the
    # address straps on 5-8, so at rot 0 in the LEFT margin its I2C pins face
    # outward, into the clear band at the board edge; in the RIGHT margin the
    # same rotation faces them inward, into the 2.4 mm gap between the
    # package's own two rows of pads -- which the part's own V+ track runs
    # down, with the +3V3_A rail at x = 194.2 sealing the only other way out.
    # U5002 at y = 48 escaped only because that rail starts at y = 62.7;
    # U5004 and U5006 were walled in on all four sides.
    temps, tmirror = {}, {}
    for i, sy in enumerate((48.0, 90.0, 132.0)):
        temps["U500%d" % (2 * i + 1)] = (6.5, sy)
        temps["U500%d" % (2 * i + 2)] = (G.BW - 6.5, sy)
        tmirror["U500%d" % (2 * i + 2)] = True
    # One ON the helper, between its two jacks and directly above the block.
    # The margins tell you about the gradient across the array; this one tells
    # you about the thing whose drift actually moves the measurement, and
    # round 15 left it out.
    # Rev B (item 20, Jason 2026-10-09: option A, a thermostat on the 24
    # heaters as they are): it moves BESIDE THE FAN-OUT, between the two
    # LMK1C1108s on the block's right side, as the thermostat's sensor --
    # the one thing whose temperature every channel's timing shares.
    # (2026-10-09 afternoon) at the far end of U3005, local (96.5, -7.6):
    # between the LMKs is where their outputs' 33Rs now fan out.
    temps["U5007"] = (G.XC - 0.2 + 7.6, 40.0 + 96.5)
    temps["U5008"] = (6.5, 168.0)   # a fourth down the left margin;
                                    # at (70, BH-6) its support stack ran
                                    # off the bottom edge
    d.update(temps)
    # A thermometer's bead and capacitors travel WITH it, in the same margin
    # strip -- but lying ACROSS the strip, not stood on end, and turned so that
    # every V+ pad is on the same side.  Round 17 had them vertical with the
    # bead's V+ pad pointing away from the part and each capacitor's ground pad
    # pointing towards it, which put four terminals of one 4 mm net on three
    # different sides of a SOIC-8.  Nothing could route it, and nothing did:
    # thirty of the 141 remaining connections were eight copies of this.
    #
    # Turned this way all three V+ pads land on x = centre - 0.95, and the
    # column between the SOIC's two rows of pins is free copper, so V+ is one
    # straight track down the middle of the part plus a hop over the top to
    # pin 8.  See the hand routes in build().
    # s = +1 for a left-margin stack, -1 for a mirrored right-margin one.  Every
    # offset is multiplied by it, so the two sides are exact reflections and
    # every clearance that works on one works on the other by construction.
    for i, (ref, (sx, sy)) in enumerate(sorted(temps.items())):
        s = -1.0 if tmirror.get(ref) else 1.0
        d[ref] = (sx, sy, 180 if s < 0 else 0)
        rf = 0 if s < 0 else 180
        d["R505%d" % (i + 1)] = (sx, sy - s * 5.0, rf)     # rev B: was FB500n
        d["C50%02d" % (2 * i + 1)] = (sx, sy + s * 4.2, 180 - rf)
        d["C50%02d" % (2 * i + 2)] = (sx, sy + s * 7.0, 180 - rf)

    # Eleven heaters ring the array from the margins and the bottom band; the
    # other thirteen sit one per tile (see build()).  Margin heaters go in the
    # gaps the thermometer stacks leave.
    # The LEFT margin ones are turned round.  A 2010 lying across a 10 mm margin
    # puts one pad at x = 4.19 and the other at 8.81, and which is which decides
    # whether the +15 V lane or the drain lane has to cross the other to reach
    # it.  Both rails come DOWN THE MARGIN from the top, so both want their pad
    # on the same side: the inboard one.  On the right margin pin 1 is already
    # inboard; on the left it is not, so those four turn 180 degrees.  Round 18.
    ring = [(6.5, y, 180) for y in (22.0, 68.0, 110.0, 150.0)]
    ring += [(G.BW - 6.5, y, 0) for y in (22.0, 68.0, 110.0, 150.0)]
    # The last three go BELOW the array, and they are set on the tile columns
    # rather than anywhere convenient: a 2010 lying across x = 70.9 has its two
    # pads at 68.59 and 73.21, which is exactly where the left column's drain
    # and +15 V trunks already run, so it costs no copper at all to reach.  The
    # same at 134.1 for the right column, and R2022 on the centre line under
    # the helper, which is the one place the array has no heater near it.
    ring += [(G.XC, 156.0, 0),              # R2022, centre, under the helper
             (70.9, G.BH - 6.0, 180),       # R2023, astride the left columns
             (134.1, 157.0, 0)]             # R2024, astride the right columns
    for i, (hx, hy, hr) in enumerate(ring):
        d["R20%02d" % (14 + i)] = (hx, hy, hr)
    # Rev B item 19: the three rail taps (+5V_HDR, +3V3_A, +3V3_D), each a 1k
    # above its U.FL, in the open strip under unit 13 -- the far end of
    # +3V3_A, which enters at the top right.
    for i, tx in enumerate((80.0, 88.0, 96.0)):
        d["R20%02d" % (27 + i)] = (tx, 165.0, 90)
        d["J200%d" % (4 + i)] = (tx, 170.0, 0)
    return d


def is_heater(ref):
    """R2001-R2013 (one per channel tile) and R2014-R2024 (the ring)."""
    import re
    m = re.match(r"^R20(\d\d)$", ref)
    return bool(m) and 1 <= int(m.group(1)) <= 24


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
    # Round 29: footprints are SERIALISED LAST.  A reference designator can
    # only be positioned once everything else on the silkscreen exists --
    # every other designator, every marker letter, every legend line -- and
    # the designator lives inside the footprint's own s-expression.  So put()
    # reserves a slot in `out` and records what goes in it, and the very end
    # of build() fills all 458 of them in.
    pending = []
    fpof = {}          # placed ref -> (library dir, footprint name)

    def put(ref, x, y, rot=0, layer="F.Cu"):
        fp = fps.get(ref)
        if not fp:
            return
        lib, name = fp.split(":", 1)
        d = LOCAL_FP if lib == "GPSDO-PYNQ-Z2" else os.path.join(KFP, lib + ".pretty")
        out.append(None)
        pending.append((len(out) - 1, d, name, ref, vals.get(ref, ""),
                        round(x, 3), round(y, 3), rot, layer,
                        nets.get(ref, {})))
        placed[ref] = (x, y, rot)
        boxes[ref] = P.box_at(d, name, x, y, rot)
        fpof[ref] = (d, name)

    def put_raw(name, ref, x, y, rot=0):
        """A footprint that is not a part: it has no netlist entry, no pads
        with nets, no BOM line.  The mounting holes are the only users."""
        out.append(None)
        pending.append((len(out) - 1, LOCAL_FP, name, ref, "", round(x, 3),
                        round(y, 3), rot, "F.Cu", {}))
        placed[ref] = (x, y, rot)
        boxes[ref] = P.box_at(LOCAL_FP, name, x, y, rot)
        fpof[ref] = (LOCAL_FP, name)

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
    # ---- REAL mounting holes ---------------------------------------------
    # Round 29.  Six captions reading "M3 standoff" and not one hole: put()
    # looked "H1".."H6" up in the netlist, no sheet declares a mounting-hole
    # symbol, and put() returns quietly when it finds nothing.  These go down
    # BEFORE any routing, so their keep-out is an obstacle to the router and
    # to the ground-via search like any other pad, and their courtyard is the
    # standoff's keep-out so the existing overlap check tests the clearance.
    for i, ((mx, my), kind, note) in enumerate(G.MOUNT):
        put_raw("MountingHole_M3_NPTH" if kind == "hole"
                else "MountingSlot_M3_NPTH", "MH%d" % (i + 1), mx, my)
        out.append(text(mx + 5.0, my + 5.5, note.split(" - ")[0].split(".")[0],
                        "Cmts.User", 1.0, 0.15))

    # ---- the socket -------------------------------------------------------
    px, py = G.hdr_pin(1)
    put("J4001", px, py, 0, "B.Cu")

    # Every header pin is named on the silkscreen; see silkscreen() below for
    # where.  The short name is the part that belongs with the header map.
    def _short(net):
        if net == "+3V3_HOST":
            # Round 21: pins 1 and 17 are the PYNQ's own 3V3 and this board
            # leaves them OPEN -- it makes its own 3.3 V from the 5 V pins and
            # never loads the host regulator.  Labelling them "3V3" invited
            # someone to probe them and believe the rail was ours.
            return "nc"
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

    # ---- the thirteen channel tiles ---------------------------------------
    # Round 15: each unit is a horizontal strip pointing at the helper on the
    # vertical centre line.  Left-hand units are the whole tile at rot 90 (its
    # chain, which runs +y locally, then runs to the RIGHT); right-hand units
    # at rot 270.  Either way the 10 MHz signal flows inward and meets the
    # sampling clock where it is generated.
    import math as _m

    def xf(u):
        ox, oy, urot = G.unit_origin(u)
        a = _m.radians(-urot)
        ca, sa = int(round(_m.cos(a))), int(round(_m.sin(a)))

        def f(lx, ly, off=(0.0, 0.0)):
            lx, ly = lx + off[0], ly + off[1]
            return (ox + lx * ca - ly * sa, oy + lx * sa + ly * ca)
        return f, urot

    byunit = {}
    for ref in fps:
        u, slot = unit_of(ref)
        if u:
            byunit.setdefault(u, {})[slot] = ref
    TILE = T.tile()
    for u in sorted(byunit):
        f, urot = xf(u)
        for slot, ref in byunit[u].items():
            if slot not in TILE:
                out.append(text(4, 2, "UNPLACED %s" % ref, "Cmts.User", 1.0))
                continue
            dx, dy, prot = TILE[slot]
            x, y = f(dx, dy)
            put(ref, x, y, (prot + urot) % 360)

    for tag, ref in (("HIN", "J3002"), ("HO", "J3001")):
        put(ref, *G.HELPER_SMA[tag])

    # ---- the tile's own tracks, stamped out thirteen times ----------------
    tracks = []          # (x0, y0, x1, y1, layer, netname, width)
    tile_vias = []
    in2_term = {}

    def netof(u, slot, pad):
        r = byunit.get(u, {}).get(slot)
        return nets.get(r, {}).get(pad) if r else None

    def run(u, spec, off=(0.0, 0.0)):
        (slot, pad), w, pts = spec
        nm = netof(u, slot, pad)
        if not nm or nm.startswith("unconnected-"):
            return
        f, _ = xf(u)
        for i in range(len(pts) - 1):
            p0, p1 = f(*pts[i], off=off), f(*pts[i + 1], off=off)
            if p0 != p1:
                tracks.append(p0 + p1 + ("F.Cu", nm, w))

    def escape(u, slot, pad, vx, vy, ey):
        """In2 via plus the stub that takes it clear of the tile.

        All three of a unit's In2 nets come out on the same line just past its
        inner end, so every unit hands them over in the same place."""
        nm = netof(u, slot, pad)
        if not nm:
            return
        f, _ = xf(u)
        vp, ep = f(vx, vy), f(vx, ey)
        sx = round(ep[0] / MZ.PITCH) * MZ.PITCH
        sy = round(ep[1] / MZ.PITCH) * MZ.PITCH
        tile_vias.append((vp[0], vp[1], nm))
        tracks.append(vp + ep + ("In2.Cu", nm, T.W_SIG))
        if (sx, sy) != ep:
            tracks.append(ep + (sx, sy) + ("In2.Cu", nm, T.W_SIG))
        in2_term.setdefault(nm, []).append((sx, sy))

    railends = {}
    gutters = []
    # Rev B: NOHAND=1 leaves out rev A's hand-drawn tile and helper tracks,
    # which no longer fit the parts (a placement preview).
    _NOHAND = bool(os.environ.get("NOHAND"))
    for u in sorted(byunit):
        f, urot = xf(u)
        for spec in ([] if _NOHAND else T.routes_10m(T.RAIL_HEAD_PPS)):
            run(u, spec)
        if byunit[u].get("U04") and not _NOHAND:
            for spec in T.routes_pps():
                run(u, spec, off=T.PPS_OFFSET)
        for slot, pad, vx, vy, ey in ([] if _NOHAND else T.VIAS_10M):
            escape(u, slot, pad, vx, vy, ey)
        for slot, pad, vx, vy in ([] if _NOHAND else T.PLAIN_VIAS_10M):
            nm = netof(u, slot, pad)
            if nm:
                tile_vias.append(f(vx, vy) + (nm,))
        if byunit[u].get("U04") and not _NOHAND:
            for slot, pad, vx, vy, ey in T.VIAS_PPS:
                escape(u, slot, pad, vx, vy, ey)
        railends.setdefault(urot, []).append(f(T.RAIL_10M, T.RAIL_HEAD_PPS))
        # Rev B: the rail is gone (the B.Cu plane), but where it ran stays
        # closed to the plane-via search -- see gutter_clear().
        gutters.append(f(T.RAIL_10M, T.RAIL_HEAD_PPS) + f(T.RAIL_10M, T.RAIL_FOOT))
        # One heater per tile, in the empty strip down the tile's outboard
        # side: no ground pad lives there, so it costs nothing, and it puts a
        # heater beside every channel instead of only around the outside.
        hr = "R20%02d" % u
        if hr in fps:
            # Unit 13's heater sits 1.7 mm nearer its own row than the rest,
            # which frees the strip below it for Q2001's tab -- and that in turn
            # lets Q2001's GATE pad land on the y = 161 trunk, the trick that
            # already freed Q2002 (round 19.5).  Nothing thermal depends on the
            # 1.7 mm: the copper's spreading length here is 40-50 mm.  Round 20.
            hx, hy = f(-5.0 if (u == 13 and os.environ.get("R13UP")) else -6.7,
                       28.0)
            put(hr, hx, hy, (90 + urot) % 360)

    # Rev A ran one +3V3_A spine per side up the margin, picking up every
    # unit's gutter rail.  Rev B: the B.Cu plane (item 5) replaces both.

    # ---- the helper oscillator and its fan-out ---------------------------
    # At rot 270 so its chain, which runs +x locally, runs DOWN the centre
    # line.  The source end sits at the top beside its own two SMAs; the four
    # second-stage buffers stay clustered (round 10) rather than being spread
    # out beside the rows they feed -- a buffer's threshold moves 5-10 ps/degC
    # against 0.7 ps per 100 mm per 10 degC for the trace, so thermal
    # clustering beats branch shortening by an order of magnitude.
    # 1.5 mm east of where round 15 put it, which is round 19's last fix.  The
    # thirteen left-hand returns and the twelve right-hand ones come down two
    # corridors either side of this block: the left one was 4.5 mm wide for 13
    # wires and the right one 12 mm for 12, and the odd one out -- BEAT_00,
    # unit 1's, the outermost of the left fan because its source is highest up
    # the board -- had nowhere to go.  Moving the block east lends the left
    # corridor 1.5 mm of the right one's surplus and every return routes.
    # Measured, not guessed.  On the 205 mm board: 0 mm left two unrouted,
    # 1.5 mm left none, 3.0 mm left three -- by then the right corridor is the
    # tight one.  Re-measured on the 207 mm board of round 20, where the band
    # itself is 1 mm wider a side, 2.0 mm total is the best of 1.5, 2.0 and 2.5.
    HX, HY = G.XC - 0.2 + float(os.environ.get("HSHIFT", "0")), 40.0
                                  # spans x 89.0..108.6 inside the band,
                                  # y 35..152 alongside the thirteen rows

    def hf(lx, ly):
        return (HX - ly, HY + lx)

    for ref, (dx, dy, rot) in sorted(H.PARTS.items()):
        put(ref, *hf(dx, dy), rot=(rot + 270) % 360)

    def hnet(slot, pad):
        return nets.get(slot, {}).get(pad)

    _hroutes = H.routes()        # rev B: also fills IN2_ROUTES, VIAS, LOCAL_VIAS
    for lst, lyr in ((_hroutes, "F.Cu"), (H.IN2_ROUTES, "In2.Cu")):
        for (slot, pad), w, pts in lst:
            nm = hnet(slot, pad)
            if not nm or nm.startswith("unconnected-"):
                continue
            for i in range(len(pts) - 1):
                p0, p1 = hf(*pts[i]), hf(*pts[i + 1])
                if p0 != p1:
                    tracks.append(p0 + p1 + (lyr, nm, w))
    # No escape stubs here.  The fourteen branch vias sit in a neat column 2.4 mm
    # apart down the block's edge, already in the open lane; a stub sideways
    # only walked into the left-hand units' hand-off column 1.8 mm away.
    # Rev B: hops inside the block, with no stub to the edge.
    for slot, pad, vx, vy in H.LOCAL_VIAS:
        nm = hnet(slot, pad)
        if nm:
            tile_vias.append(hf(vx, vy) + (nm,))
    for slot, pad, vx, vy in H.VIAS:
        nm = hnet(slot, pad)
        if not nm:
            continue
        vp = hf(vx, vy)
        tile_vias.append((vp[0], vp[1], nm))
        if nm == "HELPER_SRC":          # hand-routed inside the block
            continue
        # The fourteen branch vias already sit on the block's left edge, in the
        # open lane.  The two helper-SMA vias do not -- they are 9 and 15 mm
        # INSIDE it, behind the block's own ground vias -- so they get a stub
        # out to the edge, which is the only way anything can reach them.
        ex = HX - 7.6 - 0.5
        if vp[0] > ex + 0.5:
            sx = round(ex / MZ.PITCH) * MZ.PITCH
            sy = round(vp[1] / MZ.PITCH) * MZ.PITCH
            tracks.append(vp + (sx, sy) + ("In2.Cu", nm, T.W_SIG))
            in2_term.setdefault(nm, []).append((sx, sy))
        else:
            in2_term.setdefault(nm, []).append(vp)
    # Rev B: the right-hand column's branches are drawn out to the corridor
    # beside those tiles on In2 (helper.EAST); the router starts where they end.
    for slot, pad, ex_, ey_ in H.EDGE_TERMS:
        nm = hnet(slot, pad)
        if not nm:
            continue
        ep = hf(ex_, ey_)
        sx = round(ep[0] / MZ.PITCH) * MZ.PITCH
        sy = round(ep[1] / MZ.PITCH) * MZ.PITCH
        if abs(sx - ep[0]) + abs(sy - ep[1]) > 1e-6:
            tracks.append(ep + (sx, sy) + ("In2.Cu", nm, T.W_SIG))
        in2_term.setdefault(nm, []).append((sx, sy))

    # ---- the power input block -------------------------------------------
    for ref, (px, py, prot) in sorted(PW.PARTS.items()):
        put(ref, *PW.place(px, py), rot=(prot + PW.ROT) % 360)
    for lst, lyr in ((PW.routes(), "F.Cu"), (PW.IN2_ROUTES, "In2.Cu")):
        for (slot, pad), w, pts in lst:
            nm = nets.get(slot, {}).get(pad)
            if not nm or nm.startswith("unconnected-"):
                continue
            for i in range(len(pts) - 1):
                p0, p1 = PW.place(*pts[i]), PW.place(*pts[i + 1])
                if p0 != p1:
                    tracks.append(p0 + p1 + (lyr, nm, w))
    # NOTE for anyone adding In2 copper in this block: the six board-level
    # links (I2C_SCL, I2C_SDA, Q2003-D, HTR_DRIVE, +3V3_D, +15V_HTR) run the
    # whole width of the board on In2 at y = 25.0 .. 29.0, straight through
    # the power block, and are laid AFTER this by spine().  In2 here must stay
    # above y = 24 or below y = 30, or the links hop to F.Cu and cannot land
    # (round 28's first interlock layout crossed all six and dropped five).
    for slot, pad, vx, vy in PW.VIAS:                  # round 28: LDO_EN
        nm = nets.get(slot, {}).get(pad)
        if nm:
            vp = PW.place(vx, vy)
            tile_vias.append((vp[0], vp[1], nm))

    # ---- hand-placed: edges and hot spots ---------------------------------
    for ref, xy in sorted(hand_placed(G).items()):
        put(ref, xy[0], xy[1], xy[2] if len(xy) > 2 else 0)
    # ---- everything else, in blocks ---------------------------------------
    byblock = {}
    for ref in fps:
        b = block_of(ref)
        if b and ref not in placed:
            byblock.setdefault(b, []).append(ref)
    overflow = []
    blockrefs = {}                 # block -> the refs that actually landed
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
            blockrefs.setdefault(b, []).append(r)
            cx += w + 1.6
            rowh = max(rowh, h)
        # The label and the box round this region are drawn by silkscreen(),
        # from the parts that actually landed here rather than from the
        # packer's nominal rectangle -- which is 4 mm bigger than its contents
        # in every direction and used to be drawn on Cmts.User, where nobody
        # holding the board can see it.
    if overflow:
        out.append(text(4.0, 99.0, "OVERFLOW: %d parts did not fit their block"
                        % len(overflow), "Cmts.User", 2.0, 0.3))
        import sys as _s
        print("OVERFLOW:", overflow, file=_s.stderr)

    # ---- every SMD GND pad gets a stub and a via down to the plane ---------
    # This is what makes the ratsnest readable: with ground already connected,
    # what is left on screen is only the signals.  Through-hole GND pads are
    # skipped -- their own barrel already reaches every layer.
    import math as _m
    allpads = []
    for ref, (px, py, prot) in sorted(placed.items()):
        d, name = fpof[ref]
        _n0 = len(allpads)
        for pn, ax, ay, tht, hd, prect in P.pads(d, name, px, py, prot):
            allpads.append((ref, pn, ax, ay, tht, nets.get(ref, {}).get(pn), hd,
                            prect))
        # Every footprint must yield at least one pad.  Round 14's worst bug was
        # a regex in place.pads() that silently matched nothing for our own SMA
        # footprint, which writes its pads on one line -- so all 27 jacks'
        # through-hole pads were invisible to every collision test on the board,
        # including the ground-via search, for four rounds.  A reader of that
        # code could not see it; this line would have.  It costs nothing and the
        # pad reader has grown two more optional fields since.
        assert len(allpads) > _n0, (
            "%s (%s) yielded NO pads -- place.pads() failed to parse %s"
            % (ref, name, os.path.join(d, name + ".kicad_mod")))

    gnd_no = numof["GND"]

    # ---- bond every duplicated pad number to itself -----------------------
    # SOT-223-3_TabPin2 declares pad "2" TWICE: the centre lead and the big
    # tab.  They are the same pin of the same device, but KiCad's connectivity
    # does NOT join two same-numbered pads across bare board -- it wants
    # copper, like any other pair.  Round 21 found Q2002's centre lead sitting
    # completely isolated on the finished board, with the tab 6.3 mm away
    # carrying the whole drain net: one unconnected item, and pure luck that
    # Q2001 and Q2003 had picked up a stub that happened to reach both.
    #
    # So bond them here rather than leaving it to the router, which has no
    # reason to know the two pads are the same thing.  The copper between a
    # tab and its own lead is the same net by definition, so a straight track
    # is always safe.  This is written against duplicate pad NUMBERS, not
    # against SOT-223, so any future tabbed package is covered too.
    _bypad = {}
    for ref, pn, ax, ay, tht, nname, hd, prect in allpads:
        _bypad.setdefault((ref, pn), []).append((ax, ay, nname))
    # ...but ONLY where the straight line is safe.  An SMA_Vertical_THT jack
    # declares its four shield pads all as pad "2", and a straight track
    # between two opposite ones runs clean through the centre pin.  So every
    # candidate bond is checked against every pad of a DIFFERENT net first,
    # and dropped if it does not clear.  Of 84 candidates on this board only a
    # handful are real tab-to-lead pairs; the rest are shield rings that are
    # already tied together by the ground pour and need nothing.
    def _seg_pad_gap(x0, y0, x1, y1, px, py, hw, hh):
        import math as _bm
        dx, dy = x1 - x0, y1 - y0
        L = dx * dx + dy * dy
        s = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L))
        cx, cy = x0 + s * dx, y0 + s * dy
        return _bm.hypot(max(0.0, abs(cx - px) - hw), max(0.0, abs(cy - py) - hh))

    _bonds, _skipped = 0, 0
    for (ref, pn), lst in sorted(_bypad.items()):
        if len(lst) < 2:
            continue
        nm = lst[0][2]
        if not nm or nm.startswith("unconnected-"):
            continue
        if nm == "GND":
            continue        # already tied together by the pour on three layers
        ax, ay, _ = lst[0]
        for bx, by, _ in lst[1:]:
            ok = True
            for oref, opn, ox, oy, otht, onm, ohd, oprect in allpads:
                if onm == nm:
                    continue
                ohw, ohh, oang = oprect
                if round(oang) % 180:
                    ohw, ohh = ohh, ohw
                if ohd:
                    ohw, ohh = max(ohw, ohd / 2.0), max(ohh, ohd / 2.0)
                if (_seg_pad_gap(ax, ay, bx, by, ox, oy, ohw, ohh)
                        < 0.15 + T.W_PWR / 2.0):
                    ok = False
                    break
            if ok:
                tracks.append((ax, ay, bx, by, "F.Cu", nm, T.W_PWR))
                _bonds += 1
            else:
                _skipped += 1
    import sys as _bs
    print("bonded %d duplicated pad pairs, skipped %d as unsafe"
          % (_bonds, _skipped), file=_bs.stderr)

    # ---- lane design aid --------------------------------------------------
    # With SPINEDUMP set, write out everything that exists BEFORE the ground
    # vias and the routers run -- every pad and every hand-laid track -- and
    # stop.  Choosing a distribution lane means asking "what is already in this
    # strip", and asking that against the FINISHED board gives the wrong answer:
    # most of what is in the way at the end is the router's own output, which
    # would have gone somewhere else had the lane been there first.
    # The two column drains get their own margin lane 2.2 mm inside the
    # +15 V one -- see LANES below for why that gap is wider than the rest.
    DRAIN_X = {"Net-(Q2001-D)": 6.4, "Net-(Q2002-D)": G.BW - 6.4}

    # ---- distribution lanes ----------------------------------------------
    # Nine nets have to reach every corner of this board: the two 3.3 V rails,
    # +15V_HTR, the three heater drains, I2C and 1-Wire.  Rounds 16 and 17 left
    # them to the maze router and it could not finish them; more rip-up passes
    # and thinner track did not move the number, because the obstacle is not
    # the search order.  It is that by the time the router sees them, F.Cu is
    # full of thirteen tiles and In2 is full of twenty-five returns.
    #
    # Look at the board BEFORE any of that is placed, though, and In2 is empty
    # exactly where a distribution net wants to be:
    #   - both 10 mm margins, x 1..11 and 194..204, clear from y 19 to 176;
    #   - the top band, y 19..35, clear right across;
    #   - the bottom band, y 157..169, clear right across;
    #   - and at every in-tile heater's own row, a clear run from the margin
    #     all the way in to its pads.
    # Every part on this board is SMD on F.Cu, so In2 in the margins has
    # nothing in it at all.  What fills those lanes by the end is the ground
    # vias and the router's own output -- and both of those AVOID EXISTING
    # TRACK.  So the lanes cost nothing if they are laid first.  That is the
    # same trick that makes the +3V3_A rail work inside a tile.
    #
    # Each lane is a trunk, not a finished net: it gets the copper to within a
    # couple of millimetres of every pad and leaves the last hop to the
    # multi-terminal pass, which is a job that router is good at and was never
    # being given.
    #
    # spine() refuses to lay anything that would not pass DRC.  Where a lane
    # crosses something already there it hops to F.Cu for a millimetre or two
    # and back; where it cannot, it drops that segment and says so.  A missing
    # segment costs ratsnest, which is honest.  The first attempt at this had
    # no such check, ran a link straight through the 1-Wire block, and produced
    # four DRC errors and six MORE unconnected items than it started with.
    W_LANE = 0.3
    # CLR is the margin the analytic checks keep BEYOND the copper itself.  It
    # is 0.15 while the rule kicad-cli enforces on this board is 0.2, and that
    # is deliberate: these checks are a filter in front of the DRC, not a
    # replacement for it, and 0.2 everywhere refuses so many candidate paths
    # that eight nets stop routing.  Measured, round 20: at 0.15 the board
    # comes out with zero violations; at 0.2 it comes out with eight fewer
    # connections and still zero violations.  The DRC is what decides, and it
    # is run on every build.
    #
    # VR is the real one.  A via is 0.6 mm across, so a track must stay
    # 0.3 + clearance from its centre -- and THAT was wrong until round 20,
    # written as a flat 0.45 which is 0.05 short.  It cost nothing for as long
    # as the grid happened to keep things further apart than the check did,
    # and fifteen clearance errors the moment the grid changed.
    CLR, VIA_R = 0.15, 0.3
    VIA_GROW = 0.15
    # Hole-to-hole.  A via drill is 0.3 mm; the board rule is 0.25 mm between
    # drills and JLCPCB's same-net via-to-hole figure is 0.254.  Round 28: the
    # grid had no notion of this at all, so two vias were drilled into
    # through-hole pads of their own net.  0.35 leaves 0.1 mm over the rule.
    HOLE_TO_HOLE = 0.35

    def NOVIA_R(hd):
        return (hd or 0.0) / 2.0 + 0.15 + HOLE_TO_HOLE
    # STRICTVIA turns on the two corrections round 20 found and could not yet
    # afford.  Off, the analytic checks are exactly what produced this board;
    # on, they are what the rules actually say.  See 20.4 in the write-up: the
    # corrected checks are RIGHT and they cost five to eight nets, because they
    # are now stricter than the GRID the router searches, and the two have to
    # be made to agree before either can be tightened alone.
    STRICT = bool(os.environ.get("STRICTVIA"))
    VR = VIA_R + (0.05 if STRICT else 0.0)

    def _pdist(px, py, x0, y0, x1, y1):
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 == 0 else max(0.0, min(
            1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
        return _m.hypot(px - (x0 + u * dx), py - (y0 + u * dy))

    def pt_why(px, py, lyr, nm, w, grow=0.0):
        """Same test as pt_clear, but says WHAT is in the way."""
        for _r, _p, ax, ay, tht, net, hd, rc in allpads:
            if net == nm or not (tht or lyr == "F.Cu"):
                continue
            if P.pad_gap(px, py, ax, ay, rc) < w / 2.0 + 0.2 + grow:
                return "pad %s.%s[%s]" % (_r, _p, net)
        for a, b, c, d, l, n2, w2 in tracks:
            if n2 == nm or l != lyr:
                continue
            if _pdist(px, py, a, b, c, d) < w / 2.0 + w2 / 2.0 + 0.2 + grow:
                return "trk %s %s (%.1f,%.1f)-(%.1f,%.1f)" % (n2, l, a, b, c, d)
        for vx, vy, n2 in tile_vias:
            if n2 == nm:
                continue
            if (px - vx) ** 2 + (py - vy) ** 2 < (w / 2.0 + 0.5 + grow) ** 2:
                return "via %s (%.1f,%.1f)" % (n2, vx, vy)
        return None

    def pt_clear(px, py, lyr, nm, w, grow=0.0):
        """Could a track of width w on lyr sit here?  SMD pads live on F.Cu
        only, so In2 sees only the through-hole ones -- which is the whole
        reason there is room for these lanes."""
        for _r, _p, ax, ay, tht, net, hd, rc in allpads:
            if net == nm or not (tht or lyr == "F.Cu"):
                continue
            # The real rectangle, not the half-diagonal: these lanes have to
            # thread between a SOIC-8's pins, where the circle is 1 mm wrong.
            if P.pad_gap(px, py, ax, ay, rc) < w / 2.0 + 0.2 + grow:
                return False
        for a, b, c, d, l, n2, w2 in tracks:
            if n2 == nm or l != lyr:
                continue
            if _pdist(px, py, a, b, c, d) < w / 2.0 + w2 / 2.0 + 0.2 + grow:
                return False
        for vx, vy, n2 in tile_vias:
            if n2 == nm:
                continue
            if (px - vx) ** 2 + (py - vy) ** 2 < (w / 2.0 + 0.5 + grow) ** 2:
                return False
        return True

    spine_report = []

    def spine(nm, pts, w=W_LANE, lyr="In2.Cu"):
        """Lay a hand-routed trunk, hopping to the other layer over anything
        already in the way."""
        if nm not in numof:
            return
        other = "F.Cu" if lyr == "In2.Cu" else "In2.Cu"
        JOG, STEP = 0.8, 0.25
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            L = _m.hypot(x1 - x0, y1 - y0)
            if L < 1e-9:
                continue
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            n = max(2, int(L / STEP) + 1)
            bad = [not pt_clear(x0 + ux * L * k / n, y0 + uy * L * k / n,
                                lyr, nm, w) for k in range(n + 1)]
            runs, k = [], 0
            while k <= n:
                if bad[k]:
                    j = k
                    while j <= n and bad[j]:
                        j += 1
                    runs.append((k * L / n, (j - 1) * L / n))
                    k = j
                else:
                    k += 1
            # Widen each blocked run into a jog window and merge any that now
            # touch.  A window that runs off either end is not a failure: the
            # segment simply STARTS (or ends) on the other layer, with the via
            # at the segment's own endpoint.  That is the ordinary case for a
            # spur leaving a trunk that has a neighbouring lane a couple of
            # millimetres away -- there is no room to jog after setting off, so
            # it sets off already on the other layer.
            wins = []
            for a, b in runs:
                a, b = max(0.0, a - JOG), min(L, b + JOG)
                if wins and a < wins[-1][1] + 0.8:
                    wins[-1] = (wins[-1][0], b)
                else:
                    wins.append((a, b))
            if wins and wins[0][0] <= 0.0 and wins[-1][1] >= L:
                spine_report.append((nm, (x0, y0, x1, y1), "blocked end to end"))
                continue
            # Build the whole piece list first, then accept or reject it whole.
            segs, vis, t = [], [], 0.0
            for a, b in wins:
                pa = (x0 + ux * a, y0 + uy * a)
                pb = (x0 + ux * b, y0 + uy * b)
                if a > 0.0:
                    segs.append((x0 + ux * t, y0 + uy * t, pa[0], pa[1], lyr))
                segs.append((pa[0], pa[1], pb[0], pb[1], other))
                vis += [pa, pb]
                t = b
            if t < L:
                segs.append((x0 + ux * t, y0 + uy * t, x1, y1, lyr))
            ok, why = True, ""
            for ax, ay, bx, by, sl in segs:
                if _m.hypot(bx - ax, by - ay) < 1e-9:
                    continue
                m2 = max(2, int(_m.hypot(bx - ax, by - ay) / STEP) + 1)
                for k in range(m2 + 1):
                    qx = ax + (bx - ax) * k / m2
                    qy = ay + (by - ay) * k / m2
                    if not pt_clear(qx, qy, sl, nm, w):
                        ok = False
                        why = "%s at (%.1f,%.1f) hits %s" % (
                            sl, qx, qy, pt_why(qx, qy, sl, nm, w))
                        break
                if not ok:
                    break
            for vx, vy in vis:
                # A via needs its own 0.3 mm radius plus clearance, which is
                # more than the track it replaces.
                for sl in (lyr, other):
                    if not pt_clear(vx, vy, sl, nm, w, VR - w / 2.0 + 0.05):
                        ok = False
                        why = why or "via (%.1f,%.1f) on %s hits %s" % (
                            vx, vy, sl, pt_why(vx, vy, sl, nm, w, 0.15))
            if not ok:
                spine_report.append((nm, (x0, y0, x1, y1),
                                     "%d jog(s): %s" % (len(wins), why)))
                continue
            for ax, ay, bx, by, sl in segs:
                if _m.hypot(bx - ax, by - ay) > 1e-9:
                    tracks.append((ax, ay, bx, by, sl, nm, w))
            for vx, vy in vis:
                tile_vias.append((vx, vy, nm))

    # The margin lanes, west to east on the left and mirrored on the right.
    # Each carries the y at which its two margins are linked across the top and
    # how far down the margin it has to run.
    #
    # The ORDER is what makes the top band work: the outermost lane gets the
    # HIGHEST link, and every lane starts at its own link, so a link only ever
    # passes over lanes that have not begun yet.  Nothing crosses anything, and
    # six nets get both margins joined without a single via.
    #
    # NOTHING here sends a spur inward.  That is a rule, not an accident: two
    # lanes in the same 10 mm margin that both have to reach the tile array
    # cannot both get there, because the outer one's spur has to cross the
    # inner one, and there is nowhere in this margin for the jog to land -- the
    # 8.97 mm pin column, the 6.5 mm bead column and the +3V3_A rail at 10.8
    # leave no clear millimetre of F.Cu between them.  The heater rails go down
    # the TILE COLUMNS instead (below), where their own pads already form the
    # lane.
    #   x     net              link y  down to
    # The links sit at y = 26..34, not 20..28, because the two helper jacks put
    # a 12 mm escape stub straight down the board from y = 12 to y = 24 and
    # those stubs are laid blind, after this, by the two-point pass.  Higher up
    # the first four links crossed them: five tracks_crossing errors, and the
    # only ones that round produced.
    #
    # The pitch is 1.6 mm, not 0.8.  A lane is only useful if something can drop
    # a VIA on it, and a via needs its own cell and its four neighbours clear on
    # both layers -- 1.5 mm across.  At 0.8 mm pitch the six lanes blocked In2
    # continuously from x = 0.35 to 4.85, so the thermometers' I2C pins had no
    # via site anywhere in the margin and ten I2C connections could not be made.
    # At 1.6 mm a via sits on its own lane with 1.1 mm to its neighbours.
    #
    # Left and right are NOT mirror images, because the parts are not.  A
    # TMP1075 has SDA and SCL on pins 1-2 and V+ and the address straps on
    # 5-8, and all eight parts are at rot 0, so in the left margin the I2C pins
    # face outward and in the right margin they face inward.  Mirroring the
    # lanes put the right-hand I2C lane 7 mm from its own pins with the part's
    # other four pins in between.  Each side is ordered by what it has to
    # reach.  The cost is that the links no longer nest, so a few of them cross
    # in the top band; spine() jogs over those, and the top band is empty.
    #   left x  net              right x  link y   down to
    # The six links share a 4 mm band, 25.0 to 29.0.  Above it is the helper
    # jacks' escape stub, which runs down to y = 24; below it is Q2003, whose
    # SOT-223 pads occupy y 29.4..34.6 in the right margin.  A link needs no
    # via site of its own -- only the verticals do -- so 0.8 mm between them is
    # plenty here.
    # The right margin is the MIRROR of the left, now that the parts in it are
    # (see hand_placed).  That is why there is no separate right-hand column in
    # this table: 205 - x, and every clearance holds on both sides.  Round 18
    # placed the two sides independently, by where a via could be got in given
    # parts that faced the wrong way, and no arrangement covered every pin.
    #   left x  net              link y   down to
    LANES = [(1.4, "I2C_SCL", 25.0, G.BH - 4.0),
             (3.0, "I2C_SDA", 25.8, G.BH - 4.0),
             (4.6, "Net-(Q2003-D)", 26.6, 155.0),
             (6.2, "HTR_DRIVE", 27.4, G.BH - 4.0),
             (7.8, "+3V3_D", 28.2, G.BH - 4.0),
             (9.4, "+15V_HTR", 29.0, 155.0)]
    LANE_X = {nm: lx for lx, nm, _l, _b in LANES}
    LANE_Y = {nm: ly for _lx, nm, ly, _b in LANES}
    LANE_RX = {nm: G.BW - lx for lx, nm, _l, _b in LANES}
    for lx, nm, ly, by in LANES:
        rx = G.BW - lx
        spine(nm, [(lx, ly), (rx, ly)])                    # the top link
        spine(nm, [(lx, ly), (lx, by)])                    # left margin
        spine(nm, [(rx, ly), (rx, by)])                    # right margin
    # J5001 pin 13, the debug header's SCL, is boxed in by its neighbours'
    # links above and the +3V3_D run below, and the router left it stranded
    # (2026-10-09).  By hand on In2: down between pins 12 and 14, along under
    # the header 1 mm in from the edge, and up onto the foot of the SCL lane.
    for ref, pn, ax, ay, _t, net, _hd, _rc in allpads:
        if ref == "J5001" and pn == "13" and net == "I2C_SCL":
            gx, ey = ax + 1.27, G.BH - 1.0
            pts = [(ax, ay), (gx, ay + 1.27), (gx, ey), (LANE_X["I2C_SCL"], ey),
                   (LANE_X["I2C_SCL"], G.BH - 4.0)]
            for qa, qb in zip(pts, pts[1:]):
                tracks.append(qa + qb + ("In2.Cu", net, T.W_SIG))

    # ---- the heater rails down the tile columns ---------------------------
    # Each in-tile heater is a 2010 lying across the tile's outboard strip with
    # its +15 V pad inboard and its drain pad outboard, and the thirteen of them
    # sit on two rows 17.8 mm apart -- so their pads already form four straight
    # vertical lines: +15 V at x = 73.21 and 131.79, drain at 68.59 and 136.41.
    # A trunk laid ON one of those lines runs through every pad it has to
    # reach, crosses no other rail, and needs no spurs at all.
    #
    # The only thing in the way is the 1 pps escape stub, which leaves each
    # tile horizontally at its row + 4.9 mm; the trunk hops to F.Cu for a
    # couple of millimetres there.  That F.Cu is the tile's own empty outboard
    # strip, which is why the heater is in it in the first place.
    # dx from the unit's own origin, and how far down the column has to run:
    # the left pair carries on to R2023 at y = 174 and the right pair stops at
    # R2024 and the FET, well clear of the socket at 169.
    # dx from the unit's own origin, then the top and bottom of the trunk.  The
    # +15 V pair starts ON its own top link at y = 32 -- that is how it is fed;
    # the two drains start BELOW every link, because they are fed from the FET
    # at the foot of their own column and must not cross anything on the way.
    HCOL = {("+15V_HTR", True): (30.31, 32.0, 176.0),
            ("+15V_HTR", False): (30.31, 32.0, 160.0),
            ("Net-(Q2001-D)", True): (25.69, 40.0, 176.0),
            ("Net-(Q2002-D)", False): (25.69, 40.0, 168.0)}
    for (nm, left), (dx, ytop, ybot) in sorted(HCOL.items()):
        sgn = 1.0 if left else -1.0
        cx = G.XC - sgn * G.SMA_10M_DX + sgn * dx
        spine(nm, [(cx, ytop), (cx, ybot)])

    # Two of the three heaters below the array sit ON the columns and need no
    # copper of their own.  The third, R2022, is on the centre line under the
    # helper: it is reached along the clear band at y = 151..153, which is under
    # the last right-hand tile row and above the helper's foot.
    LCOL_D = G.XC - G.SMA_10M_DX + 25.69       # left drain column, x = 68.59
    LCOL_H = G.XC - G.SMA_10M_DX + 30.31       # left +15 V column, x = 73.21
    RCOL_D = G.XC + G.SMA_10M_DX - 25.69       # right drain column, x = 136.41
    RCOL_H = G.XC + G.SMA_10M_DX - 30.31       # right +15 V column, x = 131.79
    spine("Net-(Q2002-D)", [(RCOL_D, 153.0), (104.81, 153.0), (104.81, 156.0)])
    spine("+15V_HTR", [(RCOL_H, 151.0), (100.19, 151.0), (100.19, 156.0)])
    # The gate line has to reach all three FETs, and two of them sit at the
    # foot of their own tile column.  y = 161 is the one clear row between the
    # last tile and the socket comb.
    # ...and its last 2.5 mm on F.Cu rather than In2, so that it arrives on
    # Q2002's gate pad without needing a lane of its own down to it.
    spine("HTR_DRIVE", [(LANE_X["HTR_DRIVE"], 161.0), (128.5, 161.0)])
    spine("HTR_DRIVE", [(128.5, 161.0), (131.0, 161.0)], w=T.W_SIG, lyr="F.Cu")
    if (pt_clear(128.5, 161.0, "F.Cu", "HTR_DRIVE", T.W_SIG, VIA_GROW) and
            pt_clear(128.5, 161.0, "In2.Cu", "HTR_DRIVE", T.W_SIG, VIA_GROW)):
        tile_vias.append((128.5, 161.0, "HTR_DRIVE"))
    else:
        spine_report.append(("HTR_DRIVE", (128.5, 161.0, 128.5, 161.0),
                             "no room for the gate trunk's F.Cu hop"))
    # All three gates, laid by hand.  A SOT-223's gate is 2.3 mm from its own
    # drain tab on the same x, and the router kept losing one or other of these
    # last hops -- and losing them silently, because a missing gate shows up in
    # the DRC report as whichever pair of items happens to be closest across
    # the two halves of the net, which was twice a pad 130 mm from the actual
    # break.  They are short, forced and identical, so there is no reason for a
    # search to be involved at all.
    #
    # Q2001 and Q2002 sit just under the y = 161 gate trunk, so each drops
    # straight down its own x.  Q2003 is up in the right margin beside the gate
    # lane, so it runs across at its gate's own y, under its own package and
    # clear of the tab above it and the source pin beyond it.
    def _lerp(a, b, step=0.25):
        n = max(2, int(_m.hypot(b[0] - a[0], b[1] - a[1]) / step) + 1)
        return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                for k in range(n + 1)]

    def _trunk_is_fcu(px, py):
        return any(l == "F.Cu" and n2 == "HTR_DRIVE" and
                   _pdist(px, py, a, b, c, d) < 0.2
                   for a, b, c, d, l, n2, _w in tracks)

    for qref in ("Q2001", "Q2002", "Q2003"):
        if qref not in placed:
            continue
        qx, qy, _qr = placed[qref]
        gpx, gpy = qx - 3.15, qy - 2.3          # the gate pad
        # Where each one meets the gate net: Q2003 across to the right-hand
        # margin lane at its own y, Q2002 straight up to the top link, Q2001
        # straight up to the y = 161 trunk it sits under.
        if qref == "Q2002" or (qref == "Q2001" and os.environ.get("R13UP")):
            continue          # its gate pad sits on the trunk itself
        vx, vy = {"Q2003": (LANE_RX["HTR_DRIVE"], gpy),
                  "Q2001": (gpx, 161.0)}[qref]
        # Ask BEFORE laying the stub, or the stub is what the answer finds.
        need_via = not _trunk_is_fcu(vx, vy)
        # All on F.Cu, right up to the point where the via drops onto the
        # trunk.  Q2002's run crosses four In2 links on the way, which costs it
        # nothing because they are on the other layer -- whereas breaking the
        # run into In2 pieces between them leaves 2.6 mm gaps with nowhere to
        # jog, which is what the first attempt did.
        spine("HTR_DRIVE", [(gpx, gpy), (vx, vy)], w=T.W_SIG, lyr="F.Cu")
        if not need_via:
            continue                            # the trunk is already F.Cu here
        if (pt_clear(vx, vy, "F.Cu", "HTR_DRIVE", T.W_SIG, VIA_GROW) and
                pt_clear(vx, vy, "In2.Cu", "HTR_DRIVE", T.W_SIG, VIA_GROW)):
            tile_vias.append((vx, vy, "HTR_DRIVE"))
        else:
            spine_report.append(("HTR_DRIVE", (vx, vy, vx, vy),
                                 "no room for %s's gate via" % qref))

    # ---- the five 1-Wire probe cells -------------------------------------
    # Pad geometry follows from the placement: an 0805 at rot 90 puts pad 1
    # 0.91 mm above centre, a 1206 puts it 1.46 mm above.
    ONE_Y, PWR_Y = 18.91, 17.0
    spine("ONEWIRE", [(G.PROBE_X[0], ONE_Y), (G.PROBE_X[-1], ONE_Y)],
          w=T.W_SIG, lyr="F.Cu")
    spine("+3V3_D", [(LANE_X["+3V3_D"], PWR_Y), (G.PROBE_X[-1] - 3.5, PWR_Y)])
    # ...and up the margin to meet the lane, which starts at its own link.
    spine("+3V3_D", [(LANE_X["+3V3_D"], PWR_Y),
                     (LANE_X["+3V3_D"], LANE_Y["+3V3_D"])])
    for i, jx in enumerate(G.PROBE_X):
        n = i + 1
        spine("Net-(J600%d-Pin_1)" % n, [(jx, 17.09), (jx, 8.0)],
              w=T.W_SIG, lyr="F.Cu")
        spine("Net-(J600%d-Pin_2)" % n, [(jx - 3.5, 13.14), (jx - 3.5, 8.0)],
              w=T.W_SIG, lyr="F.Cu")
        # the power resistor's own hop down to the In2 bus, 1 mm above it
        spine("+3V3_D", [(jx - 3.5, 16.06), (jx - 3.5, PWR_Y)],
              w=W_LANE, lyr="F.Cu")
        if (pt_clear(jx - 3.5, PWR_Y, "F.Cu", "+3V3_D", W_LANE, VIA_GROW) and
                pt_clear(jx - 3.5, PWR_Y, "In2.Cu", "+3V3_D", W_LANE, VIA_GROW)):
            tile_vias.append((jx - 3.5, PWR_Y, "+3V3_D"))
        else:
            spine_report.append(("+3V3_D", (jx - 3.5, PWR_Y, jx - 3.5, PWR_Y),
                                 "no room for the bus via"))

    # ---- adjacent pins of the same net, jumpered ------------------------
    # A TMP1075's three address pins are strapped high or low to set its I2C
    # address, so on most of the eight, two of them are adjacent and both on
    # +3V3_D -- 1.27 mm apart on the same x, with nothing whatever in between.
    # The router kept losing one of those, which is an absurd thing to ask a
    # maze search for: the answer is a straight line 1.27 mm long.  Any two
    # pads of one part, on one net, within 1.4 mm of each other, get joined.
    for ref in sorted({r for r, _p, _x, _y, _t, _n, _h, _rc in allpads
                       if r.startswith("U50") or r.startswith("U60")}):
        mine = [(pn, ax, ay, net) for r, pn, ax, ay, _t, net, _h, _rc in allpads
                if r == ref and net and not net.startswith("unconnected-")]
        for i in range(len(mine)):
            for j in range(i + 1, len(mine)):
                if mine[i][3] != mine[j][3] or mine[i][3] == "GND":
                    continue
                if _m.dist(mine[i][1:3], mine[j][1:3]) > 1.4:
                    continue
                spine(mine[i][3], [mine[i][1:3], mine[j][1:3]],
                      w=T.W_SIG, lyr="F.Cu")

    # ---- the helper's own thermometer, out to the I2C links --------------
    # U5007 sits on the centre line with the two I2C links passing a couple of
    # millimetres below it, but its SDA and SCL pins are pins 1 and 2, with the
    # ALERT and GND pins between them and the links.  Step west clear of the
    # package first, then drop.
    if "U5007" in placed and placed["U5007"][1] < 40.0:    # rev A's spot only
        cx, cy, _r7 = placed["U5007"]
        for pin, nm7, dx7 in (("2", "I2C_SCL", 4.6), ("1", "I2C_SDA", 5.6)):
            n7 = nets.get("U5007", {}).get(pin)
            if not n7 or n7 not in numof:
                continue
            py7 = cy - (0.635 if pin == "2" else 1.905)
            spine(n7, [(cx - 2.47, py7), (cx - dx7, py7),
                       (cx - dx7, LANE_Y[nm7])], w=T.W_SIG, lyr="F.Cu")
            if (pt_clear(cx - dx7, LANE_Y[nm7], "F.Cu", n7, T.W_SIG, VIA_GROW) and
                    pt_clear(cx - dx7, LANE_Y[nm7], "In2.Cu", n7, T.W_SIG, VIA_GROW)):
                tile_vias.append((cx - dx7, LANE_Y[nm7], n7))
            else:
                spine_report.append((n7, (cx - dx7, LANE_Y[nm7]) * 2,
                                     "no room for U5007's %s via" % nm7))

    # ---- the DS2482 and the DAC, one straight supply track each -----------
    # SOIC-8 pins 1-4 sit 2.47 mm left of centre at y offsets -1.905..+1.905;
    # SOT-23-6 pins 1-3 sit 1.14 mm left at -0.95, 0, +0.95.
    if "U6001" in placed:
        cx, cy, _r = placed["U6001"]
        vnm = nets.get("U6001", {}).get("1")
        spine(vnm, [(cx - 4.55, cy + 3.2), (cx - 4.55, cy - 1.905),
                    (cx - 2.47, cy - 1.905)], w=T.W_SIG, lyr="F.Cu")
        spine(vnm, [(cx - 2.47, cy - 3.79), (cx - 2.47, cy - 1.905)],
              w=T.W_SIG, lyr="F.Cu")
        # the bead's own +3V3_D end drops onto the probe-cell bus
        spine("+3V3_D", [(cx - 2.47, cy - 5.61), (cx - 2.47, PWR_Y)],
              w=W_LANE, lyr="F.Cu")
        if (pt_clear(cx - 2.47, PWR_Y, "F.Cu", "+3V3_D", W_LANE, VIA_GROW) and
                pt_clear(cx - 2.47, PWR_Y, "In2.Cu", "+3V3_D", W_LANE, VIA_GROW)):
            tile_vias.append((cx - 2.47, PWR_Y, "+3V3_D"))
    if "U5009" in placed:
        cx, cy, _r = placed["U5009"]
        vnm = nets.get("U5009", {}).get("3")
        spine(vnm, [(cx - 3.55, cy - 2.0), (cx - 3.55, cy + 0.95),
                    (cx - 1.14, cy + 0.95)], w=T.W_SIG, lyr="F.Cu")
        spine(vnm, [(cx - 1.14, cy + 3.09), (cx - 1.14, cy + 0.95)],
              w=T.W_SIG, lyr="F.Cu")

    # ---- the eight thermometer stacks ------------------------------------
    # Each one is the same four terminals: the bead's output, the part's V+ pin
    # and two capacitors.  With the passives turned so their V+ pads share a
    # column (see hand_placed), the whole net is one straight run between the
    # SOIC's two rows of pins and one hop over the top of the package.  0.25 mm
    # signal track: this carries the 45 uA a TMP1075 draws.
    for i in range(1, 9):
        ic = "U500%d" % i
        if ic not in placed:
            continue
        cx, cy, crot = placed[ic]
        vnm = nets.get(ic, {}).get("8")
        if not vnm:
            continue
        s = -1.0 if crot == 180 else 1.0      # mirrored right-margin stack
        spine(vnm, [(cx - s * 0.95, cy - s * 5.0),
                    (cx - s * 0.95, cy + s * 7.0)], w=T.W_SIG, lyr="F.Cu")
        spine(vnm, [(cx - s * 0.95, cy - s * 3.5),
                    (cx + s * 2.475, cy - s * 3.5),
                    (cx + s * 2.475, cy - s * 1.905)], w=T.W_SIG, lyr="F.Cu")

    if spine_report:
        import sys as _sp
        print("spines: %d segment(s) dropped" % len(spine_report), file=_sp.stderr)
        for nm, sg, why in spine_report:
            print("   %-16s (%.1f,%.1f)-(%.1f,%.1f)  %s"
                  % (nm, sg[0], sg[1], sg[2], sg[3], why), file=_sp.stderr)

    if os.environ.get("SPINEDUMP"):
        import pickle
        pickle.dump({"pads": allpads, "tracks": list(tracks),
                     "vias": list(tile_vias), "placed": placed, "fps": fps},
                    open(os.environ["SPINEDUMP"], "wb"))
        return out, placed, fps, boxes

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
            # The board's real 0.2, not CLR's 0.15: a plane via has 96 places
            # to try, so the full rule costs it nothing, and at 0.15 rev B put
            # two GND vias 0.185 from the In2 I2C_SCL ring (KiCad: 0.2).
            if (px - qx) ** 2 + (py - qy) ** 2 < (rad + w / 2.0 + 0.2) ** 2:
                return False
        for tx, ty, _n in tile_vias:
            if (px - tx) ** 2 + (py - ty) ** 2 < (rad + 0.45) ** 2:
                return False
        return True

    def gutter_clear(px, py):
        """Rev A's +3V3_A rail ran down every tile's gutter, and it kept this
        search out of it, "which is what leaves a clean vertical channel on
        In2.Cu underneath" (tile.py) for the beat and pps returns.  Rev B's
        plane took the rail away; without this, ground and +3V3_A vias landed
        in the gutters, the returns spilled onto F.Cu along the bottom, and
        I2C_SCL to the header lost its way out (2026-10-09).  0.75 mm: the old
        0.5 mm rail's half-width, a via's radius and the 0.2 mm rule."""
        for x0, y0, x1, y1 in gutters:
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy
            u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
            qx, qy = x0 + u * dx, y0 + u * dy
            if (px - qx) ** 2 + (py - qy) ** 2 < 0.75 ** 2:
                return False
        return True

    # Rev B: the same search gives every +3V3_A pad its via to the B.Cu plane
    # (item 5), except a pad that a tile already drops to it by hand (R51).
    PLANE_NETS = ("GND", "+3V3_A")
    vias, nvia, skipped = [], {n: 0 for n in PLANE_NETS}, {n: 0 for n in PLANE_NETS}
    for ref, pn, ax, ay, tht, net, _hd, _rc in allpads:
        if net not in PLANE_NETS or tht or (ref, pn) in H.NO_PLANE_VIA:
            continue
        if any(_n == net and (ax - tx) ** 2 + (ay - ty) ** 2 < 2.0 ** 2
               for tx, ty, _n in tile_vias):
            continue
        best = None
        # Sixteen directions and six radii, not eight and four.  The margin
        # lanes leave 1.1 mm gaps between them which a 0.6 mm via fits in
        # comfortably, but a search that only looks along the eight compass
        # points at four distances mostly misses them: round 19 left 62 pads
        # with no via at all, up from 32 before the lanes went in.
        for rad in (1.35, 1.6, 1.85, 2.1, 2.45, 2.8):
            for k in range(16):
                th = k * _m.pi / 8.0
                vx, vy = ax + rad * _m.cos(th), ay + rad * _m.sin(th)
                # 0.3 via radius + that pad's OWN half-diagonal + 0.25 clearance.
                # A constant was fine for 0805s and far too small for the
                # SOT-223 tab and the SMA diodes.
                ok = all(P.pad_gap(vx, vy, qx, qy, qrc) > 0.55
                         for _r, _p, qx, qy, _t, _n, qh, qrc in allpads
                         if not (_r == ref and _p == pn))
                ok = ok and all((vx - wx) ** 2 + (vy - wy) ** 2 > 1.5 ** 2
                                for wx, wy in vias)
                # the STUB has to clear other pads too, not just the via:
                # checking only the endpoint left tracks running over pads
                if ok:
                    for f in (0.35, 0.6, 0.85):
                        sx, sy = ax + (vx - ax) * f, ay + (vy - ay) * f
                        if not all(P.pad_gap(sx, sy, qx, qy, qrc) > 0.43
                                   for _r, _p, qx, qy, _t, _n, qh, qrc in allpads
                                   if not (_r == ref and _p == pn)):
                            ok = False
                            break
                # and it must not hang off the board edge
                ok = ok and (0.8 < vx < G.BW - 0.8 and 0.8 < vy < G.BH - 0.8)
                ok = ok and seg_clear(vx, vy, 0.3) and gutter_clear(vx, vy)
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
            skipped[net] += 1
            if net != "GND":
                print("PLANE VIA: no room for %s pad %s (%s)" % (ref, pn, net),
                      file=sys.stderr)
            continue
        vx, vy = best
        vias.append((vx, vy))
        out.append(track(ax, ay, vx, vy, "F.Cu", numof[net], ref + pn, 0.35))
        out.append(via(vx, vy, numof[net], ref + pn))
        # ...and into `tracks`, so the routers know this copper exists.  They
        # did not: only the VIAS were being registered, so every F.Cu route
        # was free to run straight over a ground stub.
        tracks.append((ax, ay, vx, vy, "F.Cu", net, 0.35))
        nvia[net] += 1
    out.append(text(4.0, G.BH - 2.0, "%d ground vias (%d pads had no room); "
                    "%d +3V3_A plane vias (%d had no room)"
                    % (nvia["GND"], skipped["GND"], nvia["+3V3_A"], skipped["+3V3_A"]),
                    "Cmts.User", 1.2, 0.2))
    print("plane vias: GND %d (%d no room), +3V3_A %d (%d no room)"
          % (nvia["GND"], skipped["GND"], nvia["+3V3_A"], skipped["+3V3_A"]),
          file=sys.stderr)

    # ---- In2.Cu: helper branches, beat/pulse returns, helper SMAs ---------
    # Routed by a maze router (pcb/maze.py) rather than by hand-assigned lanes.
    # Twenty-five returns converge on a 48 mm connector from sources spread
    # over 200 mm; that is a single-layer planarity problem, and a router that
    # only ever walks free cells cannot produce a crossing.
    _ntracks0, _nvias0 = len(tracks), len(tile_vias)
    grid = MZ.Grid(G.BW, G.BH)
    IN2, FCU = 0, 1
    for ref, pn, ax, ay, tht, net, hd, rc in allpads:
        if tht:
            grid.block_rect(ax, ay, rc, 0.35)           # both layers
            grid.block_via(ax, ay, NOVIA_R(hd))
        else:
            grid.block_rect(ax, ay, rc, 0.85, FCU)
    for vx, vy in vias:                                 # the ground vias
        grid.block_disc(vx, vy, 0.62)
    for vx, vy, _nm in tile_vias:
        grid.block_disc(vx, vy, 0.62)
    for x0, y0, x1, y1, lyr, nm, w in tracks:
        grid.block_seg(x0, y0, x1, y1, w / 2.0 + 0.3,
                       IN2 if lyr == "In2.Cu" else FCU)

    def _segdist(a, b, c, d, e, f, g_, h):
        """Minimum distance between segments (a,b)-(c,d) and (e,f)-(g_,h)."""
        def pd(px, py, x0, y0, x1, y1):
            dx, dy = x1 - x0, y1 - y0
            L2 = dx * dx + dy * dy
            u = 0.0 if L2 == 0 else max(0.0, min(
                1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
            return _m.hypot(px - (x0 + u * dx), py - (y0 + u * dy))
        d1 = (c - a, d - b)
        d2 = (g_ - e, h - f)
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if den:
            s = ((e - a) * d2[1] - (f - b) * d2[0]) / den
            u = ((e - a) * d1[1] - (f - b) * d1[0]) / den
            if 0 <= s <= 1 and 0 <= u <= 1:
                return 0.0
        return min(pd(a, b, e, f, g_, h), pd(c, d, e, f, g_, h),
                   pd(e, f, a, b, c, d), pd(g_, h, a, b, c, d))

    def vias_clear(newvias, nm, trk=None):
        """The same analytic check, for the VIAS a path wants to place.

        path_clear() only ever looked at segments, so a candidate via was
        accepted on the grid's word alone -- and the grid is a model.  That was
        invisible while the grid was rebuilt per net from the same code that
        drew it, and it showed up the moment the grid changed: the
        reference-counted version routed everything and left fifteen clearance
        errors, every one of them a via.  A via is 0.6 mm across and needs
        0.15 mm to anything on ANY layer, because it goes through all of them.
        """
        trk = tracks if trk is None else trk
        for vx, vy in newvias:
            for _r, _p, ax, ay, tht, n2, _h, rc in allpads:
                # hole-to-hole applies to the net's OWN through-hole pads too
                if tht and _h and (vx - ax) ** 2 + (vy - ay) ** 2 < NOVIA_R(_h) ** 2:
                    return False
                if n2 == nm:
                    continue
                if P.pad_gap(vx, vy, ax, ay, rc) < VR + CLR:
                    return False
            for a, b, c, d, _lyr, n2, w2 in trk:
                if n2 == nm:
                    continue
                if _segdist(vx, vy, vx, vy, a, b, c, d) < VR + w2 / 2.0 + CLR:
                    return False
            for qx, qy in vias:
                if (vx - qx) ** 2 + (vy - qy) ** 2 < (2 * VR + CLR) ** 2:
                    return False
            for qx, qy, n2 in tile_vias:
                if n2 == nm:
                    continue
                if (vx - qx) ** 2 + (vy - qy) ** 2 < (2 * VR + CLR) ** 2:
                    return False
        return True

    def path_clear(newsegs, nm, trk=None):
        """Analytic clearance check on a candidate path.

        The grid is a model of the board and every bug in this pass so far has
        been a place where the model and the board disagreed.  This checks the
        real geometry instead, and simply refuses a path that would not pass
        DRC -- a lost join shows as ratsnest, which is honest, where a bad one
        shows as an error."""
        trk = tracks if trk is None else trk
        for x0, y0, x1, y1, l0, w0 in newsegs:
            lyr0 = "In2.Cu" if l0 == IN2 else "F.Cu"
            # Pads too.  This used to check only tracks and vias, which was
            # fine while the grid blocked every pad by 0.85 mm -- but 0.85 mm
            # on a 1.27 mm pin pitch walls a SOIC-8 in completely, so the grid
            # is looser now and the real check has to live here.
            for _r, _p, ax, ay, tht, n2, _h, rc in allpads:
                if n2 == nm or not (tht or lyr0 == "F.Cu"):
                    continue
                n = max(2, int(_m.hypot(x1 - x0, y1 - y0) / 0.25) + 1)
                if any(P.pad_gap(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n,
                                 ax, ay, rc) < w0 / 2.0 + CLR
                       for k in range(n + 1)):
                    return False
            for a, b, c, d, lyr, n2, w2 in trk:
                if n2 == nm or lyr != lyr0:
                    continue
                if _segdist(x0, y0, x1, y1, a, b, c, d) < \
                        w0 / 2.0 + w2 / 2.0 + CLR:
                    return False
            for vx, vy in vias:
                if _segdist(x0, y0, x1, y1, vx, vy, vx, vy) < w0 / 2.0 + VR + CLR:
                    return False
            for vx, vy, n2 in tile_vias:
                if n2 == nm:
                    continue
                if _segdist(x0, y0, x1, y1, vx, vy, vx, vy) < w0 / 2.0 + VR + CLR:
                    return False
        return True

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
    # Relative to the board edge, not absolute: when round 15 took the board
    # from 170 to 180 these stayed put, which turned a 2.5 mm stub into a
    # 12.5 mm one and made the picket fence in front of the socket five
    # times deeper than it needed to be.
    ODD_Y, EVEN_Y = G.BH - 10.0, G.BH - 13.0
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
            # Branches before returns.  Tried it the other way round on the
            # theory that 7 branches hopping to F.Cu beats 13 returns doing
            # it; measured, it is worse -- 33 routed against 37 -- because a
            # branch that has already crossed the lane leaves a gap a return
            # can use, while a return bundle leaves nothing.
            jobs.append((nm, pts[0], targets[nm],
                         -1 if nm == "HELPER_CLK" else 0))
    for nm in sorted(src):
        if nm.startswith("HCLK_") and len(src[nm]) == 2:
            aa, bb = sorted(src[nm], key=lambda q: q[1])
            jobs.append((nm, aa, bb, -1))
    for nm in ("Net-(J3001-In)", "Net-(J3002-In)"):
        pts = list(src.get(nm, []))
        for ref, pn, ax, ay, tht, net, _hd, _rc in allpads:
            if net == nm and tht:
                # A vertical SMA's centre pin sits inside a ring of four
                # ground pins 2.54 mm away, so nothing can start next to it:
                # give it a stub straight up the 1.14 mm gutter between them --
                # or DOWN, for the two helper jacks, which since round 15 sit
                # in the top band where "up" is off the board.
                d = 12.0 if ay > G.BH / 2.0 else -12.0
                ey = round((ay - d) / MZ.PITCH) * MZ.PITCH
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
    # The topmost unit of each lane: its return is the outermost wire of its
    # fan, so it is the one with no slack.  units_by_x() ends each lane with
    # its topmost unit, so these are the last of each half.
    _by_lane = G.units_by_x()
    _left = [u for u in _by_lane if G.UNIT_ROW[u][2] == 90]
    _right = [u for u in _by_lane if G.UNIT_ROW[u][2] != 90]
    _top = (_left[-1], _right[-1])          # units_by_x ends each lane at its top
    OUTERMOST = set()
    for _u in _top:
        OUTERMOST.add("BEAT_%02d" % (_u - 1))
        OUTERMOST.add("PPS_%02d" % (_u - 1))

    def _K2(j):
        return (0 if abs(j[1][0] - j[2][0]) < 15.0 else 1, j[2][0])

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
          8: lambda j: (0 if j[1][0] > j[2][0] else 1, -j[2][0]),
          # 9: stage-aware.  With the header order nested (round 19), a return
          #    bundle is a fan turning a corner, and the wire that ends at the
          #    furthest pin is the OUTERMOST of the fan -- it has to hug the
          #    outside of both the descent and the run along the socket, so it
          #    must claim those lanes before the inner ones box it in.  Longest
          #    first, therefore, but only for the returns: ordering the HELPER
          #    BRANCHES that way as well (which is what plain order 7 does)
          #    costs four of them, because a branch is not part of a fan.
          # 10: the OUTERMOST wire of each bundle first, and everything else
          #     exactly as order 2.  With the header nested (round 19) a bundle
          #     is a fan turning a corner, and the wire belonging to the unit
          #     highest up the board is the one that has to hug the outside of
          #     both the descent and the run along the socket.  It is the only
          #     one in the bundle with no slack, so it is the only one that has
          #     to be laid before the rest -- reordering the WHOLE stage by
          #     length (order 9) makes the early searches wander instead, and
          #     takes five times as long for a worse answer.
          10: lambda j: ((0 if j[3] == 0 and j[0] in OUTERMOST else 1,) +
                         tuple(_K2(j))),
          9: lambda j: ((-abs(j[1][0] - j[2][0]), 0.0) if j[3] == 0 else
                        (0.0 if abs(j[1][0] - j[2][0]) < 15.0 else 1.0,
                         j[2][0]))}[ORD]
    jobs.sort(key=lambda j: (j[3], _k(j)))
    # Rip-up and retry.  A maze router's finished route is a wall, so the
    # order decides who gets boxed in; the standard cure is to put whoever
    # failed at the FRONT of the next attempt and start over from a clean
    # layer.  Three passes is enough here -- it goes 37, 40, 41.
    def one_pass(order, base_tracks, base_vias):
        g = MZ.Grid(G.BW, G.BH)
        for ref, pn, ax, ay, tht, net, hd, rc in allpads:
            if tht:
                g.block_rect(ax, ay, rc, 0.35)
                g.block_via(ax, ay, NOVIA_R(hd))
            else:
                g.block_rect(ax, ay, rc, 0.85, FCU)
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
                cand, candv = [], []
                for i in range(len(pts) - 1):
                    x0, y0, l0 = pts[i]
                    x1, y1, l1 = pts[i + 1]
                    if l0 != l1:
                        candv.append((x0, y0, nm))
                    elif (x0, y0) != (x1, y1):
                        cand.append((x0, y0, x1, y1, l0, T.W_SIG))
                # The grid lets a route step ONTO a goal cell even when that
                # cell is blocked -- it has to, or nothing could ever terminate
                # on a pad -- and when the goal is another net's copper that is
                # a short.  Check the real geometry, the way the multi-terminal
                # pass does; a refused path costs ratsnest, a bad one costs an
                # error.
                if not (path_clear(cand, nm, base_tracks + newt) and
                        (not STRICT or
                         vias_clear([(q[0], q[1]) for q in candv], nm,
                                    base_tracks + newt))):
                    path = None
            if path:
                for x0, y0, _n in candv:
                    newv.append((x0, y0, nm))
                    g.block_disc(x0, y0, 0.62)
                for x0, y0, x1, y1, l0, w0 in cand:
                    newt.append((x0, y0, x1, y1,
                                 "In2.Cu" if l0 == IN2 else "F.Cu", nm, w0))
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
    # NOROUTE=1 skips every routing pass.  The board it produces is useless --
    # no board-level copper at all -- but it is produced in fifteen seconds
    # rather than twenty-five minutes, which is what makes it possible to
    # iterate on 600 pieces of silkscreen.  Never used by build.py.
    _NOROUTE = bool(os.environ.get("NOROUTE"))
    for attempt in range(0 if _NOROUTE else int(os.environ.get("RTPASSES", "6"))):
        nt, nv, nfail = one_pass(order, base_t, base_v)
        if best is None or len(nfail) < len(best[2]):
            best = (nt, nv, nfail)
        if not nfail:
            break
        # Failed nets to the front, and rotate the rest, so a pass that keeps
        # failing the same few is not simply repeated.
        bad = set(nfail)
        rest = [j for j in order if j[0] not in bad]
        rest = rest[attempt + 1:] + rest[:attempt + 1]
        order = [j for j in order if j[0] in bad] + rest
    nt, nv, nfail = best if best else ([], [], [])
    tracks.extend(nt)
    tile_vias.extend(nv)

    # ---- multi-terminal nets: the rails, I2C and 1-Wire -------------------
    # These are not two-point nets, so they need a spanning tree, and the rule
    # that matters is: route each disconnected piece to the NEAREST POINT OF
    # WHAT IS ALREADY CONNECTED, not to the nearest other pad.  A two-point
    # router does the latter and produces a daisy chain with the wrong
    # topology; the multi-goal mode in pcb/maze.py exists for this.
    # 0.3 mm, not 0.5: these are DISTRIBUTION runs, not the trunk.  The trunk
    # inside the power block is already 0.5 and carries the whole 643 mA; a
    # branch to one heater carries 27 mA and the +3V3_D rail about 60 mA total,
    # for which 0.3 mm on 35 um is good for ~700 mA.  Halving the width is the
    # single biggest thing available for routability here.
    W_DIST = 0.3
    # EVERY net, not a hand-written list of eleven.  Rounds 15-17 named the
    # rails and the buses here and left everything else to the two-point pass,
    # which only ever sees nets that have an In2 escape terminal -- so a
    # thermometer's bead-and-capacitor group, a probe terminal's pull-up, the
    # DS2482's own decoupling, thirty connections in all, were never offered to
    # ANY router.  They showed as ratsnest and looked like congestion.  They
    # were not: nothing had tried.
    #
    # Cheap to do, because a net that is already whole costs one union-find
    # pass and no grid: the expensive part, rebuilding the obstacle grid, only
    # happens for a net that still has two pieces.
    PWRNETS = ("+3V3_A", "+3V3_D", "+5V_HDR", "+15V_HTR", "Net-(Q2001-D)",
               "Net-(Q2002-D)", "Net-(Q2003-D)")
    _npads = {}
    for _r, _p, ax, ay, _t, net, _h, _rc in allpads:
        _npads.setdefault(net, []).append((ax, ay))

    def _span(nm):
        pts = _npads.get(nm, [])
        if len(pts) < 2:
            return 0.0
        return (max(p[0] for p in pts) - min(p[0] for p in pts) +
                max(p[1] for p in pts) - min(p[1] for p in pts))

    # Most-constrained first: a two-pad group 2 mm across has one way to go and
    # a rail has a thousand, so the rail must be the one that bends round it.
    MULTI = sorted(((nm, W_DIST if nm in PWRNETS else T.W_SIG)
                    for nm in numof
                    if nm and nm not in PLANE_NETS and not nm.startswith("unconnected-")
                    and len(_npads.get(nm, ())) > 1),
                   key=lambda q: _span(q[0]))

    # The grid is rebuilt from scratch for each net, with only THAT net's pads
    # left open.  Freeing a disc around a pad in a shared grid also wipes the
    # blocking of whatever else happens to pass within a millimetre of it --
    # first the neighbouring pins of the same SOIC, then, once that was fixed,
    # other nets' tracks.  Rebuilding costs a couple of seconds a net and
    # removes the whole class of bug.
    # ---- the same grid, built once ---------------------------------------
    # Rebuilding it per net is correct and it is where a build spends 33 of its
    # 40 minutes: 600 pads and 2000 tracks rasterised into 2 x 148k cells, once
    # for every net that still has two pieces, three times over.  With the
    # cells REFERENCE COUNTED (see maze.Grid) a net's own copper can be lifted
    # out of the finished grid and put back exactly, which is O(that net's
    # copper) instead of O(the whole board).  Setting cells to zero instead is
    # the round-18 bug this avoids: freeing the disc round a pad also freed
    # whatever else happened to pass within a millimetre of it.
    _fast = {}

    def _fast_grid():
        """The all-nets-blocked grid, plus each net's own contribution."""
        if _fast:
            return _fast["g"], _fast["cells"]
        g = MZ.Grid(G.BW, G.BH, counted=True)
        cells = {}

        def own(nm, cs):
            if nm:
                cells.setdefault(nm, []).extend(cs)
            g.add(cs)

        for _r, _p, ax, ay, tht, net, hd, rc in allpads:
            own(net, g.cells_rect(ax, ay, rc, 0.5 if tht else 0.45,
                                  None if tht else FCU))
            if tht:
                g.block_via(ax, ay, NOVIA_R(hd))    # never lifted: see maze.py
        for vx, vy in vias:
            g.add(g.cells_disc(vx, vy, 0.75))
        for vx, vy, n2 in tile_vias:
            own(n2, g.cells_disc(vx, vy, 0.75))
        for x0, y0, x1, y1, lyr, n2, w2 in tracks:
            own(n2, g.cells_seg(x0, y0, x1, y1, w2 / 2.0 + 0.5,
                                IN2 if lyr == "In2.Cu" else FCU))
        _fast["g"], _fast["cells"] = g, cells
        return g, cells

    def build_g2(open_net=None):
        if os.environ.get("FASTGRID"):
            g, cells = _fast_grid()
            g.sub(cells.get(open_net, ()))
            _fast["open"] = open_net
            return g
        g = MZ.Grid(G.BW, G.BH)
        for _r, _p, ax, ay, tht, net, hd, rc in allpads:
            # The no-via disc goes on BEFORE the net's own pads are skipped:
            # hole-to-hole does not care whose hole it is.  Round 28's first
            # build put this after the `continue` and both drill clashes -- a
            # via inside J5001 pin 13 (I2C_SCL's own pad) and one 0.24 mm from
            # J4001 pin 4 (+5V_HDR's own pad) -- came straight back.
            if tht:
                g.block_via(ax, ay, NOVIA_R(hd))
            if net == open_net:
                continue
            # 0.45 mm, not 0.85.  A 0.25 mm track needs 0.275 mm of clear
            # copper from a pad edge; 0.85 is three times that, and on a
            # SOIC-8's 1.27 mm pin pitch it leaves no free cell at all between
            # two pins, so the part's own pins cannot be escaped.  That -- not
            # congestion -- is why the I2C bus and the 3.3 V straps could not
            # be finished.  path_clear() checks the real clearance before
            # anything is committed.
            g.block_rect(ax, ay, rc, 0.5 if tht else 0.45,
                         None if tht else FCU)
        for vx, vy in vias:
            g.block_disc(vx, vy, 0.75)
        for vx, vy, _n in tile_vias:
            g.block_disc(vx, vy, 0.75)
        # w/2 + 0.5, not + 0.3: the clearance a neighbour needs depends on the
        # width of the track being ADDED, not the one already there, and these
        # add 0.5 mm rails next to 0.25 mm signals.
        for x0, y0, x1, y1, lyr, n2, w2 in tracks:
            if n2 == open_net:
                continue        # its own copper is the TREE, not an obstacle
            g.block_seg(x0, y0, x1, y1, w2 / 2.0 + 0.5,
                        IN2 if lyr == "In2.Cu" else FCU)
        return g

    def _near(px, py, s, tol, rc=None):
        """Does this track touch this pad?

        The centre-within-tol version said no whenever a track stopped on the
        EDGE of a pad, which is what a hand route normally does -- so about
        forty tile VCC nets, every one of them properly connected and none of
        them in the ratsnest, looked like two pieces to this pass and were
        re-routed from scratch.  Test against the pad rectangle, which is what
        KiCad's own connectivity does."""
        x0, y0, x1, y1 = s
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 == 0 else max(0.0, min(
            1.0, ((px - x0) * dx + (py - y0) * dy) / L2))
        if (px - (x0 + u * dx)) ** 2 + (py - (y0 + u * dy)) ** 2 <= tol * tol:
            return True
        if rc is None:
            return False
        n = max(2, int(_m.hypot(dx, dy) / 0.25) + 1)
        return any(P.pad_gap(x0 + dx * k / n, y0 + dy * k / n, px, py, rc) < 0.05
                   for k in range(n + 1))

    def _samples(s, step=1.5):
        x0, y0, x1, y1 = s
        n = max(1, int(_m.hypot(x1 - x0, y1 - y0) / step))
        return [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n)
                for k in range(n + 1)]

    def _thin(pts, cap=1500):
        return pts if len(pts) <= cap else pts[::(len(pts) // cap) + 1]

    def _multi_pass(order):
        """One full attempt at the multi-terminal nets.  Returns the
        names whose joins failed."""
        pwr_fail = []
        for nm, w in order:
            if nm not in numof:
                continue
            # Every terminal and every piece of copper carries the LAYER it
            # lives on.  It did not, and that one omission is what stopped the
            # rails: the router was asked to start on F.Cu and end on F.Cu (the
            # default when end_layer is None), so a hop from a pad to a lane
            # that lives on In2 ended one layer ABOVE the lane with no via, and
            # reported success.  The board showed a 0.5 mm stub sitting beside
            # the lane it was supposed to join, and the ratsnest still showed
            # the break.
            pds = [(ax, ay, _rc, None if _t else FCU)      # THT reaches both
                   for _r, _p, ax, ay, _t, net, _h, _rc in allpads if net == nm]
            sgs = [(a, b, c, d, IN2 if l == "In2.Cu" else FCU)
                   for a, b, c, d, l, n2, _w in tracks if n2 == nm]
            vis = [(vx, vy) for vx, vy, n2 in tile_vias if n2 == nm]
            if len(pds) < 2:
                continue
            P_, S_, V_ = len(pds), len(sgs), len(vis)
            par = list(range(P_ + S_ + V_))

            def find(i, par=par):
                while par[i] != i:
                    par[i] = par[par[i]]
                    i = par[i]
                return i

            def uni(i, j, par=par):
                a, b = find(i), find(j)
                if a != b:
                    par[a] = b

            for i, (px, py, prc, pl) in enumerate(pds):
                for j, s in enumerate(sgs):
                    if pl is not None and s[4] != pl:
                        continue          # an SMD pad only touches F.Cu
                    if _near(px, py, s[:4], 0.5, prc):
                        uni(i, P_ + j)
            # A via of this net bridges the two layers, and is the ONLY thing
            # that does; without it two pieces that merely cross are not joined.
            for k, (vx, vy) in enumerate(vis):
                for i, (px, py, _rc, _pl) in enumerate(pds):
                    if (px - vx) ** 2 + (py - vy) ** 2 < 0.36:
                        uni(i, P_ + S_ + k)
                for j, s in enumerate(sgs):
                    if _pdist(vx, vy, s[0], s[1], s[2], s[3]) < 0.3:
                        uni(P_ + j, P_ + S_ + k)
            # Segment to segment by real distance, not endpoint to endpoint.
            # Endpoint-to-endpoint misses a T -- one track starting halfway
            # along another -- which is how a tile's stub joins its rail, so
            # nearly every net inside a tile looked like two pieces.  About a
            # hundred nets that were already whole, and not one of them in the
            # ratsnest, were being handed to the router to "fix", which cost
            # half an hour a build and laid redundant copper in the gaps other
            # nets needed.
            for j in range(S_):
                for k in range(j + 1, S_):
                    if sgs[j][4] != sgs[k][4]:
                        continue          # crossing is not connecting
                    if _segdist(sgs[j][0], sgs[j][1], sgs[j][2], sgs[j][3],
                                sgs[k][0], sgs[k][1], sgs[k][2], sgs[k][3]) < 0.2:
                        uni(P_ + j, P_ + k)
            comps = {}
            for i in range(P_ + S_ + V_):
                comps.setdefault(find(i), []).append(i)
            # A via on its own is not a piece worth routing to -- it is always
            # part of something else -- so drop any component that is only vias.
            comps = {r: m for r, m in comps.items()
                     if any(i < P_ + S_ for i in m)}
            if len(comps) < 2:
                continue
            cpts = {}
            for r, mem in comps.items():
                pts = []
                for i in mem:
                    if i < P_:
                        pts.append((pds[i][0], pds[i][1], pds[i][3]))
                    elif i < P_ + S_:
                        s = sgs[i - P_]
                        pts.extend((qx, qy, s[4]) for qx, qy in _samples(s[:4]))
                cpts[r] = pts
            # A pad is blocked in the grid so OTHER nets keep away from it -- but
            # its own net has to be able to reach it, and every terminal here IS a
            # pad, sitting in the middle of its own blocking disc with no free
            # neighbour to step to.  That is why the first attempt failed all 118
            # joins.  Open this net's pads up, and close them again afterwards.
            if os.environ.get("RTPROG"):
                import sys as _pg
                print("    multi %-18s %d pieces" % (nm, len(comps)), file=_pg.stderr)
            g2 = build_g2(nm)
            order2 = sorted(cpts, key=lambda r: -len(cpts[r]))
            tree = _thin(list(cpts[order2[0]]))
            left = order2[1:]
            while left:
                best_r, best_a, best_d = None, None, 1e18
                for r in left:
                    for p in cpts[r]:
                        d = min(abs(p[0] - q[0]) + abs(p[1] - q[1]) for q in tree)
                        if d < best_d:
                            best_d, best_r, best_a = d, r, p
                # Start on the layer the source piece is actually on, and try
                # ending on each layer the tree actually offers, against only
                # the goals that live there.  Keep the cheaper of the two.
                sl = FCU if best_a[2] is None else best_a[2]
                path = None
                for el in (FCU, IN2):
                    goals = [(q[0], q[1]) for q in tree if q[2] in (el, None)]
                    if not goals:
                        continue
                    for tn in (None, 0.4):
                        kw = {} if tn is None else {"turn": tn}
                        cand = g2.route((best_a[0], best_a[1]), goals,
                                        layers=(FCU, IN2), start_layer=sl,
                                        end_layer=el, cap=CAP,
                                        strict_goals=True, **kw)
                        if cand and (path is None or len(cand) < len(path)):
                            path = cand
                        if cand:
                            break
                newsegs, newvias = [], []
                if path:
                    for i in range(len(path) - 1):
                        x0, y0, l0 = path[i]
                        x1, y1, l1 = path[i + 1]
                        if l0 != l1:
                            newvias.append((x0, y0))
                        elif (x0, y0) != (x1, y1):
                            newsegs.append((x0, y0, x1, y1, l0, w))
                    if not (path_clear(newsegs, nm) and
                            (not STRICT or vias_clear(newvias, nm))):
                        path = None
                if path:
                    for x0, y0 in newvias:
                        tile_vias.append((x0, y0, nm))
                        g2.block_disc(x0, y0, 0.75)
                    for x0, y0, x1, y1, l0, w0 in newsegs:
                        tracks.append((x0, y0, x1, y1,
                                       "In2.Cu" if l0 == IN2 else "F.Cu", nm, w0))
                        g2.block_seg(x0, y0, x1, y1, w0 / 2.0 + 0.5, l0)
                        tree.extend((qx, qy, l0)
                                    for qx, qy in _samples((x0, y0, x1, y1)))
                else:
                    pwr_fail.append(nm)
                tree.extend(cpts[best_r])
                tree = _thin(tree)
                left.remove(best_r)
            if os.environ.get("FASTGRID") and _fast.get("open") == nm:
                # Put this net's own copper back before moving to the next one.
                # What the pass ADDED during its routing stays blocked, which is
                # right: it is an obstacle for everything that follows.
                _fast["g"].add(_fast["cells"].get(nm, ()))
                _fast["open"] = None
        return pwr_fail

    # Rip-up and retry, which this pass did not have: it took each join once and
    # gave up, while the two-point router got six passes.  Everything the pass
    # adds goes onto `tracks`, so a retry means restoring the snapshot and
    # running the nets in a different order -- hardest first next time.
    # A way to try two-point routing orders without paying for the twenty
    # minutes the multi-terminal pass costs.
    if os.environ.get("RTSKIPMULTI"):
        import sys as _sk
        print("routed %d of %d off-block nets"
              % (len(jobs) - len(nfail), len(jobs)), file=_sk.stderr)
        print("  FAILED:", nfail, file=_sk.stderr)
        return out, placed, fps, boxes
    base_t2, base_v2 = list(tracks), list(tile_vias)
    best_pwr, order_m = None, list(MULTI)
    for attempt in range(0 if _NOROUTE else 3):
        _fast.clear()           # `tracks` is about to be restored; rebuild it
        if os.environ.get("RTPROG"):
            import sys as _pg
            print("  multi-terminal attempt %d of 3" % (attempt + 1), file=_pg.stderr)
        tracks[:] = list(base_t2)
        tile_vias[:] = list(base_v2)
        pwr_fail = _multi_pass(order_m)
        if best_pwr is None or len(pwr_fail) < len(best_pwr[2]):
            best_pwr = (list(tracks), list(tile_vias), list(pwr_fail))
        if not pwr_fail:
            break
        bad = set(pwr_fail)
        order_m = ([j for j in order_m if j[0] in bad] +
                   [j for j in order_m if j[0] not in bad])
    if best_pwr is None:
        best_pwr = (list(tracks), list(tile_vias), [])
    tracks[:], tile_vias[:] = best_pwr[0], best_pwr[1]
    pwr_fail = best_pwr[2]
    import sys as _sy
    print("multi-terminal: %d joins failed %s"
          % (len(pwr_fail), sorted(set(pwr_fail))), file=_sy.stderr)


    import sys as _s
    print("routed %d of %d off-block nets" % (len(jobs) - len(nfail), len(jobs)),
          file=_s.stderr)
    if nfail:
        print("  two-point pass left:", nfail, file=_s.stderr)

    # ---- an APPROXIMATE look at what is still in two pieces ---------------
    # Round 29.  The board printed "UNROUTED: PPS_05, PPS_03" on Cmts.User and
    # had done for several rounds, while KiCad's own filled DRC reported zero
    # unconnected items -- and KiCad was right.  `nfail` is what the TWO-POINT
    # pass gave up on, and the multi-terminal pass that runs after it takes
    # every net with more than one pad, so it had already finished both of
    # them.  Nothing ever went back and asked.
    #
    # So ask, once, at the end, with the same union-find the multi-terminal
    # pass uses: pads joined by segments they actually touch, segments joined
    # by real distance rather than endpoint to endpoint, and the two layers
    # joined only where this net has a via.  GND is excluded because it is
    # poured, not routed.
    #
    # THIS IS A DIAGNOSTIC AND NOT A VERDICT, and round 29 nearly repeated the
    # exact mistake it was fixing by treating it as one.  It is stricter than
    # KiCad's connectivity -- on the build that ships it calls three nets split
    # that KiCad, and a deliberately generous re-check against the finished
    # board file, both call whole.  So it prints, and it does NOT write a
    # caption onto the board: a board must not carry a claim that a better
    # check contradicts.  The verdict is KiCad's, and build.py step 5 refuses
    # to produce a release when it finds anything.
    def net_pieces(nm):
        pds = [(ax, ay, _rc, None if _t else FCU)
               for _r, _p, ax, ay, _t, net, _h, _rc in allpads if net == nm]
        if len(pds) < 2:
            return 1
        sgs = [(a0, b0, c0, d0, IN2 if l == "In2.Cu" else FCU)
               for a0, b0, c0, d0, l, n2, _w in tracks if n2 == nm]
        vis = [(vx, vy) for vx, vy, n2 in tile_vias if n2 == nm]
        NP, NS, NV = len(pds), len(sgs), len(vis)
        par = list(range(NP + NS + NV))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i

        def uni(i, j):
            a1, b1 = find(i), find(j)
            if a1 != b1:
                par[a1] = b1

        for i, (px_, py_, prc, pl) in enumerate(pds):
            for j, s in enumerate(sgs):
                if pl is not None and s[4] != pl:
                    continue
                if _near(px_, py_, s[:4], 0.7, prc):
                    uni(i, NP + j)
        for k, (vx, vy) in enumerate(vis):
            for i, (px_, py_, _rc2, _pl) in enumerate(pds):
                if (px_ - vx) ** 2 + (py_ - vy) ** 2 < 0.64:
                    uni(i, NP + NS + k)
            for j, s in enumerate(sgs):
                if _pdist(vx, vy, s[0], s[1], s[2], s[3]) < 0.4:
                    uni(NP + j, NP + NS + k)
        for j in range(NS):
            for k in range(j + 1, NS):
                if sgs[j][4] != sgs[k][4]:
                    continue
                if _segdist(sgs[j][0], sgs[j][1], sgs[j][2], sgs[j][3],
                            sgs[k][0], sgs[k][1], sgs[k][2], sgs[k][3]) < 0.3:
                    uni(NP + j, NP + k)
        comps = set()
        for i in range(NP):
            comps.add(find(i))
        return len(comps)

    split = [] if _NOROUTE else sorted(
        nm for nm in numof
        if nm and nm not in PLANE_NETS and not nm.startswith("unconnected-")
        and net_pieces(nm) > 1)
    print("approximate connectivity check (stricter than KiCad's, and NOT "
          "what gates the build): %d net(s) look split %s"
          % (len(split), split), file=_s.stderr)
    for x0, y0, x1, y1, lyr, nm, w in tracks[_ntracks0:]:
        out.append(track(x0, y0, x1, y1, lyr, numof[nm], "rt", w))
    for vx, vy, nm in tile_vias[_nvias0:]:
        out.append(via(vx, vy, numof[nm], "rv%s%g%g" % (nm, vx, vy)))

    # ---- the planes: GND on In1, +3V3_A on B.Cu (rev B item 5) -------------
    poly = [(0.3, 0.3), (G.BW - 0.3, 0.3), (G.BW - 0.3, G.BH - 0.3), (0.3, G.BH - 0.3)]
    out.append(zone(numof["GND"], "GND", "In1.Cu", poly, "GND-In1.Cu"))
    out.append(zone(numof["+3V3_A"], "+3V3_A", "B.Cu", poly, "+3V3_A-B.Cu"))
    # ...but not under a standoff.  Rev A's B.Cu was GND, so a metal standoff
    # or screw head on the bottom face touched nothing that mattered; rev B's
    # is +3V3_A, under nothing but solder mask, and the slot's standoff is the
    # one shared with the PYNQ (whose hole is ground).  Keep the pour 3.6 mm
    # from each hole's centre (an M3 standoff is 6.35 mm across its corners),
    # and 3.6 mm from the slot's axis along its 3.8 mm of travel.
    for i, ((mx, my), kind, _n) in enumerate(G.MOUNT):
        R_KO, half = 3.6, (0.0 if kind == "hole" else 1.9)
        ko = []
        for k in range(13):                       # right end, -90..+90 deg
            a = _m.radians(-90 + 15 * k)
            ko.append((mx + half + R_KO * _m.cos(a), my + R_KO * _m.sin(a)))
        for k in range(13):                       # left end, 90..270 deg
            a = _m.radians(90 + 15 * k)
            ko.append((mx - half + R_KO * _m.cos(a), my + R_KO * _m.sin(a)))
        out.append(pour_keepout("B.Cu", ko, "MH%d-B.Cu-keepout" % (i + 1)))
    # ...and a pour on F.Cu as well.  That is what actually clears the ground
    # ratsnest: 32 SMD ground pads never found room for a via, and a pad sitting
    # in a ground pour does not need one.  It costs a little capacitance on the
    # high-impedance squarer input -- roughly 0.3 pF over that node's 6 mm,
    # against the 0.7 pF it already has to the In1 plane 0.21 mm below -- which
    # is small beside the 5 pF the gate input presents anyway.
    # Solid pad connection, not thermal relief: this is a ground pour on a
    # signal layer, so the lower inductance is what you want, and the relief
    # spokes could not reach 15 of the crowded SOT-23-5 ground pads anyway.
    out.append(zone(numof["GND"], "GND", "F.Cu", poly, "GND-F.Cu", solid=True))

    # =======================================================================
    # THE SILKSCREEN
    # =======================================================================
    # Round 29 rewrote this, and the rewrite is mostly one idea: a label's
    # position is expressed in the frame of the THING IT LABELS, and it is
    # emitted once, at the end, when every other thing on the board is known.
    #
    # What that fixes, in the order round 29 was asked about it:
    #
    #  * A tile is stamped out thirteen times, at rot 90 down the left of the
    #    board and rot 270 down the right.  Every marker offset used to be in
    #    BOARD coordinates, so "1.5 mm to the right of the pad" meant "towards
    #    the helper" on one side and "away from it" on the other.  That is why
    #    the input test point's letter was beside its pad on the odd channels
    #    and underneath the SMA's ground post on the even ones, and why the
    #    heaters' H and the thermometers' T were scattered: the spiral that
    #    dodges pads found a different gap each time.  In the part's own frame
    #    the two sides are mirror images by construction, and a marker cannot
    #    drift away from the part it names, because it is placed FROM it.
    #  * The dodge radius is now 3 mm, not 9.  A letter 9 mm from its pad does
    #    not label that pad; it labels whatever it happens to have landed on.
    #  * Reference designators are placed by the same machinery, LAST, so the
    #    designator is what yields when it and a test-point letter want the
    #    same square millimetre.  Before this they sat wherever the stock
    #    footprint put them, which is how an `S` came to be buried under
    #    `R1204`, and how thirteen 560R heaters ended up with their names
    #    outside the box that contains them.
    #  * Obstacles live in a 5 mm bucket grid.  A linear scan was fine for
    #    sixty markers and is not for those plus 460 designators.
    ADV = 0.82                 # glyph advance / height, measured in round 21
    _dropped = []              # lines the board had no room for
    _OB = 5.0
    _obst = {}
    _nlost = []

    def obstruct(b, kind="ink"):
        for cx in range(int(_m.floor(b[0] / _OB)), int(_m.floor(b[2] / _OB)) + 1):
            for cy in range(int(_m.floor(b[1] / _OB)), int(_m.floor(b[3] / _OB)) + 1):
                _obst.setdefault((cx, cy), []).append((b[0], b[1], b[2], b[3], kind))

    # Two different margins, because they mean two different things.  0.18 mm
    # from a PAD is JLCPCB's 0.15 silkscreen-to-mask-opening rule with a
    # little to spare, and breaking it means the letter is scraped off.
    # 0.04 mm from other INK is only legibility: two labels that touch are
    # ugly, and KiCad calls that `silk_overlap`, which is a warning here.
    M_PAD, M_INK = 0.18, 0.12
    NEAR_SLACK = 0.3            # mm: a designator nearer its own part than any other
    # What a short label avoids, and what a line of prose avoids.  The
    # difference is the vias; see where they are added, below.
    ALL, PROSE = ("pad", "ink", "via"), ("pad", "ink")

    def hit(b, M=None, kinds=ALL):
        """The first obstacle this box runs into, or None."""
        q0, q1, q2, q3 = b[0] - M_PAD, b[1] - M_PAD, b[2] + M_PAD, b[3] + M_PAD
        for cx in range(int(_m.floor(q0 / _OB)), int(_m.floor(q2 / _OB)) + 1):
            for cy in range(int(_m.floor(q1 / _OB)), int(_m.floor(q3 / _OB)) + 1):
                for o in _obst.get((cx, cy), ()):
                    if o[4] not in kinds:
                        continue
                    e = (M_INK if o[4] == "ink" else M_PAD) if M is None else M
                    if (b[0] - e < o[2] and o[0] < b[2] + e
                            and b[1] - e < o[3] and o[1] < b[3] + e):
                        return o
        return None

    def blocked(b, M=None, kinds=ALL):
        return hit(b, M, kinds) is not None

    def adv(s, size):
        """How wide this string's ink really is, per character.

        0.82 is the AVERAGE advance measured in round 21 against KiCad's own
        bounding boxes, over prose.  A short all-capitals string is dominated
        by its widest glyphs instead, and using the average for one of those
        is how round 29's first pass put an `H` 0.07 mm inside the DS2482's
        pin 1 and still believed it was clear.
        """
        return size * (1.0 if len(s) <= 5 else 0.9)

    def ink(x, y, s, size, thick, just="left", angle=0):
        """Where a gr_text's ink actually lands.

        KiCad anchors left-justified text on the left edge and CENTRES it
        vertically; at angle 90 it reads UP the board, so the run goes from
        the anchor towards smaller y and the box turns with it."""
        w = len(s) * adv(s, size) + thick
        h = size + thick
        if angle:
            return (x - h / 2.0, y - w, x + h / 2.0, y)
        x0 = x - w if just == "right" else (x - w / 2.0 if just in (None, "center")
                                            else x)
        return (x0, y - h / 2.0, x0 + w, y + h / 2.0)

    def silk(x, y, s, size, thick, just="left", angle=0, layer="F.SilkS"):
        obstruct(ink(x, y, s, size, thick, just, angle))
        out.append(text(x, y, s, layer, size, thick, just=just, angle=angle))

    def spiral(step=0.5, rmax=3.0):
        pts = [(0.0, 0.0)]
        r = step
        while r <= rmax + 1e-9:
            n = max(8, int(2.0 * _m.pi * r / step))
            for k in range(n):
                a = 2.0 * _m.pi * k / n
                pts.append((r * _m.cos(a), r * _m.sin(a)))
            r += step
        return pts

    def to_board(rot, lx, ly):
        a = _m.radians(-rot)
        ca, sa = _m.cos(a), _m.sin(a)
        return (lx * ca - ly * sa, lx * sa + ly * ca)

    def to_local(rot, bx, by):
        a = _m.radians(rot)
        ca, sa = _m.cos(a), _m.sin(a)
        return (bx * ca - by * sa, bx * sa + by * ca)

    def place_text(cx, cy, s, size, thick, tries=None, angle=0, force=True,
                   within=None):
        """`s` CENTRED on (cx, cy), nudged by the first offset that is clear.

        Returns the anchor used, or None when nothing was clear and force is
        off -- which is how a reference designator decides to give up and move
        itself to the fabrication layer instead of printing on a pad.
        within: a predicate on the ink box; a candidate it rejects is not
        clear (round 41: a unit's labels stay inside the unit's box)."""
        w = len(s) * adv(s, size) + thick
        for dx, dy in (tries or spiral()):
            x = cx + dx - (0.0 if angle else w / 2.0)
            y = cy + dy + (w / 2.0 if angle else 0.0)
            b = ink(x, y, s, size, thick, "left", angle)
            if not blocked(b) and (within is None or within(b)):
                silk(x, y, s, size, thick, angle=angle)
                return (x, y)
        if not force:
            return None
        x = cx - (0.0 if angle else w / 2.0)
        y = cy + (w / 2.0 if angle else 0.0)
        silk(x, y, s, size, thick, angle=angle)
        return (x, y)

    def place_in(x0, y0, x1, y1, s, size, thick, step=0.5, xpref=None):
        """Put this line ANYWHERE inside the rectangle that is clear.

        Round 29's "you'll need to sprinkle text between components".  A
        spiral round a guessed point is the wrong tool for a line of prose:
        it either finds the gap immediately or walks somewhere misleading.
        Naming the region it may live in and scanning that is both more
        honest about what is being asked and easier to get right."""
        w, h = len(s) * adv(s, size) + thick, size + thick
        y, last = y0 + h / 2.0, None
        while y <= y1 - h / 2.0 + 1e-9:
            # A line under another line starts at the same x if it can: a
            # stack of ragged left edges reads as three unrelated labels,
            # which is what "HELPER / Clock / Distribution" looked like when
            # each line found its own first clear column.
            if xpref is not None and x0 <= xpref <= x1 - w:
                if hit((xpref, y - h / 2.0, xpref + w, y + h / 2.0),
                       kinds=PROSE) is None:
                    silk(xpref, y, s, size, thick)
                    return (xpref, y)
            x = x0
            while x <= x1 - w + 1e-9:
                q = hit((x, y - h / 2.0, x + w, y + h / 2.0), kinds=PROSE)
                if q is None:
                    silk(x, y, s, size, thick)
                    return (x, y)
                last = q
                x += max(step, q[2] - x)      # step past what we just hit
            y += step
        place_in.why = ("needs %.1f x %.1f; last hit %s (%.1f,%.1f)-(%.1f,%.1f)"
                        % ((w, h) + (last[4],) + last[:4]) if last else
                        "region smaller than the text")
        return None

    def stack_in(x0, y0, x1, y1, lines, gap=0.7):
        """A run of lines down a region, each below and left-aligned with the
        one above it where the board allows."""
        top, xp = y0, None
        for s, size, thick in lines:
            got = place_in(x0, top, x1, y1, s, size, thick, xpref=xp)
            if got is not None and xp is None:
                xp = got[0]
            if got is None:
                import sys as _si
                _dropped.append(s)
                print("SILK: no room for %r in (%g,%g)-(%g,%g): %s"
                      % (s, x0, y0, x1, y1,
                         getattr(place_in, "why", "?")), file=_si.stderr)
                continue
            top = got[1] + (size + thick) / 2.0 + gap

    def part_text(ref, ldx, ldy, s, size, thick, rmax=3.0, angle=0, alts=()):
        """A label at a fixed offset in the PART's own frame.

        The preferred offset, then the alternates (also in the part's frame,
        so they mirror with it), each with a small spiral round it.  Only if
        every one of them is on copper does it print at the preferred spot
        anyway -- a clipped letter beside the right part still points at the
        right part, and moving it further away would not.

        ROUND 31.  "Anyway" has one exception: OFF THE BOARD is not a clipped
        letter, it is no letter.  U5005 and U5004 sit hard against the left
        and right edges, and the forced fallback put their T at x = 0.75,
        whose ink runs off the edge at x = -0.06.  So the fallback picks the
        first candidate that is at least ON the board, and only then the
        preferred one."""
        if ref not in placed:
            return
        px, py, prot = placed[ref]
        w = len(s) * adv(s, size) + thick

        def keep(at):
            """Remember what was printed for whom, for check_owned()."""
            if at:
                _owned.append((ref, s, ink(at[0], at[1], s, size, thick,
                                           "left", angle)))
            return at

        def mine(b):
            return inside_home(ref, b)

        cands = ((ldx, ldy),) + tuple(alts) + ((-ldx, -ldy),)
        for ax, ay in cands:
            bx, by = to_board(prot, ax, ay)
            if keep(place_text(px + bx, py + by, s, size, thick,
                               spiral(0.45, rmax), angle=angle, force=False,
                               within=mine)):
                return
        # Nothing clear near the part: a wider search, still inside the box.
        for ax, ay in cands:
            bx, by = to_board(prot, ax, ay)
            if keep(place_text(px + bx, py + by, s, size, thick,
                               spiral(0.45, 2.0 * rmax), angle=angle,
                               force=False, within=mine)):
                return
        for ax, ay in cands:
            bx, by = to_board(prot, ax, ay)
            b = ink(px + bx - (0.0 if angle else w / 2.0),
                    py + by + (w / 2.0 if angle else 0.0), s, size, thick,
                    "left", angle)
            if (b[0] > 0.3 and b[1] > 0.3 and b[2] < G.BW - 0.3
                    and b[3] < G.BH - 0.3 and mine(b)):
                keep(place_text(px + bx, py + by, s, size, thick, [(0.0, 0.0)],
                                angle=angle))
                return
        bx, by = to_board(prot, ldx, ldy)
        keep(place_text(px + bx, py + by, s, size, thick, [(0.0, 0.0)],
                        angle=angle))

    # ---- every pad on the board is an obstacle ----------------------------
    for _r, _pn, _ax, _ay, _tht, _net, _hd, _rc in allpads:
        hw, hh, pang = _rc
        if round(pang) % 180:
            hw, hh = hh, hw
        if _hd:
            hw, hh = max(hw, _hd / 2.0), max(hh, _hd / 2.0)
        obstruct((_ax - hw, _ay - hh, _ax + hw, _ay + hh), "pad")
    # ...and every via, but as its own SOFT class.  These vias are tented --
    # no tenting property is set, so they take the board default, and the
    # experiment that settles it is to drop a `gr_text` on one and run the
    # DRC: zero violations.  So ink over a via is not a manufacturing fault
    # and `silk_over_copper` does not fire on it.  It is still worth avoiding
    # for a single letter or a designator, which can move a third of a
    # millimetre and be clear; it is not worth avoiding for a 35 mm sentence,
    # which cannot.  Round 29's second build treated them as hard obstacles
    # and lost the title, the author line and the test-point legend heading
    # off the board entirely, because after routing there is no 35 mm row in
    # the bottom-right corner with no via in it.
    for _vx, _vy in vias:
        obstruct((_vx - 0.35, _vy - 0.35, _vx + 0.35, _vy + 0.35), "via")
    for _vx, _vy, _n in tile_vias:
        obstruct((_vx - 0.35, _vy - 0.35, _vx + 0.35, _vy + 0.35), "via")
    # ...and so is the board edge, so nothing prints off it
    for _e in ((-2.0, -2.0, G.BW + 2.0, 0.3), (-2.0, G.BH - 0.3, G.BW + 2.0, G.BH + 2.0),
               (-2.0, -2.0, 0.3, G.BH + 2.0), (G.BW - 0.3, -2.0, G.BW + 2.0, G.BH + 2.0)):
        obstruct(_e, "pad")

    def silk_edge(x0, y0, x1, y1, w=0.15):
        """One side of a silkscreen box, BROKEN wherever it would cross a pad.

        A region box is only worth drawing if it can be drawn without ink on
        a solder-mask opening, and around 460 parts there is always somewhere
        it cannot.  Breaking it there costs nothing to read and is what the
        fab would have done anyway, except that the fab breaks it wherever it
        likes and does not tell you."""
        n = max(2, int(_m.hypot(x1 - x0, y1 - y0) / 0.4) + 1)
        run, runs = None, []
        for k in range(n + 1):
            px, py = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
            if blocked((px, py, px, py), 0.3, PROSE):
                if run:
                    runs.append(run)
                run = None
            else:
                run = (run[0], run[1], px, py) if run else (px, py, px, py)
        if run:
            runs.append(run)
        for a0, b0, a1, b1 in runs:
            if _m.hypot(a1 - a0, b1 - b0) < 1.0:
                continue
            out.append(line(a0, b0, a1, b1, "F.SilkS", w))
            obstruct((min(a0, a1) - w, min(b0, b1) - w,
                      max(a0, a1) + w, max(b0, b1) + w))

    def silk_box(x0, y0, x1, y1, w=0.15):
        silk_edge(x0, y0, x1, y0, w)
        silk_edge(x1, y0, x1, y1, w)
        silk_edge(x1, y1, x0, y1, w)
        silk_edge(x0, y1, x0, y0, w)

    # ---- one box round each input circuit ---------------------------------
    # A FIXED rectangle centred on its own SMA, not the bounding box of its
    # contents: sizing to contents is what put the 1 pps jack off to one side
    # of its own rectangle, because that half has parts out to +5.5 mm and
    # only -4.4.  A fixed rectangle also makes a unit's two boxes read as a
    # pair and gives the gutter a constant width for the rail.
    colbox = {}
    ubox = {}                  # (unit, "10m" | "pps") -> its box, board coords
    for u in sorted(byunit):
        f, _ = xf(u)
        todo = [("10m", T.BOX_10M)]
        if byunit[u].get("U04"):
            todo.append(("pps", T.pps_box()))
        for kind, (bx0, by0, bx1, by1) in todo:
            cs = [f(bx0, by0), f(bx1, by0), f(bx1, by1), f(bx0, by1)]
            r = (min(c[0] for c in cs), min(c[1] for c in cs),
                 max(c[0] for c in cs), max(c[1] for c in cs))
            ubox[(u, kind)] = r
            silk_box(*r)
            k = (kind, "L" if r[0] < G.XC else "R")
            e = colbox.get(k)
            colbox[k] = ((min(e[0], r[0]), min(e[1], r[1]),
                          max(e[2], r[2]), max(e[3], r[3])) if e else r)

    # ROUND 41.  Everything that belongs to a unit's box -- its parts, their
    # designators and the letters beside its test points -- must print INSIDE
    # that box.  The tiles are rotated 90 or 270, so a tile's power gutter
    # faces the neighbouring unit, and a label pushed out of it used to land
    # in the next box: FB401 in unit 6's, unit 2's R203/C203/C207 in unit 4's,
    # FB204/C209/R208 outside P2 altogether, 71 designators in all on rev A.
    # The placement searches below only accept positions inside home_of(ref),
    # and check_owned() refuses to finish a board that has one outside.
    BOX_MARGIN = 0.3           # clear of the box's own 0.15 mm line
    _owned = []                # (ref, what, ink box) for check_owned()

    def home_of(ref):
        u, slot = unit_of(ref)
        if not u:
            # A tile's own heater (R2001-R2013) belongs to the power sheet but
            # lives in its tile's 10 MHz box.  With no home its designator was
            # free to go anywhere, and on eight units it went into the NEXT
            # unit's box (2026-10-10; Jason: "labels for one unit showed up in
            # another unit's box" -- round 41's problem by another route).
            if is_heater(ref) and ref in placed:
                hx, hy = placed[ref][0], placed[ref][1]
                for (_u, kind), bx in sorted(ubox.items()):
                    if kind == "10m" and bx[0] <= hx <= bx[2] and bx[1] <= hy <= bx[3]:
                        return bx
            return None
        kind = ("10m" if slot in T.PARTS_10M else
                "pps" if slot in T.PARTS_PPS else None)
        return ubox.get((u, kind)) if kind else None

    def inside_home(ref, b):
        hb = home_of(ref)
        if hb is None:
            # No box of its own, so in nobody else's either: a ring heater's
            # H touched unit 3's pps box (2026-10-10).
            return not any(b[0] < v[2] + BOX_MARGIN and v[0] - BOX_MARGIN < b[2]
                           and b[1] < v[3] + BOX_MARGIN and v[1] - BOX_MARGIN < b[3]
                           for v in ubox.values())
        return (b[0] >= hb[0] + BOX_MARGIN and b[1] >= hb[1] + BOX_MARGIN
                and b[2] <= hb[2] - BOX_MARGIN and b[3] <= hb[3] - BOX_MARGIN)

    # ---- a box round each named region ------------------------------------
    # Round 29.  "HELPER", "POWER", "HOUSEKEEPING" and "1-WIRE" were four
    # words floating near four groups of parts, and the only boxes were on
    # Cmts.User, which is not printed and which nobody holding the board can
    # see.  Each box is now the extent of the parts that ARE in that region --
    # read from `placed`, so it cannot describe a group that has moved.
    def region(refs, pad=1.3):
        bs = [boxes[r] for r in refs if r in boxes]
        if not bs:
            return None
        return (min(b[0] for b in bs) - pad, min(b[1] for b in bs) - pad,
                max(b[2] for b in bs) + pad, max(b[3] for b in bs) + pad)

    REGIONS = {
        # U5007 and its filter are the fan-out's own thermometer, at its
        # foot (rev B item 20): inside the box, not hanging under its edge.
        "helper": sorted(H.PARTS) + ["J3001", "J3002",
                                     "U5007", "R5057", "C5013", "C5014"],
        "power": sorted(PW.PARTS),
        "house": sorted(blockrefs.get("house", [])) + ["U5009", "R5059",
                                                       "C5017", "C5018"],
        # ROUND 31.  The box is drawn round what the LABEL names -- the five
        # screw terminals you wire external probes into, their ten series
        # resistors, and the bus's own pull-up, diode and test point.  The
        # DS2482 bridge and its decoupling sit below it and are deliberately
        # outside: including them dragged the bottom edge down to y = 30.5,
        # which is past the "10 MHz IN" heading of the column beneath, so the
        # heading read as part of the 1-Wire block.  A bridge is not an
        # external thermometer, and this is the honest place to draw the line.
        "probes": (sorted(blockrefs.get("probes", []))
                   + ["J600%d" % (i + 1) for i in range(5)]
                   + ["R60%02d" % n for n in range(2, 12)]
                   + ["R6051"]),
    }
    rboxes = {}
    for _name, _refs in sorted(REGIONS.items()):
        r = region(_refs)
        if not r:
            continue
        rboxes[_name] = (max(r[0], 1.0), max(r[1], 1.0),
                         min(r[2], G.BW - 1.0), min(r[3], G.BH - 1.0))
    # The BOXES themselves are drawn at the end of this function, after every
    # label -- a region border breaks round anything already printed, which is
    # how the region's own name comes to sit in a gap in its own border
    # instead of being pushed out of the region it names.
    #
    # ROUND 31.  A box is invisible to a label placed BEFORE it, which is how
    # the left column's "10 MHz IN" came to sit inside the 1-Wire box at
    # y = 28.2 with its own sub-heading outside it at 31.8.  Reserving all
    # four edges of every region here fixes that and costs more than it is
    # worth -- it moved the bench-post warning off its own strip and onto the
    # GND label, and lost C1006's designator.  Containment is only a problem
    # for the labels that scan a tall strip, so it is handled there: see the
    # column headings below.

    # ---- the big labels ---------------------------------------------------
    def region_label(name, x0, y0, x1, y1, size=1.9, thick=0.32):
        stack_in(x0, y0, x1, y1,
                 [(s, size, thick) for s in LB.REGION[name]], gap=0.2)

    hb = rboxes.get("helper")
    if hb:
        # In the free column between the two helper SMAs and the block below
        # them -- U5007, the helper's OWN thermometer, sits on the centre line
        # at y = 25 with a bead and two capacitors under it, so the label goes
        # to the left of that column, inside the band.
        region_label("helper", hb[0] + 0.8, 15.3, hb[2] - 0.8, 30.0, 1.3, 0.22)
    pb = rboxes.get("power")
    if pb:
        # "Up and to the left" (round 29): it was BELOW the block and read as
        # a caption for the bench posts rather than a name for the region.
        region_label("power", pb[0] + 1.0, pb[1] + 0.5, pb[0] + 30.0,
                     pb[1] + 12.0, 2.0, 0.34)
    kb = rboxes.get("house")
    if kb:
        # Above the block as well as inside it: the housekeeping region is
        # only 14 mm wide (two resistors, the DAC and its decoupling) and its
        # name is 12.8 of them, so the row it needs is usually the clear band
        # just above.  The border is drawn afterwards and breaks round it.
        region_label("house", kb[0] - 1.0, kb[1] - 7.0, kb[0] + 28.0,
                     kb[1] + 10.0, 1.3, 0.22)

    # ---- the 1-Wire screw terminals ---------------------------------------
    # W1..W5, not P1..P5: the 1 pps jacks are P1..P12, and two connectors
    # thirteen rows apart carrying the same five names is a real trap when
    # someone is reading a wiring note off the board.
    probe_pads = []
    for i in range(5):
        pr = "J600%d" % (i + 1)
        if pr not in placed:
            continue
        silk(placed[pr][0] - 1.7, 2.6, LB.PROBE_TAG(i + 1), 1.6, 0.28)
        dd, nm = fpof[pr]
        probe_pads.append(sorted(P.pads(dd, nm, *placed[pr]), key=lambda q: q[0]))
    # A wire colour against every screw: five identical three-way blocks and
    # fifteen wires in your hand is exactly when you want it on the board.
    for pd in probe_pads:
        for pn, ax, ay, _t, _h, _rc in pd:
            lab = {"1": "yel", "2": "red", "3": "blk"}.get(pn)
            if lab:
                place_text(ax, 16.6, lab, 1.0, 0.16,
                           spiral(0.5, 3.5), angle=90)
    # ROUND 31: two lines, colours on top, and every number here is measured
    # off the board rather than eyeballed, because the strip they have to fit
    # in is 1.28 mm tall and the text is 1.18.
    #
    #   the fifteen rotated colour tags above end at y = 18.18
    #   R6003/5/7/9/11's pads run y 18.21..19.61, five columns the line
    #     would otherwise cross -- so its ink starts at 19.79, a pad
    #     clearance below them
    #   R6001, D6001 and TP6001 start at y = 21.25, so its ink ends by 21.07
    #   FB6001's lower pad is x 12.8..14.2, so the line starts at 14.5
    #
    # That is the line you want under your eyes while you are screwing wires
    # down, and it is why it is 1.0 mm text: 1.1 does not fit.
    #
    # x1 = 71.0 KEEPS IT INSIDE THE BOX, whose right edge is at 71.55.  Round
    # 31's first attempt allowed 77.0, the line found no room in the strip and
    # fell through to the whole-board fallback, and it printed at x = 69.2
    # running 28 mm past the edge it was supposed to stay inside -- breaking
    # that edge in the same place the single long line used to, which was the
    # whole complaint.
    #
    # The region's NAME goes below it, in the band east of the three packed
    # parts (they occupy x 12..32 at y 21..23).
    if not place_in(14.5, 19.8, 71.0, 21.1, LB.PROBE_COLOURS, 1.0, 0.18):
        place_in(4.0, 19.0, G.BW - 4.0, 34.0, LB.PROBE_COLOURS, 1.0, 0.18)
    if not place_in(33.5, 21.4, 70.5, 24.3, LB.PROBE_HEADING, 1.1, 0.18):
        place_in(4.0, 19.0, G.BW - 4.0, 34.0, LB.PROBE_HEADING, 1.1, 0.18)

    # ---- every jack named, beside the unit it belongs to -------------------
    for x, y, tag, _desc in G.sma_rows():
        if tag in G.HELPER_SMA:
            continue          # named by the loop below, with their own offset
        if tag.startswith("P"):
            # ABOVE its box, in the 6 mm gutter between pps boxes.  At y - 6.4
            # the label straddled the box's own top edge, because a pps box is
            # only 11.8 mm tall against the 10 MHz box's 16.8.
            silk(x - 3.0, y - 7.6, tag, 2.4, 0.4)
        else:
            silk(x - 3.0, y - 6.4, tag, 2.4, 0.4)
    for tag, ref in (("HIN", "J3002"), ("HO", "J3001")):
        if ref in placed:
            silk(placed[ref][0] - 3.5, placed[ref][1] - 6.4, tag, 2.0, 0.34)


    # ---- what may be applied to each COLUMN of jacks -----------------------
    # Round 29.  The board said what each test point should show and never
    # said what you are allowed to plug in.  Two lines above each column, the
    # first one deliberately bigger than the 2.4 mm jack numbers, because it
    # is the line that stops someone putting 8 Vpp into an unterminated
    # ZED-F9T channel.
    for (kind, _side), r in sorted(colbox.items()):
        head, sub = (LB.col_head_pps() if kind == "pps" else LB.col_head_10m())
        # The strip above the column's topmost box, which already holds that
        # jack's own number: stack_in finds the rows that are left.  The top
        # of the strip stops below any REGION BOX the column passes under, or
        # the heading lands inside that box and reads as part of it -- round
        # 31, "10 MHz IN" sitting inside the 1-Wire terminal's box.
        ytop = r[1] - 10.0
        for _b in rboxes.values():
            if _b[0] < r[2] and r[0] < _b[2] and _b[3] < r[1]:
                ytop = max(ytop, _b[3] + 0.7)
        stack_in(r[0], ytop, r[2], r[1] - 0.6,
                 [(head, 3.0, 0.44), (sub, 1.25, 0.22)], gap=1.1)

    # ---- test-point letters ------------------------------------------------
    # In the TILE's frame, which for a part at rot 0 in tile.py IS the part's
    # own frame, so one offset serves both sides of the board.
    TP_OFF = {"TP_IN": (2.7, 0.0), "TP_SQ": (2.5, 0.0),
              "TP_BEAT": (1.7, 1.9), "TP_PPS": (1.9, 1.5)}
    for r in sorted(placed):
        if not r.startswith("TP"):
            continue
        v = vals.get(r, "")
        L = LB.TP_LETTER.get(v)
        if not L:
            continue
        sz = 1.3 if len(L) > 1 else 1.5
        dx, dy = TP_OFF.get(v, (2.2, 0.0))
        part_text(r, dx, dy, L, sz, 0.26, rmax=2.2,
                  alts=((dy, -dx), (-dy, dx)))

    # ---- what each monitor tap carries (rev B item 19) ----------------------
    # A U.FL has no pin names to read.  Every tap is NAMED beside it and its
    # designator stays off the silk (below): "J103" reads as a jumper
    # (Jason's rule from ECP5-2ADC-2DAC, CLAUDE_PCB.md).  The tiles' own
    # "TAP IN" jacks get "TAP" where their J number used to try to go -- on
    # ten of the thirteen units that J number had found no room and the jack
    # carried no label at all (2026-10-10).
    TAP_NAME = {"TAP +5V": "+5V", "TAP +3V3_A far": "+3V3_A", "TAP +3V3_D": "+3V3_D",
                "TAP REF": "REF", "TAP CLK0": "CLK0", "TAP HELPER": "HCLK",
                "TAP IN": "TAP"}
    _tapless = []
    for r in sorted(placed):
        L = TAP_NAME.get(vals.get(r, "")) if r.startswith("J") else None
        if L == "TAP":
            # Small, upright, and tight against the jack on its SMA side --
            # the same side in the TILE's frame on both columns, and away from
            # JP01.  A first try let part_text range 8 mm, and on the
            # right-hand units "TAP" landed on JP01's top edge, where it reads
            # as the jumper's setting.  Nowhere near the jack: no label.
            _u, _slot = unit_of(r)
            _rot = TILE[_slot][2]
            px_, py_, prot_ = placed[r]
            at = None
            # The tile's y axis is across the board (the tiles stand at 90 and
            # 270); the U.FL's courtyard is 2.5 mm each side of it.  The SMA
            # side first on both columns, over a tented via if need be (the
            # right-hand units have a ground via there; ink on a tented via is
            # legal, as for designators) -- only then the jumper side.
            # 0.8 x 0.16: JLCPCB's minimum height and the board's minimum silk
            # stroke (0.155), the same as a designator.
            w_ = len(L) * adv(L, 0.8) + 0.16
            for ty, kinds in ((-3.2, ALL), (-3.2, PROSE), (3.2, ALL)):
                bx, by = to_board(prot_, *to_local(_rot, 0.0, ty))
                for ddx, ddy in spiral(0.15, 0.6):
                    ax_, ay_ = px_ + bx + ddx, py_ + by + ddy + w_ / 2.0
                    bb = ink(ax_, ay_, L, 0.8, 0.16, "left", 90)
                    if not blocked(bb, kinds=kinds) and inside_home(r, bb):
                        silk(ax_, ay_, L, 0.8, 0.16, angle=90)
                        _owned.append((r, L, bb))
                        at = (ax_, ay_)
                        break
                if at:
                    break
            if not at:
                _tapless.append(r)
        elif L:
            part_text(r, 0.0, 3.7, L, 1.2, 0.22, rmax=2.0,
                      alts=((3.9, 0.0), (-3.9, 0.0)))

    # ---- a pin-1 dot where the footprint forgot one ------------------------
    # ROUND 35.  Every other package on this board marks pin 1 with a filled
    # triangle -- SOT-23-5, SOT-23-6, SOT-223, SOIC-8 and MSOP-10 all carry
    # one.  KiCad's Oscillator_SMD_Fox_FT5H_5.0x3.2mm carries NONE.  What it
    # has instead is an outline drawn as four disconnected stubs, and the two
    # nearest the NORTH-EAST corner (a 2.2 mm north edge and a 0.7 mm east
    # cap) look far more like a right-angle pin-1 bracket than the two real
    # pin-1 tails do, which are 0.45 and 0.50 mm and sit at the SOUTH-WEST.
    #
    # That cost two rounds of "does X3001 need another 180 degrees?" against
    # a part where 180 degrees out puts the 25 MHz output and +3V3 onto the
    # two GND pads.  A 0.8 mm filled dot outside the courtyard, beside pad 1,
    # costs nothing and ends the question.
    for _r in sorted(placed):
        if _r not in fpof or _r not in vals:
            continue
        _dd, _nm = fpof[_r]
        if "FT5H" not in _nm:
            continue
        _px, _py, _prot = placed[_r]
        _p1 = [q for q in P.pads(_dd, _nm, _px, _py, _prot) if q[0] == "1"]
        if not _p1:
            continue
        _ax, _ay = _p1[0][1], _p1[0][2]
        # Outward from the part centre, through pad 1, past the courtyard --
        # then along each axis, then a small spiral.  Vias do not count: the
        # dot is 0.8 mm of ink over a tented via, which round 29 established
        # DRCs clean, and insisting on via-free ink is what left this with no
        # room at all on the first try.
        _vx, _vy = _ax - _px, _ay - _py
        _l = _m.hypot(_vx, _vy) or 1.0
        _ux, _uy = _vx / _l, _vy / _l
        _cands = [(_px + _ux * (_l + _d), _py + _uy * (_l + _d))
                  for _d in (1.55, 1.9, 2.25)]
        _cands += [(_ax + _ux * 1.6, _ay), (_ax, _ay + _uy * 1.6),
                   (_ax + _ux * 2.1, _ay), (_ax, _ay + _uy * 2.1)]
        _cands = [(x + dx, y + dy) for x, y in _cands
                  for dx, dy in spiral(0.4, 1.2)]
        for _cx, _cy in _cands:
            if not blocked((_cx - 0.5, _cy - 0.5, _cx + 0.5, _cy + 0.5),
                           kinds=PROSE):
                out.append(gr("gr_circle", A("center", _cx, _cy),
                              A("end", _cx + 0.4, _cy),
                              A("stroke", A("width", 0.16), A("type", "solid")),
                              A("fill", "yes"), A("layer", S("F.SilkS")),
                              A("uuid", S(uid("p1dot", _r)))))
                obstruct((_cx - 0.45, _cy - 0.45, _cx + 0.45, _cy + 0.45))
                sys.stderr.write("SILK: pin-1 dot for %s at (%.2f, %.2f)\n"
                                 % (_r, _cx, _cy))
                break
        else:
            sys.stderr.write("SILK: NO ROOM for a pin-1 dot on %s\n" % _r)

    # ---- H on every heater, T on every thermometer -------------------------
    # Both derived from the placement, in the part's own frame, so an `H`
    # cannot end up beside a different heater -- or, as round 28's board had
    # it, under a DMN6068 six millimetres away.
    #
    # A 2010 heater is 6.5 x 3.2: -5.5 in its own x is 2.3 mm off its end.
    # In a tile that is along the channel, into the empty strip between the
    # heater and the flip-flops; in a margin it is inboard, away from the
    # board edge.  The two come out the same because the heaters are placed
    # as mirror images in the first place.
    # FOUR digits, not "starts with R20".  Round 28 tested `r.startswith("R20")`
    # and `r.startswith("U50")`, and this board numbers a channel's own parts
    # `R201`..`R208` for unit 2 and `U501`..`U504` for unit 5 -- so unit 2's
    # eight resistors each got an `H` and unit 5's four gates each got a `T`.
    # Twelve markers naming parts that are not heaters or thermometers, in the
    # middle of two channel tiles.  That is round 29's "random H's scattered
    # around" and "the T labels are not always next to their thermometers":
    # they were never near a heater or a thermometer at all.
    # And only R2001-R2024: R2025/R2026 are the LDO_EN pair and rev B's
    # R2027-R2029 the rail taps (item 19), none of them a heater.
    for r in sorted(placed):
        if is_heater(r):
            part_text(r, -5.5, 0.0, "H", 1.5, 0.26, rmax=2.2,
                      alts=((0.0, 3.2), (0.0, -3.2)))
        elif re.match(r"^U500[1-8]$", r):
            # ROUND 31.  Where this letter goes is fixed by three numbers,
            # all measured off the board rather than guessed:
            #
            #   the SOIC-8's pads reach 3.45 mm either side of its centre
            #   its bead and its two capacitors are at -5.0, +4.2 and +7.0
            #     in y, so there is no 1.7 mm row above or below it
            #   the 1 pps jack names are a column of 2.4 mm text at x = 13
            #     and x = 188, and the thermometers are at 6.5 and 200.5
            #
            # 4.2 mm out put the T on the pads; the dodge then walked it
            # inboard, where the only free space is the gap between the
            # thermometer and the jack column -- so U5003's T landed 0.9 mm
            # from "P7" and U5002's 1.8 mm from "P2", and a lone capital
            # letter that close to a jack number reads as part of it.
            #
            # OUTBOARD is the answer, and it is the one place nothing else
            # wants: the strip between the board edge and the thermometer is
            # 2.75 mm wide, holds nothing, and is on the opposite side from
            # the jack names.  4.8 centres the letter in it -- 0.89 mm off the
            # edge, 0.54 mm off the nearest pad.  Every thermometer's local
            # -x faces outboard, because the two margins are placed as mirror
            # images; the alternates walk along that strip before the last
            # resort turns back inboard.
            part_text(r, -4.8, 0.0, "T", 1.7, 0.3, rmax=1.2,
                      alts=((-4.8, 2.9), (-4.8, -2.9), (5.2, 0.0)))

    # ---- title, author and the key -----------------------------------------
    # Round 21 moved this whole band out of the bottom-left, where the legend
    # crossed forty rotated header names and the title ran through the debug
    # header's seven.  Round 29 moves the title and author to join it, because
    # the bottom-left corner now has a mounting hole in it.
    # x 141..196, y 151..169 is the one rectangle in the bottom band with
    # nothing in it: unit 12's 10 MHz box stops at y = 151.2, the right margin
    # heater R2019 starts at x = 197, and the socket's rotated pin names start
    # at y = 169.2.  Round 21 found it for the legend; round 29 moves the
    # title and the author line here too, because the bottom-left corner they
    # used to sit in now has a mounting hole 3 mm from the first glyph.
    LX1, LX2, LY0 = 141.0, 176.0, 151.0
    stack_in(LX1, LY0, 196.0, LY0 + 6.6,
             [("GPSDO DDMTD FRONT END   rev %s" % D.REV, 1.5, 0.26),
              ("Jason Gallicchio   jason@hmc.edu   %s" % D.DATE, 1.05, 0.18),
              ("TEST POINTS - the letter beside each pad", 1.1, 0.18)], gap=0.35)
    ca, cb = LB.legend_columns()
    for lx, col in ((LX1, ca), (LX2, cb)):
        stack_in(lx, LY0 + 6.6, lx + 33.0, LY0 + 13.4,
                 [(s, 1.0, 0.17) for s in col], gap=0.35)
    stack_in(LX1, LY0 + 13.4, 196.0, LY0 + 18.4,
             [(s, 0.95, 0.17) for s in LB.jack_key() + LB.helper_key()],
             gap=0.3)

    # ---- the 2x20 socket ---------------------------------------------------
    px, py = G.hdr_pin(1)
    silk(px + 2.6, py + 1.3, "1", 1.6, 0.3)
    # Round 29: HALF the names above and half below, each beside its own row.
    # Both rows used to be named above the socket, 1.27 mm apart, which is a
    # forty-name thicket over the odd row and nothing at all over the even one
    # -- and the reader still has to count to find out which of two adjacent
    # names belongs to the pin under their probe.
    for pinno in range(1, 41):
        gx, gy = G.hdr_pin(pinno)
        nm = _short(D.HEADER[pinno][0])
        silk(gx, 171.5 if pinno % 2 else 179.3, nm, 0.9, 0.16, angle=90)
    # The strip below the even row of pin names, right of the socket.
    place_in(163.0, G.BH - 3.4, G.BW - 1.0, G.BH - 0.6,
             "RPi 2x20 SOCKET, UNDERSIDE", 1.3, 0.22)
    # Round 22.  This board needs NO modification to a PYNQ-Z2, but it takes
    # the whole Raspberry Pi header, and the manual says of that header: "28
    # Total FPGA I/O (8 pins are shared with Pmod A)".  We use all 28, so all
    # 8 of Pmod A's I/O balls are ours -- checked ball by ball.
    stack_in(G.BW - 46.0, G.BH - 11.0, G.BW - 1.0, G.BH - 3.4,
             [("PMOD A IS UNUSABLE WITH THIS BOARD ON:", 1.0, 0.16),
              ("ITS 8 I/O ARE THIS HEADER'S", 1.0, 0.16)], gap=0.35)

    # ---- the debug header --------------------------------------------------
    if "J5001" in placed:
        hx, hy, hrot = placed["J5001"]
        jn = nets.get("J5001", {})
        # Names come from the netlist, not from a list typed here that goes
        # stale.  At rot 270 pin 1 is at +x, the numbering runs back towards
        # -x, the SIGNAL row is the upper one and the ground row faces the
        # board edge.
        step = -2.54 if hrot == 270 else 2.54
        dy = -4.2 if hrot == 270 else 4.2
        for i in range(10):
            s = jn.get(str(2 * i + 1), "")
            # Round 29: an unconnected pin is labelled NC rather than left
            # blank.  A blank pin on a debug header reads as "the silkscreen
            # ran out", and the three of them are the first place someone
            # will clip a probe.
            if not s or s.startswith("unconnected-"):
                s = "NC"
            silk(hx + i * step, hy + dy, s, 0.9, 0.16, angle=90)
        # ...and the whole even row is ground, which nothing said at all.
        place_in(hx + 2.2, hy + 1.2, hx + 22.0, hy + 4.0, "GND x10", 1.1, 0.18)
        # The clear band between unit 13's 1 pps box and the tops of this
        # connector's own rotated pin names.  ROUND 31: starting the search at
        # hx - 24 put it at (15.1, 158.8), which is 2.8 mm from the M3 hole at
        # (13, 157) and nowhere near the middle of the header -- so it read as
        # that hole's label.  Starting at hx - 16.9 lands it at (20.0, 160.8),
        # 7.9 mm from the hole and centred over the ten signal pins it names.
        # (The asked-for 161.5 is half a millimetre lower than the band goes:
        # unit 13's 1 pps box is above and there is one clear row, not two.)
        stack_in(hx - 16.9, hy - 14.0, hx + 6.0, hy - 11.0,
                 [("DEBUG 2x10", 1.4, 0.24)])

    # ---- the connectors in the power block ---------------------------------
    jx, jy = PW.place(*PW.PARTS["J2003"][:2])          # the 15 V barrel jack
    # BESIDE AND BELOW THE BARREL JACK.  Round 28 printed these at x = 172,
    # which is 12 mm from the bench 5 V posts and 12 mm from the jack, so they
    # read as a warning about the 5 V input -- the one place on this board
    # where 15 V must never go.  The region is the corner the jack is in.
    stack_in(jx - 22.0, jy + 5.0, G.BW - 1.0, jy + 20.0,
             [(s, 1.2, 0.2) for s in LB.BARREL_LINES])
    p5 = PW.place(*PW.PARTS["J2001"][:2])              # bench +5V post
    pg = PW.place(*PW.PARTS["J2002"][:2])              # bench GND post
    place_text(p5[0] + 4.5, p5[1], "+5V", 1.5, 0.26, spiral(0.5, 2.5))
    place_text(pg[0] - 4.5, pg[1], "GND", 1.5, 0.26, spiral(0.5, 2.5))
    # Round 29: three short lines that fit between the posts and the board
    # edge, instead of one 88-character line that ran off it (the DRC said so,
    # once, as a warning nobody was reading).  It says what the board normally
    # does before it says what not to do, because "OR LEAVE OPEN" was the only
    # hint that these posts are not the normal supply.
    # Round 29: three short lines instead of one 88-character line that ran
    # off the edge of the board (silk_edge_clearance, reported once, as a
    # warning nobody was reading).  They say what the board normally does
    # before they say what not to do, because "OR LEAVE OPEN" was the only
    # hint these posts are not the normal supply.  The strip they live in runs
    # left from the posts along the top edge, which is the nearest clear board
    # -- immediately above the posts there are 2.5 mm and two Schottkys.
    stack_in(pb[0] + 9.0, 0.7, G.BW - 13.0, 4.6,
             [(s, 0.9, 0.16) for s in LB.BENCH_LINES], gap=0.35)
    # ~110 mA at 5 V is modest, but it lands on top of whatever the Zynq is
    # already drawing and the manual warns that micro-USB "should provide
    # enough power for MOST designs".
    place_in(40.0, G.BH - 3.6, 112.0, G.BH - 0.6, LB.PYNQ_POWER_LINE,
             1.05, 0.18)

    # ---- reference designators, last ---------------------------------------
    # They go down after everything else precisely so that they are the thing
    # that moves.  A designator is the least important text on the board: it
    # names a part you can also find on the assembly drawing, whereas a test
    # point's letter is the only thing that says what you are probing.
    def default_ref(d, name):
        k = (d, name)
        if k not in _refdef:
            txt = _fpcache.get(k) or open(os.path.join(d, name + ".kicad_mod"),
                                          encoding="utf-8").read()
            mm = re.search(r'\(property "Reference".*?\(at\s+([-\d.]+)\s+([-\d.]+)',
                           txt, re.S)
            _refdef[k] = ((float(mm.group(1)), float(mm.group(2))) if mm
                          else (0.0, -1.6))
        return _refdef[k]

    _refdef = {}
    # Where a designator would rather be than where the stock footprint puts
    # it.  All in the PART's own frame, so the thirteen copies of a tile agree.
    #   the SMA jacks: 6.35 mm along the tile's own -x is directly BELOW the
    #   jack on the board, on both sides, and INSIDE the 10 MHz box -- the
    #   library position is 0.35 mm outside it.
    #   the heaters: +5.5 in their own x is the other end from the `H`, and
    #   for the thirteen in-tile ones it is inside the box their part is in.
    #   the 50R jumpers (round 41): just off the header on the side AWAY from
    #   the gutter -- above it on the right-hand units, below it (the mirror)
    #   on the left -- and centred across its two pins, which in the part's
    #   own frame are (0, 0) and (0, 2.54).
    REFPREF = {}
    # Rev B: the tap's 1k and the park 100k each in the 1.65 mm strip between
    # them and JP01; R51 beside itself, above the tile's heater.  (The tap
    # U.FL itself prints "TAP", not its J number: see TAP_NAME above.)
    # JP01's own name moves to the SPINE side of the header, between it and
    # C01: rev A's spot on the far side is now R21's.
    TILE_REF = {"R21": (1.55, 0.0), "R22": (1.55, 0.0),
                "R51": (0.0, -2.6), "JP01": (1.95, 1.27)}
    for u in sorted(byunit):
        for slot, r in byunit[u].items():
            if slot == "J01":
                REFPREF[r] = (-6.35, 0.0)
            elif slot == "J02":
                REFPREF[r] = (-4.8, 0.0)       # the pps box is 11.8 mm wide
            elif slot in TILE_REF:
                # rev B's new tile parts: the offset is in the TILE's frame,
                # so it is the same on both sides of the board.
                REFPREF[r] = to_local(TILE[slot][2], *TILE_REF[slot])
    for r in sorted(placed):
        if is_heater(r):
            REFPREF[r] = (5.5, 0.0)

    refat, reflayer = {}, {}

    def ref_order(r):
        """Who gets the room first.  Round 41: in alphabetical order the ICs
        came last, and unit 11's crowded 1 pps box gave U1104's name to the
        passives round it.  An IC's name is worth more than a test pad's --
        which already carries its letter -- so ICs and connectors go first."""
        pre = re.match(r"[A-Za-z]+", r).group(0)
        return ({"U": 0, "Q": 0, "J": 1, "X": 1, "Y": 1, "D": 2,
                 "TP": 9}.get(pre, 5), r)

    # A designator prints only where its OWN part is the nearest one
    # (2026-10-10).  Inside a unit's box the last-resort search took any clear
    # spot up to 12 mm away, and 236 names ended nearer another part than
    # their own -- R222 at TP202, R251 under the heater R2002, R204 under
    # JP201: the heater read as R251.  Round 41's rule, a name by the wrong
    # part is worse than none, holds inside a unit as well as across units.
    _bgrid = {}
    for _r2, _b2 in boxes.items():
        if _r2.startswith("MH") or _r2 == "J4001":       # holes; the underside socket
            continue
        for _gx in range(int(_b2[0] // 5), int(_b2[2] // 5) + 1):
            for _gy in range(int(_b2[1] // 5), int(_b2[3] // 5) + 1):
                _bgrid.setdefault((_gx, _gy), []).append(_r2)

    def _bdist(a, t):
        dx = max(a[0] - t[2], t[0] - a[2], 0.0)
        dy = max(a[1] - t[3], t[1] - a[3], 0.0)
        return (dx * dx + dy * dy) ** 0.5

    def nearest_ok(r, t, slack=NEAR_SLACK):
        own = _bdist(boxes[r], t)
        seen = set()
        for _gx in range(int((t[0] - 5) // 5), int((t[2] + 5) // 5) + 1):
            for _gy in range(int((t[1] - 5) // 5), int((t[3] + 5) // 5) + 1):
                for o in _bgrid.get((_gx, _gy), ()):
                    if o == r or o in seen:
                        continue
                    seen.add(o)
                    if _bdist(boxes[o], t) + slack < own:
                        return False
        return True

    for r in sorted(placed, key=ref_order):
        if r not in fpof:
            continue
        d, name = fpof[r]
        if r.startswith("MH"):
            reflayer[r] = "F.Fab"              # a hole has no designator
            continue
        if r == "J4001":
            continue                           # underside, mirrored, leave it
        if vals.get(r, "") in TAP_NAME:
            reflayer[r] = "F.Fab"              # a tap is named, not numbered
            continue
        rx, ry, rrot = placed[r]
        w = len(r) * adv(r, 0.8) + 0.16
        found = None
        # Preferred position first, then the library's own, then the four
        # sides of the part's courtyard -- and a spiral round each.  The four
        # sides matter: a spiral from a position that is deep inside a dense
        # row walks outward through every neighbour before it reaches clear
        # board, and the clear board is usually straight above or below.
        b0, b1, b2, b3 = boxes[r]
        cw, ch = (b2 - b0) / 2.0 + 0.7, (b3 - b1) / 2.0 + 0.7
        seeds = [p for p in (REFPREF.get(r), default_ref(d, name)) if p]
        seeds = [to_board(rrot, p[0], p[1]) for p in seeds]
        seeds += [(0.0, -ch), (0.0, ch), (-cw - w / 2.0, 0.0),
                  (cw + w / 2.0, 0.0)]
        for bx, by in seeds:
            for dx, dy in spiral(0.45, 3.6):
                cx, cy = rx + bx + dx, ry + by + dy
                bb = (cx - w / 2.0, cy - 0.48, cx + w / 2.0, cy + 0.48)
                if not blocked(bb) and inside_home(r, bb) and nearest_ok(r, bb):
                    found = (cx, cy, bb)
                    break
            if found:
                break
        hb = home_of(r)
        if not found and hb:
            # Round 41: every clear spot inside the part's OWN box, nearest
            # first, before giving up -- a designator in the next unit's box
            # names the wrong part, which is worse than none.
            pts = []
            y = hb[1] + BOX_MARGIN + 0.48
            while y <= hb[3] - BOX_MARGIN - 0.48:
                x = hb[0] + BOX_MARGIN + w / 2.0
                while x <= hb[2] - BOX_MARGIN - w / 2.0:
                    pts.append(((x - rx) ** 2 + (y - ry) ** 2, x, y))
                    x += 0.25
                y += 0.25
            # First clear of vias too; then over a via if that is all the box
            # has left -- they are tented, and ink on them is legal (see the
            # note where vias become obstacles).  Units 10-12's 1 pps boxes
            # need it: their five-character names are 0.8 mm wider.
            for kinds in (ALL, PROSE):
                for _d2, cx, cy in sorted(pts):
                    if _d2 > 12.0 ** 2:
                        break
                    bb = (cx - w / 2.0, cy - 0.48, cx + w / 2.0, cy + 0.48)
                    if not blocked(bb, kinds=kinds) and nearest_ok(r, bb):
                        found = (cx, cy, bb)
                        break
                if found:
                    break
        if found:
            obstruct(found[2])
            refat[r] = to_local(rrot, found[0] - rx, found[1] - ry)
            _owned.append((r, r, found[2]))
        else:
            # Nowhere on 373 cm2 that this name can be printed without
            # landing on a solder-mask opening or on something that matters
            # more.  Move it to F.Fab: it stays on the assembly drawing and
            # in the placement file, and the silkscreen stays legible.
            reflayer[r] = "F.Fab"
            _nlost.append(r)

    # ---- the region borders, now that every label is down -----------------
    for _name in sorted(rboxes):
        silk_box(*rboxes[_name], w=0.2)

    # ---- and now every footprint, with its designator where it belongs -----
    for idx, d, name, ref, value, fx, fy, frot, flayer, fnets in pending:
        out[idx] = footprint(d, name, ref, value, fx, fy, frot, flayer,
                             fnets, numof, refat=refat.get(ref),
                             reflayer=reflayer.get(ref))
    import sys as _sl
    print("silkscreen: %d designators placed, %d moved to F.Fab %s"
          % (len(refat), len(_nlost), sorted(_nlost)[:40]), file=_sl.stderr)
    if _tapless:
        print("silkscreen: no room for TAP beside %s" % sorted(_tapless), file=_sl.stderr)

    # ---- round 41: nothing that belongs to a box may print outside it -----
    # Every part of a unit tile inside its own box, and every designator and
    # test-point letter placed for such a part.  The same rule is applied to
    # a finished board file by pcb/check_silk_boxes.py.
    def check_owned():
        bad = []
        for ref, s, b in _owned:
            if not inside_home(ref, b):
                bad.append("%r (for %s) at (%.1f,%.1f)-(%.1f,%.1f) is outside %s"
                           % (s, ref, b[0], b[1], b[2], b[3], home_of(ref)))
        for ref in sorted(placed):
            hb = home_of(ref)
            if hb and ref in boxes:
                pb = boxes[ref]
                if not (pb[0] >= hb[0] and pb[1] >= hb[1] and pb[2] <= hb[2]
                        and pb[3] <= hb[3]):
                    bad.append("part %s at (%.1f,%.1f)-(%.1f,%.1f) is outside %s"
                               % ((ref,) + tuple(pb) + (hb,)))
        return bad

    # Who owns every label, and every unit's boxes, for
    # pcb/check_unit_labels.py -- which reads the WRITTEN board with KiCad's
    # own text boxes, so it also sees labels nothing here registered.
    import json as _js

    def _mkd(d):
        os.makedirs(d, exist_ok=True)
        return d
    _js.dump({"owned": [(r_, s_, list(b_)) for r_, s_, b_ in _owned],
              "ubox": {"%s|%s" % k: list(v) for k, v in sorted(ubox.items())},
              "home": {r_: list(home_of(r_)) for r_ in sorted(placed) if home_of(r_)},
              "placed": {r_: list(v) for r_, v in sorted(placed.items())}},
             open(os.path.join(_mkd(os.path.join(ROOT, "build")), "silk_owned.json"), "w"))
    _bad_owned = check_owned()
    _tile_fab = sorted(r for r in _nlost if home_of(r))
    print("silkscreen boxes: %d owned labels checked, %d outside their box; "
          "%d tile designators moved to F.Fab %s"
          % (len(_owned), len(_bad_owned), len(_tile_fab), _tile_fab[:20]),
          file=_sl.stderr)
    if _bad_owned:
        for b in _bad_owned[:40]:
            print("SILK BOX: " + b, file=_sl.stderr)
        raise SystemExit("silkscreen: %d item(s) outside the box they belong to"
                         % len(_bad_owned))
    # Every line that reaches stack_in is one the board is supposed to carry,
    # so a dropped one is a fault and not a detail.  Round 29's second build
    # lost the title, the author line and the test-point legend heading and
    # the only trace was three lines of stderr that build.py filtered out.
    if _dropped:
        print("SILK: DROPPED %d line(s) the board should carry: %s"
              % (len(_dropped), _dropped), file=_sl.stderr)

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
    open(os.environ.get("OUTPCB",
                        os.path.join(ROOT, "GPSDO-PYNQ-Z2.kicad_pcb")),
         "w", encoding="utf-8").write(txt)
    print("placed %d parts" % len(placed))
    if bad:
        print("OVERLAPS: %d" % len(bad))
        for a, b in bad[:25]:
            print("   %s <-> %s" % (a, b))
    else:
        print("no courtyard overlaps")
