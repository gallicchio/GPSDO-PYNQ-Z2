"""Where every part goes, and a check that no two of them overlap.

The floorplan follows one conclusion from the helper sheet: the branch LENGTHS
do not matter (a 100 mm mismatch drifts 0.7 ps over 10 degC against a 12.3 ps
resolution), but the four second-stage buffers being adjacent does.  So the
helper cluster is one compact block and the thirteen channel tiles are free to
sit wherever the connectors put them.
"""

# Courtyard-ish footprint sizes, w x h in mm, used only for overlap checking.
SIZE = {
    "Capacitor_SMD:C_0805_2012Metric": (3.0, 1.9),
    "Resistor_SMD:R_0805_2012Metric": (3.0, 1.9),
    "Inductor_SMD:L_0805_2012Metric": (3.0, 1.9),
    "Resistor_SMD:R_1206_3216Metric": (4.2, 2.2),
    "Resistor_SMD:R_2010_5025Metric": (6.4, 3.2),
    "Fuse:Fuse_1206_3216Metric": (4.2, 2.2),
    "Package_TO_SOT_SMD:SOT-23-5": (3.2, 3.2),
    "Package_TO_SOT_SMD:SOT-23-6": (3.2, 3.2),
    "Package_TO_SOT_SMD:SOT-23": (3.2, 3.2),
    "Package_TO_SOT_SMD:SOT-223-3_TabPin2": (7.2, 7.2),
    "TestPoint:TestPoint_Pad_D1.5mm": (2.0, 2.0),
    "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm": (6.6, 5.6),
    "Package_SO:MSOP-10_3x3mm_P0.5mm": (5.2, 4.4),
    "Diode_SMD:D_SMA": (5.4, 3.0),
    "Diode_SMD:D_SMB": (6.2, 4.0),
    "Diode_SMD:D_SOD-323": (2.6, 1.8),
    "Oscillator:Oscillator_SMD_Fox_FT5H_5.0x3.2mm": (6.0, 4.2),
    "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm": (4.2, 3.4),
    "GPSDO-PYNQ-Z2:SMA_Vertical_THT_Universal": (9.5, 9.5),
    "GPSDO-PYNQ-Z2:RPiHeader_2x20_Socket_Underside": (52.0, 6.0),
    "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical": (5.4, 3.0),
    "Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical": (3.0, 3.0),
    "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical": (6.0, 26.0),
    "Connector_PinSocket_2.54mm:PinSocket_2x20_P2.54mm_Vertical": (53.0, 7.0),
    "TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-3-3.5-H_1x03_P3.50mm_Horizontal":
        (12.0, 10.0),
    "Connector_BarrelJack:BarrelJack_Horizontal": (14.0, 12.0),
    "MountingHole:MountingHole_3.2mm_M3": (6.4, 6.4),
}
DEFAULT_SIZE = (5.0, 5.0)


# ---------------------------------------------------------------------------
# One channel tile.  Offsets are from the unit's 10 MHz SMA centre, +x right,
# +y down, and follow the signal: terminate, couple, square, sample, retime.
# The suffix is the per-unit reference number, so R"01" is R101 on unit 1 and
# R1001 on unit 10.
# ---------------------------------------------------------------------------
TILE = {
    # 10 MHz chain
    "J01":  (0.0, 0.0, 0),      # SMA, placed by the connector row
    "TP01": (-5.6, 6.5, 0),
    "R01":  (0.0, 6.5, 90),     # 51R terminator
    "JP01": (-2.0, 11.8, 90),   # 50R TERM jumper (origin is pin 1,
                                # so its body reaches 4.3 mm in +x)
    "R02":  (5.0, 6.5, 0),      # 0R series
    "C01":  (5.0, 10.6, 0),     # 10n C0G
    "R03":  (9.6, 10.6, 90),    # 2k2 shunt
    "R04":  (5.0, 14.7, 0),     # 330R
    "D01":  (9.6, 14.7, 0),     # BAV99, DNP
    "TP02": (0.0, 16.8, 0),     # TP_SQ
    "U01":  (3.4, 19.6, 0),     # 74LVC1GU04
    "R05":  (9.0, 19.6, 90),    # 1M self-bias
    "FB01": (-3.0, 19.6, 90),
    "C02":  (-3.0, 16.0, 0),
    "C03":  (-3.0, 23.2, 0),
    "U02":  (3.4, 26.0, 0),     # FF1
    "FB02": (-3.0, 26.0, 90),
    "C04":  (-3.0, 29.6, 0),
    "C05":  (9.0, 26.0, 0),
    "U03":  (3.4, 32.4, 0),     # FF2
    "FB03": (-3.0, 32.4, 90),
    "C06":  (-3.0, 36.0, 0),
    "C07":  (9.0, 32.4, 0),
    "TP03": (9.0, 36.0, 0),     # TP_BEAT
    # 1 pps chain, under the second SMA
    "J02":  (12.7, 0.0, 0),
    "R06":  (12.7, 6.5, 90),    # 51R, DNP
    "R07":  (17.0, 6.5, 0),     # 1k
    "R08":  (17.0, 10.6, 90),   # 10k
    "FB04": (13.4, 15.0, 0),
    "C08":  (17.0, 15.0, 0),
    "C09":  (12.9, 19.0, 0),
    "U04":  (17.0, 20.6, 0),    # 74LVC1G17
    "TP04": (12.7, 24.6, 0),    # TP_PPS
}


# Which tile slots belong to which input circuit, for the silkscreen boxes.
# The SMAs are deliberately outside the boxes: at a 15.24 mm pitch two 9.5 mm
# jacks nearly touch, so including them would make the two boxes overlap.
TILE_10M = ["TP01", "R01", "JP01", "R02", "C01", "R03", "R04", "D01",
            "TP02", "U01", "R05", "FB01", "C02", "C03", "U02", "FB02", "C04",
            "C05", "U03", "FB03", "C06", "C07", "TP03"]
TILE_PPS = ["R06", "R07", "R08", "FB04", "C08", "C09", "U04", "TP04"]


def tile(pitch):
    """TILE with the pps half shifted to follow the SMA pitch.

    The offsets below were authored at the 12.7 mm pitch.  Widening the pitch
    moves the pps SMA but not, without this, the parts that hang off it -- which
    left the jack 2.5 mm from the silkscreen label naming it.
    """
    d = dict(TILE)
    shift = pitch - 12.7
    if shift:
        for slot in TILE_PPS:
            dx, dy, rot = d[slot]
            d[slot] = (dx + shift, dy, rot)
    return d


def unit_refs(u):
    """Map a tile slot like 'R01' to this unit's real reference."""
    out = {}
    for slot in TILE:
        pre = slot[:2] if slot[:2] in ("TP", "FB", "JP") else slot[:1]
        num = slot[len(pre):]
        out[slot] = "%s%d%s" % (pre, u, num)
    return out


def overlaps(placed, fps):
    """placed: {ref: (x, y, rot)}.  Returns a list of colliding pairs."""
    boxes = []
    for ref, (x, y, rot) in placed.items():
        w, h = SIZE.get(fps.get(ref, ""), DEFAULT_SIZE)
        if rot % 180:
            w, h = h, w
        boxes.append((ref, x - w / 2, y - h / 2, x + w / 2, y + h / 2))
    bad = []
    boxes.sort(key=lambda b: b[1])
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if b[1] >= a[3]:
                break
            if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]:
                bad.append((a[0], b[0]))
    return bad


# ---------------------------------------------------------------------------
# Real footprint extents, read from the .kicad_mod rather than guessed.
#
# The SIZE table above assumes a footprint is centred on its origin.  That is
# true for passives and wrong for connectors, whose origin is pin 1 -- the
# 3-way terminal block's body reaches 9.25 mm one way and 2.25 mm the other.
# Using a centred box for those silently under- or over-states where they are.
# ---------------------------------------------------------------------------
import os as _os, re as _re
_EXT = {}


def extent(libdir, name):
    """(dx0, dy0, dx1, dy1) of the courtyard relative to the footprint origin."""
    key = (libdir, name)
    if key in _EXT:
        return _EXT[key]
    t = open(_os.path.join(libdir, name + ".kicad_mod"), encoding="utf-8").read()
    xs, ys = [], []
    for m in _re.finditer(r'\(fp_(?:line|rect)\s*\(start ([-\d.]+) ([-\d.]+)\)\s*'
                          r'\(end ([-\d.]+) ([-\d.]+)\)[\s\S]{0,240}?\(layer "([^"]+)"\)', t):
        if m.group(5).endswith("CrtYd"):
            xs += [float(m.group(1)), float(m.group(3))]
            ys += [float(m.group(2)), float(m.group(4))]
    if not xs:                       # no courtyard: fall back to the pads
        for m in _re.finditer(r'\(pad "[^"]*"[^\n]*\n\s*\(at ([-\d.]+) ([-\d.]+)', t):
            xs += [float(m.group(1))]
            ys += [float(m.group(2))]
        xs = [min(xs) - 1.0, max(xs) + 1.0]
        ys = [min(ys) - 1.0, max(ys) + 1.0]
    _EXT[key] = (min(xs), min(ys), max(xs), max(ys))
    return _EXT[key]


def box_at(libdir, name, x, y, rot):
    """Absolute bounding box of a footprint placed at (x, y, rot)."""
    dx0, dy0, dx1, dy1 = extent(libdir, name)
    pts = [(dx0, dy0), (dx1, dy0), (dx1, dy1), (dx0, dy1)]
    import math
    a = math.radians(-rot)
    ca, sa = math.cos(a), math.sin(a)
    px = [p[0] * ca - p[1] * sa for p in pts]
    py = [p[0] * sa + p[1] * ca for p in pts]
    return (x + min(px), y + min(py), x + max(px), y + max(py))


def overlaps_boxes(boxes):
    """boxes: {ref: (x0, y0, x1, y1)}.  Returns colliding pairs."""
    bs = sorted(((r,) + b for r, b in boxes.items()), key=lambda b: b[1])
    bad = []
    for i, a in enumerate(bs):
        for b in bs[i + 1:]:
            if b[1] >= a[3]:
                break
            if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]:
                bad.append((a[0], b[0]))
    return bad


def pads(libdir, name, x, y, rot):
    """[(padnum, px, py)] in board coordinates for a footprint placed at x,y,rot."""
    import math
    t = open(_os.path.join(libdir, name + ".kicad_mod"), encoding="utf-8").read()
    a = math.radians(-rot)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    # [^()]* rather than [^\n]*\n\s* : our own SMA footprint writes a pad on a
    # SINGLE line, and the newline-only version silently matched nothing, so all
    # 27 jacks' through-hole pads were invisible to every collision check on
    # this board -- including the ground-via search.
    for m in _re.finditer(r'\(pad "([^"]*)"\s+(\w+)\s+\w+[^()]*'
                          r'\(at ([-\d.]+) ([-\d.]+)\s*([-\d.]*)[^)]*\)\s*'
                          r'\(size ([\d.]+) ([\d.]+)\)', t):
        lx, ly = float(m.group(3)), float(m.group(4))
        pang = float(m.group(5)) if m.group(5) else 0.0
        w, h = float(m.group(6)), float(m.group(7))
        # Half-diagonal AND the real rectangle.  The half-diagonal is what the
        # grid routers use, where a conservative circle is the right trade; it
        # is far too pessimistic for a fine-pitch part, though -- a SOIC-8's
        # 1.95 x 0.6 mm pad becomes a 2.04 mm circle, so on that model nothing
        # can ever approach pin 8 without fouling pin 7, when in reality there
        # is 0.97 mm of clear copper between them.  Anything that checks real
        # clearance wants (hw, hh, angle) instead.
        out.append((m.group(1), x + lx * ca - ly * sa, y + lx * sa + ly * ca,
                    m.group(2) != "smd",           # True when it is a plated hole
                    0.5 * (w * w + h * h) ** 0.5,  # half-diagonal
                    (0.5 * w, 0.5 * h, rot + pang)))
    return out


def pad_gap(px, py, cx, cy, rect):
    """Distance from a point to a pad RECTANGLE (0 if inside)."""
    import math
    hw, hh, ang = rect
    a = math.radians(ang)
    dx, dy = px - cx, py - cy
    ux = dx * math.cos(a) - dy * math.sin(a)
    uy = dx * math.sin(a) + dy * math.cos(a)
    gx, gy = max(0.0, abs(ux) - hw), max(0.0, abs(uy) - hh)
    return math.hypot(gx, gy)
