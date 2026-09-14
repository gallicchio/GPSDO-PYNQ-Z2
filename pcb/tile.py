"""One channel tile: where its parts go, and every track inside it.

Coordinates are local to the unit's 10 MHz SMA centre, +x right, +y down.  The
same numbers are stamped out thirteen times, so the tile is worth getting right
once: it is 13/13ths of the analogue design and 588/588ths of nothing else.

Layout rules that the numbers below come from:

  * The signal spine is x = 0, directly under the SMA centre pin, which escapes
    straight down between the jack's two lower ground pins (1.14 mm of clear
    room either side of a 0.25 mm track).
  * Every logic gate is at rot 270, which puts its INPUT on the top edge, its
    OUTPUT bottom-left and its Vcc bottom-RIGHT.  So the signal flows down the
    spine and the power always comes in from the right; that is the whole
    reason the tile is asymmetric.
  * Power therefore enters from a rail in the GUTTER to the right of the box,
    goes left through the ferrite into the Vcc pin, and the two decoupling
    capacitors hang off that lane below it.  Nothing has to cross anything.
  * The 1 M self-bias resistor R05 is the only part that has to get from the
    squarer's input back to its output.  It sits to the LEFT of U01, where both
    ends are a 3 mm hop and neither crosses the Vcc lane.
  * BEAT and PPS leave on In2.Cu through a via at the bottom of each box; see
    build_pcb.py for why that layer can carry them.

Every silkscreen box is a FIXED rectangle centred on its own SMA, not the
bounding box of what happens to be inside it.  Sizing a box to its contents is
what put the 1 pps jack off to one side of its own rectangle.
"""

SMA_PITCH = 15.24

# ---------------------------------------------------------------------------
# Placement.  (dx, dy, rot); rot 270 = "pad 1 at the top".
# ---------------------------------------------------------------------------
Y_U1, IC_PITCH = 20.2, 8.0
Y_U2, Y_U3 = Y_U1 + IC_PITCH, Y_U1 + 2 * IC_PITCH
RAIL_10M = 8.9              # +3V3_A rail, in the gutter beside the tile.  One
RAIL_PPS = 8.9              # rail now serves both halves: since round 15 they
                            # are in LINE rather than side by side, so the same
                            # gutter runs the whole length of the unit.
RAIL_HEAD_PPS = -32.1       # the rail runs out past the 1 pps block to meet the
                            # board-edge +3V3_A spine
RAIL_FOOT = 44.0             # where both rails meet the row's horizontal spine,
                             # 1.4 mm below the bottom of the taller box
RAIL_HEAD = -5.0             # both rails run the FULL height of the box, not
                             # just between their ferrites.  The extra copper
                             # is a DC rail and costs nothing, and it keeps the
                             # ground-via search out of the gutter -- which is
                             # what leaves a clean vertical channel on In2.Cu
                             # underneath, and In2 badly needs the channels.

def _ic_power(y):
    """Ferrite and the two capacitors that serve one gate at spine y."""
    return {"FB": (6.6, y + 1.1375, 180),
            "CA": (2.9, y + 4.0, 270),
            "CB": (5.3, y + 4.0, 270)}

PARTS_10M = {
    "J01":  (0.0, 0.0, 0),
    "TP01": (3.0, 6.6, 0),
    "R02":  (0.0, 7.0, 270),        # 0R series
    "R01":  (-3.4, 7.0, 270),       # 51R terminator
    "JP01": (-3.4, 11.2, 0),        # 50R TERM jumper, pin 1 at the top
    "C01":  (0.0, 11.0, 270),       # 10n C0G, the AC coupling
    "R03":  (3.4, 9.4, 0),          # 2k2 to ground
    "R04":  (0.0, 15.0, 270),       # 330R into the squarer
    "D01":  (3.9, 13.0, 180),       # BAV99 clamp, DNP
    "TP02": (3.0, 17.4, 0),
    "U01":  (0.0, Y_U1, 270),       # 74LVC1GU04 squarer
    "R05":  (-3.4, Y_U1, 270),      # 1M self-bias
    "U02":  (0.0, Y_U2, 270),       # sampling flip-flop
    "U03":  (0.0, Y_U3, 270),       # re-timing flip-flop
    "TP03": (-3.4, 39.8, 0),
}
for _slot, _y in (("01", Y_U1), ("02", Y_U2), ("03", Y_U3)):
    _p = _ic_power(_y)
    PARTS_10M["FB" + _slot] = _p["FB"]
    PARTS_10M["C%02d" % (2 * int(_slot))] = _p["CA"]       # C02 C04 C06
    PARTS_10M["C%02d" % (2 * int(_slot) + 1)] = _p["CB"]   # C03 C05 C07

# Round 15: the 1 pps block sits IN LINE with the 10 MHz block, on its far
# side from the helper, rather than beside it.  Its own origin (the 1 pps jack)
# is this far back along the chain from the 10 MHz jack: the 1 pps box is
# 25.4 mm long, then a 1.5 mm gap, then the 10 MHz box starts 6 mm above its
# own jack.
PPS_OFFSET = (0.0, -26.9)

Y_U4 = 12.6
PARTS_PPS = {
    "J02":  (0.0, 0.0, 0),
    "R07":  (0.0, 7.0, 270),        # 1k top of the divider
    "R06":  (-3.4, 7.0, 270),       # 51R, DNP
    "R08":  (3.4, 8.0, 0),          # 10k to ground
    "U04":  (0.0, Y_U4, 270),       # 74LVC1G17 Schmitt buffer
    "FB04": (3.8, Y_U4 + 1.1375, 180),
    "C09":  (3.8, 10.8, 0),         # 10n, above the ferrite
    "C08":  (3.8, 17.0, 0),         # 100n, below it
    "TP04": (-3.4, 16.6, 0),
}

# The two boxes, as fixed rectangles about their own SMA.
BOX_10M = (-8.4, -6.0, 8.4, 42.6)          # 16.8 x 48.6
BOX_PPS = (-5.9, -6.0, 5.9, 19.4)          # 11.8 x 25.4, about its own origin

TILE_10M = list(PARTS_10M)
TILE_PPS = list(PARTS_PPS)


def tile(pitch=None):
    """Both halves in one dict, in unit-local coordinates."""
    ox, oy = PPS_OFFSET
    d = dict(PARTS_10M)
    for slot, (dx, dy, rot) in PARTS_PPS.items():
        d[slot] = (dx + ox, dy + oy, rot)
    return d


def pps_box():
    """BOX_PPS moved onto the unit's own origin."""
    ox, oy = PPS_OFFSET
    x0, y0, x1, y1 = BOX_PPS
    return (x0 + ox, y0 + oy, x1 + ox, y1 + oy)


# ---------------------------------------------------------------------------
# Routing.  A route is (anchor, width, [(x, y), ...]) where anchor is the
# (slot, pad) whose net the whole polyline carries.  Naming the net by a PAD
# rather than by a string means the tracks cannot drift away from the netlist:
# if the schematic moves a net, the track moves with it.
# ---------------------------------------------------------------------------
W_SIG, W_PWR = 0.25, 0.5

def _ic_power_routes(fb, y, rail):
    """rail -> ferrite -> Vcc, and the two capacitors hanging off that lane."""
    vy = y + 1.1375
    return [
        ((fb, "1"), W_PWR, [(rail, vy), (7.662, vy)]),
        ((fb, "2"), W_SIG, [(5.538, vy), (0.95, vy)]),
        ((fb, "2"), W_SIG, [(2.9, vy), (2.9, y + 3.05)]),
        ((fb, "2"), W_SIG, [(5.3, vy), (5.3, y + 3.05)]),
    ]


def routes_10m(head=RAIL_HEAD):
    """head: where the rail starts -- above the 1 pps block, or above the
    10 MHz block for unit 13, which has no 1 pps half."""
    R = []
    # --- the input node: SMA centre pin down, terminator left, test point right
    R.append((("J01", "1"), W_SIG, [(0, 0), (0, 6.088)]))
    R.append((("J01", "1"), W_SIG, [(0, 6.088), (-3.4, 6.088)]))
    R.append((("J01", "1"), W_SIG, [(0, 6.088), (3.0, 6.088), (3.0, 6.6)]))
    # --- 51R down to the jumper that grounds it
    R.append((("R01", "2"), W_SIG, [(-3.4, 7.912), (-3.4, 11.2)]))
    # --- 0R to the coupling cap, with the 2k2 hanging off that node
    R.append((("R02", "2"), W_SIG, [(0, 7.912), (0, 10.088)]))
    R.append((("R02", "2"), W_SIG, [(0, 9.4), (2.488, 9.4)]))
    # --- coupling cap to the 330R, with the clamp on that node
    R.append((("C01", "2"), W_SIG, [(0, 11.912), (0, 14.088)]))
    R.append((("C01", "2"), W_SIG, [(0, 13.0), (2.962, 13.0)]))
    # SOT-23 at rot 180 puts pad 1 BELOW the centre and pad 2 above it, so the
    # +3V3_A tap is the lower pad and the ground pad is the upper one.
    R.append((("D01", "1"), W_PWR, [(4.838, 13.95), (RAIL_10M, 13.95)]))
    # --- the squarer input node: 330R down, 1M and test point across
    R.append((("R04", "2"), W_SIG, [(0, 15.912), (0, 19.0625)]))
    R.append((("R04", "2"), W_SIG, [(-3.4, 17.4), (3.0, 17.4)]))
    R.append((("R05", "1"), W_SIG, [(-3.4, 19.288), (-3.4, 17.4)]))
    # --- squarer output: the 1M back, then on to the first flip-flop
    R.append((("U01", "4"), W_SIG, [(-3.4, 21.112), (-3.4, 21.3375), (-0.95, 21.3375)]))
    R.append((("U01", "4"), W_SIG, [(-0.95, 21.3375), (-0.95, 24.4),
                                    (0.95, 24.4), (0.95, Y_U2 - 1.1375)]))
    # --- flip-flop to flip-flop, down the left and across below U02
    R.append((("U02", "4"), W_SIG, [(-0.95, Y_U2 + 1.1375), (-0.95, Y_U2 + 4.2),
                                    (0.95, Y_U2 + 4.2), (0.95, Y_U3 - 1.1375)]))
    # --- the helper clock arrives on In2 at a via BESIDE the data path, never
    #     across it, and reaches both clock pins from the left.
    R.append((("U02", "2"), W_SIG, [(-2.2, HCLK_VIA[1]), (-2.2, 25.5),
                                    (0, 25.5), (0, Y_U2 - 1.1375)]))
    R.append((("U03", "2"), W_SIG, [(-2.2, HCLK_VIA[1]), (-2.2, 33.5),
                                    (0, 33.5), (0, Y_U3 - 1.1375)]))
    # --- the beat out, to its test point and down to In2
    R.append((("U03", "4"), W_SIG, [(-0.95, Y_U3 + 1.1375), (-0.95, 39.8),
                                    (BEAT_VIA[0], 39.8)]))
    for fb, y in (("FB01", Y_U1), ("FB02", Y_U2), ("FB03", Y_U3)):
        R += _ic_power_routes(fb, y, RAIL_10M)
    # --- the rail itself, down the gutter past all three ferrites
    R.append((("D01", "1"), W_PWR, [(RAIL_10M, head), (RAIL_10M, RAIL_FOOT)]))
    return R




def routes_pps():
    R = []
    R.append((("J02", "1"), W_SIG, [(0, 0), (0, 6.088)]))
    R.append((("J02", "1"), W_SIG, [(0, 6.088), (-3.4, 6.088)]))
    R.append((("R07", "2"), W_SIG, [(0, 7.912), (0, Y_U4 - 1.1375)]))
    R.append((("R07", "2"), W_SIG, [(0, 8.0), (2.488, 8.0)]))
    R.append((("U04", "4"), W_SIG, [(-0.95, Y_U4 + 1.1375), (-0.95, 16.6),
                                    (PPS_VIA[0], 16.6)]))
    vy = Y_U4 + 1.1375
    R.append((("FB04", "1"), W_PWR, [(RAIL_PPS, vy), (4.862, vy)]))
    R.append((("FB04", "2"), W_SIG, [(2.738, vy), (0.95, vy)]))
    R.append((("FB04", "2"), W_SIG, [(2.85, vy), (2.85, 17.0)]))
    R.append((("FB04", "2"), W_SIG, [(2.85, vy), (2.85, 10.8)]))
    return R


# Vias that take a tile signal down to In2.Cu, and where each one's stub comes
# back out into the open.  All three run to the same line just past the inner
# end of the unit, which since round 15 is the edge of the helper band -- so
# every unit hands its three In2 nets over in the same place.
#
# These are in TILE coordinates (the 1 pps via has already been moved onto the
# unit's own origin), because the whole unit gets rotated 90 or 270 depending
# on which side of the centre line it lives.
ESC_Y    = 43.0   # The hand-off line stops at the BOX EDGE, not out in the
                  # helper band.  At 48 every unit's three escape stubs ran
                  # 5 mm into the return lane and lay across it, so a return
                  # descending the lane had to cross three of them per row
                  # it passed -- which is what left eight of them unrouted.
BEAT_VIA = (-6.0, 39.8)
HCLK_VIA = (-2.2, 31.5)
PPS_VIA  = (-4.9, PPS_OFFSET[1] + 16.6)           # pps-local (-4.9, 16.6)

VIAS_10M = [("U03", "4") + BEAT_VIA + (ESC_Y,),
            ("U02", "2") + HCLK_VIA + (ESC_Y,)]
VIAS_PPS = [("U04", "4") + PPS_VIA + (ESC_Y,)]
