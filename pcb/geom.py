"""Where the board is, in millimetres, and how it relates to the PYNQ-Z2.

PYNQ frame : origin at the PYNQ's bottom-left corner, y UP.  All the measured
             numbers in round 9 are in this frame.
Board frame: KiCAD PCB, origin at OUR board's top-left, y DOWN.

    board_x = pynq_x - 72.0
    board_y = 178.0 - pynq_y

72.0 is our left edge, chosen to clear the measured HDMI right edge (69.5) by
2.5 mm.  178.0 is our top edge; our bottom edge sits at pynq y = 78, which is
2.6 mm below the even pin row, so only a 9 mm strip of us is over the PYNQ at
all and everything tall on the PYNQ stays in the open air.
"""
# ---- measured PYNQ-Z2 (round 9) -------------------------------------------
PZ_W, PZ_H      = 137.0, 87.0
HDR_MID_X       = 101.65      # midpoint of the measured pin-1/pin-39 span
HDR_PITCH       = 2.54
HDR_ODD_DY      = 3.5         # top edge to odd-row pin centres
HDR_EVEN_DY     = 6.04        # = 3.5 + exactly one pitch
HDR_PIN_H       = 8.0         # unshrouded pin tops above the PYNQ
PZ_HOLE_TR      = (133.3, 4.3)
PZ_HOLE_TL      = (4.3, 4.3)
PZ_HOLE_D       = 3.0
# What stands on the PYNQ, and whether it is under us.  We ride HDR_PIN_H =
# 8.0 mm above the PYNQ's top surface and overlap only the 11 mm strip along
# its TOP edge (PZ_BOTTOM = 76 to PZ_H = 87), so a connector matters here only
# if it is (a) on that edge and (b) taller than 8.0 mm.
#
# Round 21 re-derived the positions from the two ruled photographs
# (PYNQ-Z2_DFR0600-detail-001.jpg and ..._Dim_02.jpg) because the ETHERNET
# entry below had been misleading since round 9: the Ethernet jack is on the
# board's LEFT edge spanning y ~38..57, nowhere near our strip.  Its 13.75 mm
# would foul us if it were under us; it is not, and never was.
#
# Round 22: the HP/MIC audio jack IS on the top edge and under us, and its
# height had never been measured.  Jason measured it against the USB-A: about
# 1 mm SHORTER, so ~5.7 mm, which clears our 8.0 mm underside by ~2.3 mm.
# No notch in the bottom edge is needed.  (x, x, height, label, under_us)
PZ_TALL = [(6.0, 19.0, 13.75, "ETHERNET 13.8", False),   # LEFT edge, y 38..57
           (22.0, 30.0, 5.7, "HP/MIC JACK ~5.7", True),  # measured round 22
           (33.0, 50.0, 6.7, "USB-A 6.7", True),
           (53.0, 69.5, 6.24, "HDMI 6.2", True)]
assert all(h < HDR_PIN_H for x0, x1, h, nm, under in PZ_TALL if under), \
    "something on the PYNQ's top edge is taller than our %.1f mm ride height" % HDR_PIN_H

# ---- our board -------------------------------------------------------------
# Round 15 floorplan.  The helper runs up the VERTICAL centre line; each unit
# is a horizontal strip pointing at it:
#
#   1pps jack | 1pps block | 10 MHz jack | 10 MHz block | HELPER | ... mirrored
#
# Seven units down the left, six down the right, interleaved half a row pitch,
# so channel numbers run 1..13 straight down the board and the thirteen branch
# exits are evenly spaced along the helper band.
#
# Why this and not the two-row layout of rounds 11-14:
#   * every 10 MHz chain now ENDS at the helper, so the branches live in one
#     120 mm strip instead of spanning 200 mm of board -- they share a thermal
#     environment, which is the thing round 10 said actually matters;
#   * SMA columns on the left and right free the bottom edge, so the socket
#     stays put and the PYNQ does not have to be rotated;
#   * every cabled connector ends up on the top edge, clear of the jacks;
#   * 205 x 180 instead of 270 x 170 -- 20 % less board.  The mock-up said
#     185 x 170; the extra 10 mm each way is the price of somewhere to PUT the
#     twenty-four heaters and eight thermometers.  Packing the channels 31 %
#     tighter also leaves 31 % less room for everything that is not a channel,
#     and a heater array only works if it is distributed: with the spreading
#     length about 50 mm, heating a 175 mm-wide array from its perimeter only
#     would leave the middle at 1/cosh(87/50) = 34 % of the edge rise.  So one
#     heater goes INSIDE each tile, in the empty strip down its outboard side,
#     and the other eleven ring the array from two 10 mm margins.
PZ_BOTTOM  = 76.0        # our bottom edge in the PYNQ frame: 11.0 mm from its
                         # top edge, just clear of the HDMI at 11.5.  Unchanged,
                         # so the header, the overlap and the two shared M3
                         # standoffs are all exactly where they were.
import os as _os
_HW_EXTRA = float(_os.environ.get("HWEXTRA", "1"))   # round 20: 1 mm a side
BW, BH = 205.0 + 2.0 * _HW_EXTRA, 180.0
OX, OY = PZ_W / 2.0 - BW / 2.0, PZ_BOTTOM + BH
XC = BW / 2.0                     # the helper centre line

# 17, not 12: the helper block itself is only 19.6 mm across, but the band has
# to carry the twenty-five beat/pulse returns PAST it as well.  Thirteen of
# them run down each side, which needs 6.5 mm of lane a side at the router's
# 0.5 mm pitch; 17 leaves 7.2.  This is the single biggest cost of the round-15
# floorplan and it is what took the board from 185 wide to 205.
#
# 18, as of round 20, which takes the board to 207.  The corridors either side
# of the helper block are what the returns actually run in, and they are not
# equal: the block sits off-centre in the band, so at 17 they were 3.5 mm on
# the left for thirteen wires and 10.9 on the right for twelve.  The odd one
# out -- unit 1's beat, the outermost of the left fan -- would not route.
# Widening the BAND widens both; widening the BOARD alone does not, because
# the tiles and the helper are both placed relative to the centre line.
#
# The extra 2 mm is free.  JLCPCB's large-board fee starts at 650 cm2 and this
# board is 373; the nearest size cliff in their price list is 600 mm on a side.
# Their assembly line takes a single board up to 460 x 500 mm.  And no standard
# enclosure sits between 205 and 210: a 19-inch rack is ~450 mm inside, a
# half-rack ~215, and the nearest round number below is 200, which this board
# passed two rounds ago.
#
# 19 was measured too, and is worse: it pushes the tile columns far enough out
# to crowd the margins, and costs a courtyard overlap and four more returns.
HELPER_HW  = 17.0 + _HW_EXTRA     # half the helper band
BOX_10M_L  = 48.6                 # from pcb/tile.py
BOX_PPS_L  = 25.4
SMA_IN     = 6.0                  # jack centre, in from a block's outer end
SMA_10M_DX = HELPER_HW + BOX_10M_L - SMA_IN          # 54.6
SMA_PPS_DX = HELPER_HW + BOX_10M_L + 1.5 + BOX_PPS_L - SMA_IN   # 81.5

ROW_PITCH = 17.8         # 10 MHz block is 16.8 across plus a 1 mm rail gutter.
                         # It also sets the SMA pitch, which at 17.8 gives
                         # 8.3 mm of spanner clearance against 5.7 before.
TOP_BAND  = 36.0         # probe terminals, 15 V jack, bench posts, power.
                         # 26 was enough for the connectors but not for the
                         # power block behind them, and going to a 180 mm board
                         # is cheaper than re-laying that block out flat: it
                         # still comes in 27 % smaller than 270 x 170.
UNITS_L, UNITS_R = 7, 6
SMA_PITCH = ROW_PITCH    # kept for callers that still ask

ROWS_L = [TOP_BAND + ROW_PITCH / 2 + k * ROW_PITCH for k in range(UNITS_L)]
ROWS_R = [TOP_BAND + ROW_PITCH + k * ROW_PITCH for k in range(UNITS_R)]

# Odd channels down the left, even down the right.  With the half-pitch
# interleave that makes channel number increase monotonically down the board.
UNIT_ROW = {}
for _k, _y in enumerate(ROWS_L):
    UNIT_ROW[1 + 2 * _k] = (XC - SMA_10M_DX, _y, 90)
for _k, _y in enumerate(ROWS_R):
    UNIT_ROW[2 + 2 * _k] = (XC + SMA_10M_DX, _y, 270)

# The two helper SMAs sit at the top of the helper band, next to the oscillator
# that feeds them, instead of 150 mm away at the end of an SMA row.
# 17 mm apart, the same pitch as the channel jacks: at 13 the two coupling
# nuts left 3.5 mm of spanner room between them.
HELPER_SMA = {"HIN": (XC - 8.5, 12.0), "HO": (XC + 8.5, 12.0)}

# The five 1-Wire screw terminals along the top edge.  Here, not in
# build_pcb, because both the PLACEMENT and the hand-routed spurs that leave
# each terminal are written from it -- round 29 moved the row 3 mm and the
# spurs stayed behind, which dropped five segments and showed up as one line
# of build output.
#
# 16, and NOT the 19 round 29 first tried.  Moving the row right by 3 mm to
# make corner room for a mounting hole also moves ten resistors and five
# hand-routed spur pairs through the band the I2C bus crosses, and the board
# that came out had I2C_SDA in two pieces.  The hole moved instead; see MOUNT.
PROBE_X = [16.0 + i * 13.0 for i in range(5)]

CHANNELS = 13
TILE_H = 75.5            # a whole unit, 1 pps jack to the helper band


def B(x, y):
    """PYNQ frame -> board frame."""
    return (x - OX, OY - y)


def hdr_pin(n):
    """Board-frame (x, y) of RPi header pin n, 1..40."""
    col = (n - 1) // 2
    px = HDR_MID_X + (19 * HDR_PITCH) / 2 - col * HDR_PITCH
    py = PZ_H - (HDR_ODD_DY if n % 2 else HDR_EVEN_DY)
    return B(px, py)


def unit_origin(u):
    """(x, y, rot) of unit u's 10 MHz jack, which is its tile's local origin.

    rot 90 sends the chain to the RIGHT (left-hand units), rot 270 to the LEFT
    (right-hand units); either way it flows inward to meet the helper."""
    return UNIT_ROW[u]


def units_by_x():
    """The order units should be assigned to header pins, left to right.

    NOT simply 1..13.  The returns come down the helper band in two separate
    bundles -- one per side -- and a bundle can only unfold onto the connector
    without crossing itself if its units land on CONSECUTIVE pins.  Interleaving
    them, which is what "1..13 in row order" does, forces the two bundles to
    comb through each other in front of the socket.

    So: all the left-hand units first, then all the right-hand ones -- that part
    was right from the start, and it is what keeps the two bundles apart.  The
    LEFT bundle's terminals are at x = 85.9, west of the socket, and the right
    bundle's are at x = 119.1, above its left-hand third; give the left bundle
    the left-hand pins and the right bundle the right-hand ones and the left
    bundle's wires never have to reach as far east as the right bundle's
    descent.  Swap the groups over and every one of them crosses.

    Within a bundle, though, round 17 had the order backwards, and round 19
    turned it round.  A bundle leaves down a vertical line and lands on a
    horizontal row of pins, so in boundary order every source comes before
    every target -- two contiguous arcs of a disc, whose only non-crossing
    matching is the NESTED one.  The unit whose return leaves HIGHEST up the
    board must therefore take the pin furthest to the RIGHT, and the one
    lowest down, which is already beside the socket, takes the nearest pin.
    Hence `reversed` on each lane and not on the pair."""
    left = sorted((u for u in UNIT_ROW if UNIT_ROW[u][2] == 90),
                  key=lambda u: UNIT_ROW[u][1])
    right = sorted((u for u in UNIT_ROW if UNIT_ROW[u][2] != 90),
                   key=lambda u: UNIT_ROW[u][1])
    return left[::-1] + right[::-1]   # [13,11,9,7,5,3,1, 12,10,8,6,4,2]


def sma_rows():
    """[(x, y, tag, description)] for every jack, for the silkscreen."""
    out = []
    for u in sorted(UNIT_ROW):
        ox, oy, rot = UNIT_ROW[u]
        s = 1 if rot == 90 else -1
        out.append((ox, oy, "%d" % u,
                    "NULL 10 MHz" if u == CHANNELS else "10 MHz"))
        if u != CHANNELS:
            out.append((ox - s * (SMA_PPS_DX - SMA_10M_DX), oy, "P%d" % u,
                        "1 pps"))
    for tag, (x, y) in HELPER_SMA.items():
        out.append((x, y, tag,
                    "EXT HELPER IN" if tag == "HIN" else "CLK1 OUT"))
    return out


# ---- mounting -------------------------------------------------------------
def _pz_hole(h):
    return B(h[0], PZ_H - h[1])


def over_pynq(x, y):
    """Is this point in our board's shadow of the PYNQ-Z2?

    The PYNQ occupies board x 35..172 and board y 169..180 -- the 11 mm strip
    along our bottom edge.  A standoff DOWN to the desk cannot go there; a
    standoff that screws into the PYNQ's own mounting hole must.
    """
    return B(0.0, 0.0)[0] <= x <= B(PZ_W, 0.0)[0] and y >= B(0.0, PZ_H)[1]


# ROUND 29.  This list used to be six entries with six notes and NOTHING ELSE:
# build_pcb called put("H1".."H6"), put() looks a reference up in the netlist,
# no sheet declares a mounting-hole symbol, and put() returns quietly when it
# finds nothing.  So the board carried six comment-layer captions reading "M3
# standoff" over six places with no hole in them -- which is exactly what the
# 3D render showed, and it is what round 29 was asked about.  Each entry is
# now (xy, kind, note), build_pcb places a real NPTH footprint for it, and
# because that footprint's COURTYARD is the standoff keep-out rather than the
# hole, the courtyard-overlap check that already runs asserts the clearance.
#
# Two of the old six are gone, and both reasons are worth keeping:
#
#   * the PYNQ's TOP-LEFT hole, board (39.3, 173.3), is under the 2x10 debug
#     header -- its pin 1 pad edge is 1.6 mm from the hole's edge and well
#     inside any M3 standoff's body.  The debug header is where round 18 put
#     it after three rounds of failing to escape its signal row from anywhere
#     else.  One shared standoff plus the 2x20 header itself already locate
#     this board against the host in both axes; a second is not worth
#     re-laying out a connector for.
#   * the BOTTOM-LEFT CORNER, (5.5, 174.5), is where U5008's ferrite bead and
#     two decoupling capacitors sit -- they run down the left margin from
#     y = 161 to 176.  Not the PYNQ's fault: that corner is at board x = 5.5
#     and the PYNQ starts at x = 35.  The support moves up the same edge to
#     y = 157, the one gap between R2017's heater (ends 151.6) and U5008's
#     bead (starts 162) -- and 13 mm in from the edge, not 5.5 or 11, because
#     the six board-level margin lanes run down x = 1.4 .. 9.4 and the
#     +15V_HTR one of them ENDS at (9.4, 155).  At x = 11 the hole's keep-out
#     reached 8.9 and swallowed that lane's last millimetre, which is what
#     cost round 29's second build its one unconnected net.
MOUNT = [((4.0, 16.0), "hole",
          "M3 desk standoff, upper left - NOT the corner: J6001's terminal "
          "block reaches to x = 3.75 there, and moving the terminal row "
          "instead cost a routed I2C bus (round 29)"),
         ((BW - 5.5, 5.5), "hole", "M3 desk standoff, top-right corner"),
         ((BW - 11.0, BH - 5.5), "hole",
          "M3 desk standoff, bottom right - 11 mm in, not 5.5, to stay off "
          "the HTR_DRIVE spine that runs down x = BW - 6.2"),
         ((13.0, 157.0), "hole",
          "M3 desk standoff, lower left - the corner itself is under U5008's "
          "decoupling stack, and the six margin lanes occupy x = 1.4 to 9.4"),
         (_pz_hole(PZ_HOLE_TR), "slot",
          "M3 SLOT onto the PYNQ-Z2's own top-right mounting hole: the one "
          "standoff shared with the host.  A slot, not a hole, because the "
          "registration between the two boards runs through a 2x20 header "
          "and a set of photograph-derived dimensions good to about a "
          "millimetre")]

for _xy, _k, _n in MOUNT:
    if _k == "hole":
        assert not over_pynq(*_xy), \
            "desk standoff %s is in the PYNQ's shadow" % (_xy,)
assert over_pynq(*_pz_hole(PZ_HOLE_TR)), "the shared standoff must be over the PYNQ"
