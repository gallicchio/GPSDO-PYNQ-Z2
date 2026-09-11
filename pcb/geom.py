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
# measured heights; the x spans are still estimates and only matter under us
PZ_TALL = [(6.0, 19.0, 13.75, "ETHERNET 13.8"), (33.0, 50.0, 6.7, "USB-A 6.7"),
           (53.0, 69.5, 6.24, "HDMI 6.2")]

# ---- our board -------------------------------------------------------------
# Round 11 floorplan.  Three things drive it:
#   * cabled connectors belong on an EDGE, so the 12 V jack and the bench posts
#     take a strip down the left and the five probe terminals a strip down the
#     right.  That is what the edges were being "saved" for.
#   * the helper fan-out sits in a band BETWEEN the two channel rows, so its
#     branches radiate instead of all running one way.  Not for length matching
#     (round 10 killed that), but because it roughly halves the longest branch
#     and so its capacitance.
#   * the board is centred on the PYNQ's own centre rather than on the header,
#     so the overhang is symmetric and the two shared M3 standoffs sit well in
#     from each end.
PZ_BOTTOM  = 76.0        # our bottom edge in the PYNQ frame: 11.0 mm from its
                         # top edge, just clear of the HDMI at 11.5
EDGE_STRIP = 20.0        # left and right connector strips
TILE_L, TILE_R = 8.4, 21.7        # how far a tile reaches either side of its
                                  # 10 MHz SMA, including the power rail that
                                  # runs in the gutter on its right
UNITS_A, UNITS_B = 7, 6           # channel tiles per row
SMA_PITCH  = 15.24                # 0.6 in.  12.7 is the standard SMA panel
                                  # pitch but leaves only 3.5 mm between
                                  # coupling nuts; 15.24 gives 6 mm of spanner
                                  # room and a 5.5 mm gutter between tiles for
                                  # the silkscreen boundary and a via fence.
UNIT_PITCH = 2 * SMA_PITCH

_tile_span = TILE_L + (UNITS_A - 1) * UNIT_PITCH + TILE_R
BW = 2 * EDGE_STRIP + 8.0 + _tile_span + 8.0        # 8 mm gutters
BW = round(BW + 4.999, -1)                          # round up to 10 mm
BH = 170.0
OX, OY = PZ_W / 2.0 - BW / 2.0, PZ_BOTTOM + BH

CENTRE_L = EDGE_STRIP + 8.0
CENTRE_R = BW - EDGE_STRIP - 8.0

def B(x, y):
    """PYNQ frame -> board frame."""
    return (x - OX, OY - y)


def hdr_pin(n):
    """Board-frame (x, y) of RPi header pin n, 1..40."""
    col = (n - 1) // 2
    px = HDR_MID_X + (19 * HDR_PITCH) / 2 - col * HDR_PITCH
    py = PZ_H - (HDR_ODD_DY if n % 2 else HDR_EVEN_DY)
    return B(px, py)


# ---- vertical bands --------------------------------------------------------
ROW_A_Y   = 16.0          # SMA row A
ROW_B_Y   = 108.0         # SMA row B
HELPER_Y  = (64.0, 98.0)  # the fan-out band, between the rows
TILE_H    = 42.6          # 10 MHz box bottom, from pcb/tile.py


def sma_rows():
    lab = []
    for u in range(1, 13):
        lab += [("%d" % u, "10 MHz"), ("P%d" % u, "1 pps")]
    lab += [("13", "NULL 10 MHz"), ("HIN", "EXT HELPER IN"), ("HO", "CLK1 OUT")]
    na = UNITS_A * 2
    rows = []
    for y, items in ((ROW_A_Y, lab[:na]), (ROW_B_Y, lab[na:])):
        span = (len(items) - 1) * SMA_PITCH
        x0 = round((CENTRE_L + CENTRE_R - span) / 2.0, 2)
        rows.append([(x0 + i * SMA_PITCH, y, t, d) for i, (t, d) in enumerate(items)])
    return rows


def unit_origin(u):
    for row in sma_rows():
        for x, y, t, d in row:
            if t == "%d" % u:
                return (x, y)
    raise KeyError(u)


def units_by_x():
    """Units in left-to-right order, which is the order the RPi pins want."""
    return [u for u, _ in sorted(((u, unit_origin(u)[0]) for u in range(1, 14)),
                                 key=lambda kv: kv[1])]


# ---- mounting -------------------------------------------------------------
def _pz_hole(h):
    return B(h[0], PZ_H - h[1])


MOUNT = [(_pz_hole(PZ_HOLE_TL), "M3 shared with PYNQ"),
         (_pz_hole(PZ_HOLE_TR), "M3 shared with PYNQ"),
         ((7.0, 7.0), "M3 standoff"), ((BW - 7.0, 7.0), "M3 standoff"),
         ((7.0, BH - 7.0), "M3 standoff"), ((BW - 7.0, BH - 7.0), "M3 standoff")]
