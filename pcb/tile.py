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
    """The supply resistor (rev B item 12: 4R7 where rev A had a ferrite, same
    0805) and the two capacitors that serve one gate at spine y."""
    return {"FB": (6.6, y + 1.1375, 180),
            "CA": (2.9, y + 4.0, 270),
            "CB": (5.3, y + 4.0, 270)}

PARTS_10M = {
    "J01":  (0.0, 0.0, 0),
    "TP01": (3.0, 6.6, 0),
    "R02":  (0.0, 7.0, 270),        # 0R series
    "R01":  (-2.9, 7.0, 270),       # 51R terminator (rev B: 0.5 in, for J03)
    "JP01": (-3.4, 11.6, 0),        # 50R/PARK header, pin 1 at the top (rev B: 0.4 down)
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
    # rev B: the input tap (item 19) and the park resistor (item 11), in the
    # tile's free left column.  PLACEMENT ONLY so far: routes_10m() predates
    # them, and the squarer (U01) is now a 74LVC2GU04 in SC-70-6.
    "J03":  (-6.6, 7.3, 180),       # U.FL, TAP IN: top-left, clear of the SMA
                                    # (courtyard 1.80 / 2.55 mm off its pin, so
                                    # this puts its edge on the box's, x = -8.4)
    "R21":  (-6.6, 12.4, 270),      # 1k into the tap
    "R22":  (-6.6, 16.4, 270),      # 100k, gate to JP01 pin 3 (PARK)
    # rev B, 2026-10-10: the squarer-output tap, in the empty strip on the
    # far side of the spine from JP01, between TP02 (y 17.4) and R52 (29.3).
    # 1k with pad 1 on the 1Y-D track, the U.FL just outboard: 2.5 mm from
    # the helper clock (which enters U02 from the other side, at y 25.5), 6 mm
    # from the squarer's input node, courtyards 0.07 mm apart, the U.FL's
    # outer edge 0.1 mm inside the box.
    "R23":  (2.2, 23.0, 180),       # 1k into the tap: pad 2 (the node, as on
                                    # the sheet and as R21) inboard on 1Y-D
    "J04":  (6.5, 23.0, 0),         # U.FL, TAP SQ, its pin toward the 1k
}
# Rev B: the squarer is a 74LVC2GU04 in SC-70-6, whose VCC (pin 5) sits
# BETWEEN its two outputs on the bottom row: 2Y (the replica, pin 4) on the
# left and 1Y (pin 6) on the right.  A supply from the right-hand gutter would
# have to cross 1Y on its way down to the flip-flop, so U01's filter moves to
# the LEFT: VCC drops out of the pin's end, runs left past the two capacitors
# to R51, and R51's other end takes a via to +3V3_A (the plane, item 5).  1Y
# then runs straight down to U02 with nothing across it.  U02 and U03 keep
# rev A's right-hand arrangement.
Y_VCC1 = Y_U1 + 2.45                  # U01's VCC lane, below the replica's R05
PARTS_10M["R51"] = (-6.4, Y_VCC1, 0)  # 4R7 lying flat, pad 1 (+3V3_A) outboard,
                                      # above the tile's heater (y 24.75 on)
PARTS_10M["C02"] = (-1.5, Y_VCC1 + 0.95, 270)
PARTS_10M["C03"] = (-3.7, Y_VCC1 + 0.95, 270)
for _slot, _y in (("02", Y_U2), ("03", Y_U3)):
    _p = _ic_power(_y)
    PARTS_10M["R5" + _slot[1]] = _p["FB"]               # R51 R52 R53 (were FB01-03)
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
    "R54":  (3.8, Y_U4 + 1.1375, 180),    # was FB04
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
    """4R7 -> Vcc, and the two capacitors hanging off that lane.  Rev B: the
    4R7's +3V3_A end (pad 1) takes its own via to the B.Cu plane, found by
    build_pcb's plane-via search; rev A ran it to a rail in the gutter."""
    vy = y + 1.1375
    return [
        ((fb, "2"), W_SIG, [(5.538, vy), (0.95, vy)]),
        ((fb, "2"), W_SIG, [(2.9, vy), (2.9, y + 3.05)]),
        ((fb, "2"), W_SIG, [(5.3, vy), (5.3, y + 3.05)]),
    ]


def routes_10m(head=RAIL_HEAD):
    """head: where the rail starts -- above the 1 pps block, or above the
    10 MHz block for unit 13, which has no 1 pps half.

    Rev B (2026-10-09): the squarer is the SC-70-6 74LVC2GU04 with its replica
    bias, the input has a U.FL tap and a 100k park, and the jumper is the 3-pin
    50R/PARK header.  JP01's pins are 1.7 mm pads 2.54 apart, so the gaps
    between them are 0.84 mm: the tap and the park resistor each cross JP01's
    column through one, at y = 12.87 and 15.41."""
    R = []
    # --- the input node: SMA centre pin down, terminator left, test point right
    R.append((("J01", "1"), W_SIG, [(0, 0), (0, 6.088)]))
    R.append((("J01", "1"), W_SIG, [(0, 6.088), (-2.9, 6.088)]))
    R.append((("J01", "1"), W_SIG, [(0, 6.088), (3.0, 6.088), (3.0, 6.6)]))
    # --- 51R down to the header's pin 1 (pin 2 is ground: 1-2 = 50R)
    R.append((("R01", "2"), W_SIG, [(-2.9, 7.912), (-2.9, 11.6)]))
    # --- the tap (item 19): the input node, through 1k, to the U.FL.
    #     J03's pin is 1.5 mm in from its ground pads, so the track runs
    #     down the gap between those pads and JP01.  The 1k's node end
    #     crosses JP01's column between pins 1 and 2 and climbs to the
    #     0R-to-10n link between R01's track and C01: the SOURCE side of the
    #     coupling cap (order day, 2026-10-10 -- on the gate side a DC-coupled
    #     scope pulled the squarer off its bias; see the unit sheet).
    R.append((("J03", "1"), W_SIG, [(-5.075, 7.3), (-5.075, 10.3), (-6.6, 11.488)]))
    R.append((("R21", "2"), W_SIG, [(-6.6, 13.312), (-6.6, 12.87), (-1.5, 12.87),
                                    (-1.5, 9.0), (0, 9.0)]))
    # --- the park (item 11): the squarer input through 100k to pin 3
    R.append((("R22", "1"), W_SIG, [(-6.6, 15.488), (-6.6, 15.41), (0, 15.41), (0, 15.912)]))
    R.append((("R22", "2"), W_SIG, [(-6.6, 17.312), (-3.4, 17.312)]))
    # --- 0R to the coupling cap, with the 2k2 hanging off that node
    R.append((("R02", "2"), W_SIG, [(0, 7.912), (0, 10.088)]))
    R.append((("R02", "2"), W_SIG, [(0, 9.4), (2.488, 9.4)]))
    # --- coupling cap to the 330R, with the clamp on that node
    R.append((("C01", "2"), W_SIG, [(0, 11.912), (0, 14.088)]))
    R.append((("C01", "2"), W_SIG, [(0, 13.0), (2.962, 13.0)]))
    # SOT-23 at rot 180 puts pad 1 BELOW the centre and pad 2 above it, so the
    # +3V3_A tap is the lower pad and the ground pad is the upper one.  Rev B:
    # that pad reaches the B.Cu plane by its own via, like every +3V3_A pad.
    # --- the squarer input node: 330R down the spine, test point right, the
    #     1M up from the left, and in to 1A (pin 1, top right).  Every SC-70-6
    #     track leaves its pad by the END: the pads are 0.35 mm wide with
    #     0.30 mm between them, too little for a track.
    R.append((("R04", "2"), W_SIG, [(0, 15.912), (0, 17.4), (0.65, 18.05), (0.65, 19.3625)]))
    R.append((("R04", "2"), W_SIG, [(0, 17.4), (3.0, 17.4)]))
    R.append((("R05", "1"), W_SIG, [(-3.4, 19.288), (-2.2, 18.1), (-1.5, 17.4), (0, 17.4)]))
    # --- the replica (item 18): 2A and 2Y (pins 3 and 4, the left column)
    #     tied, and the 1M's far end on them
    R.append((("U01", "3"), W_SIG, [(-0.65, 19.3625), (-0.65, 21.0375)]))
    R.append((("U01", "4"), W_SIG, [(-3.4, 21.112), (-0.65, 21.0375)]))
    # --- ground (pin 2, top middle) through the 0.65 mm gap between the rows
    #     and out to the right, between 1A and 1Y, to its via
    R.append((("U01", "2"), 0.2, [(0, 19.3625), (0, 20.2), (1.6, 20.2)]))
    # --- VCC (pin 5, bottom middle) out of its end and left along its lane
    R.append((("U01", "5"), W_SIG, [(0, 21.0375), (0, Y_VCC1), (-5.4875, Y_VCC1)]))
    R.append((("R51", "1"), W_SIG, [(-7.3125, Y_VCC1), (-7.3125, Y_VCC1 + 1.35)]))
    # --- squarer output 1Y (pin 6, bottom right) straight down to U02's D
    R.append((("U01", "6"), W_SIG, [(0.65, 21.0375), (0.65, 22.4), (0.95, 22.7),
                                    (0.95, Y_U2 - 1.1375)]))
    # --- and off it, the squarer-output tap: 1k (pad 2 on the node, pad 1
    #     outboard), then the U.FL's pin
    R.append((("U01", "6"), W_SIG, [(0.95, 23.0), (1.2875, 23.0)]))
    R.append((("J04", "1"), W_SIG, [(3.1125, 23.0), (4.975, 23.0)]))
    # its ground pads to their own vias, inboard (PLAIN_VIAS_10M)
    R.append((("J04", "2"), 0.3, [(4.9, 21.525), (5.6, 21.525)]))
    R.append((("J04", "2"), 0.3, [(4.9, 24.475), (5.6, 24.475)]))
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
    for fb, y in (("R52", Y_U2), ("R53", Y_U3)):
        R += _ic_power_routes(fb, y, RAIL_10M)
    # Rev A's rail down the gutter is gone: the B.Cu plane (item 5).
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
    R.append((("R54", "2"), W_SIG, [(2.738, vy), (0.95, vy)]))
    R.append((("R54", "2"), W_SIG, [(2.85, vy), (2.85, 17.0)]))
    R.append((("R54", "2"), W_SIG, [(2.85, vy), (2.85, 10.8)]))
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

# Rev B: plain through vias, no In2 stub -- U01's ground, and R51's +3V3_A end,
# which lands on the +3V3_A plane (item 5; until the plane exists it is an
# unconnected via).
PLAIN_VIAS_10M = [("U01", "2", 1.6, 20.2),
                  ("R51", "1", -7.3125, Y_VCC1 + 1.35),
                  # the squarer-output U.FL's ground, on its INBOARD side: at
                  # its outboard end the plane-via search put the vias on the
                  # box edge, where the right-hand units' returns leave the
                  # tile on In2, and PPS_05 and PPS_11 failed (2026-10-10)
                  ("J04", "2", 4.9, 21.525), ("J04", "2", 4.9, 24.475)]
