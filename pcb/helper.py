"""The helper oscillator and its fan-out: placement and every track.

Local coordinates: x rightwards along the chain, y = 0 is the signal line,
-y is up.  The block origin goes at (HX, HY) in board coordinates.

The chain runs strictly left to right and every logic gate is at rot 0, which
on a SOT-23-5 puts the INPUT mid-left, the OUTPUT bottom-right and Vcc
top-RIGHT.  So the +3V3_D rail is a horizontal track ABOVE the chain, each
gate's ferrite drops vertically out of it into that gate's Vcc pin, and the two
decoupling capacitors hang off that vertical lane to either side.  Ground pads
are all on the underside of the chain and vent straight down to the plane.

The one part that does not fit that pattern is the Si5351.  In MSOP-10 it has
VDD on the top-left corner and VDDO on the lower-RIGHT, with CLK1, CLK0 and GND
physically between them down the right-hand edge.  There is no way to join VDD
to VDDO on F.Cu without crossing the clock outputs.  The way out is that both
of those outputs WANT to leave on In2.Cu anyway -- CLK0 goes to the CLK1-OUT
SMA 180 mm away and CLK1 is HELPER_SRC, the helper clock itself, and In2.Cu is
the layer reserved for exactly that.  So they drop to In2 within 3 mm of the
package and the VDD-to-VDDO link walks over the top of them on F.Cu.
"""

SIG = 0.25          # signal track
PWR = 0.5           # rail

RAIL_Y  = -9.0      # +3V3_D: only the TCXO and the synthesiser
RAIL_YA = -12.0     # +3V3_A: the squarer and all five buffers
GATE_Y = 0.0

# ---------------------------------------------------------------------------
# One gate's power group.  gx is the gate centre; a SOT-23-5 at rot 0 has Vcc
# at (gx + 1.1375, -0.95).
# ---------------------------------------------------------------------------
def gate_power_parts(fb, ca, cb, gx):
    vx, vy = gx + 1.1375, -0.95
    return {fb: (vx, vy - 5.3, 270),
            ca: (vx - 3.6, vy - 2.2, 180),
            cb: (vx + 3.6, vy - 2.2, 0)}


def gate_power_routes(fb, gx):
    vx, vy = gx + 1.1375, -0.95
    return [((fb, "1"), PWR, [(vx, RAIL_YA), (vx, vy - 6.212)]),
            ((fb, "2"), SIG, [(vx, vy - 4.388), (vx, vy)]),
            ((fb, "2"), SIG, [(vx - 2.65, vy - 2.2), (vx, vy - 2.2)]),
            ((fb, "2"), SIG, [(vx + 2.65, vy - 2.2), (vx, vy - 2.2)])]


# ---------------------------------------------------------------------------
# Where everything goes.
# ---------------------------------------------------------------------------
X_U3002, X_U3003 = 48.5, 59.5
BUF_X = (72.0, 83.0, 94.0, 105.0)          # the four second-stage buffers
BUF = ("U3004", "U3005", "U3006", "U3007")
# Which series resistors hang off which buffer, left to right under it.
BUF_R = (("R3008", "R3009", "R3010", "R3011"),
         ("R3012", "R3013", "R3014", "R3015"),
         ("R3016", "R3017", "R3018"),
         ("R3019", "R3020", "R3021"))
R_OFF4 = (-3.6, -1.2, 1.2, 3.6)
R_OFF3 = (-2.4, 0.0, 2.4)
R_Y, VIA_Y = 5.0, 7.6

PARTS = {
    # ---- 25 MHz TCXO and its decoupling -------------------------------
    "X3001": (0.0, 0.0, 0),          # pin3 OUT (1.25, 2.05), pin4 VDD (1.25,-2.05)
    "FB3001": (1.25, -5.6, 270),
    "C3001": (-2.6, -5.6, 90),
    "C3002": (5.1, -5.6, 90),
    # ---- 3k3 / 1k divider and the AC coupling into XA -----------------
    "R3001": (7.0, 2.05, 0),
    "TP3001": (9.4, -0.6, 0),
    "R3002": (9.4, 5.2, 270),
    "C3003": (11.6, 2.05, 0),
    # ---- the DNP crystal and the synthesiser --------------------------
    "Y3001": (16.0, 0.25, 0),
    "U3001": (24.0, 0.5, 0),
    "FB3002": (30.5, -5.6, 270),
    "C3004": (27.0, -5.6, 90),
    "C3005": (23.4, -5.6, 90),
    # ---- source select: the synthesiser, or the external SMA ----------
    "R3003": (34.0, -6.0, 0),        # 51R terminator for the external input
    "R3004": (36.0, -3.4, 0),        # 0R, DNP: external in
    "R3005": (36.0, 0.0, 0),         # 0R: the synthesiser
    "C3006": (40.0, 0.0, 0),
    "R3006": (43.8, 0.0, 0),
    # ---- squarer and first-stage buffer -------------------------------
    "U3002": (X_U3002, GATE_Y, 0),
    "R3007": (X_U3002, 3.6, 0),
    "U3003": (X_U3003, GATE_Y, 0),
}
for _i, _b in enumerate(BUF):
    PARTS[_b] = (BUF_X[_i], GATE_Y, 0)
    _offs = R_OFF4 if len(BUF_R[_i]) == 4 else R_OFF3
    for _o, _r in zip(_offs, BUF_R[_i]):
        PARTS[_r] = (BUF_X[_i] + _o, R_Y, 270)
PARTS.update(gate_power_parts("FB3003", "C3007", "C3008", X_U3002))
PARTS.update(gate_power_parts("FB3004", "C3009", "C3010", X_U3003))
for _i, (_fb, _ca, _cb) in enumerate((("FB3005", "C3011", "C3012"),
                                      ("FB3006", "C3013", "C3014"),
                                      ("FB3007", "C3015", "C3016"),
                                      ("FB3008", "C3017", "C3018"))):
    PARTS.update(gate_power_parts(_fb, _ca, _cb, BUF_X[_i]))

# Vias that take a helper signal down to In2.Cu, (slot, pad, x, y).
VIA_CLK1 = (27.6, -2.0)          # HELPER_SRC, out of the Si5351
VIA_CLK0 = (29.0, -1.2)          # CLK0, on its way to the CLK1-OUT SMA
VIA_SRC = (33.5, 0.0)            # HELPER_SRC, back up into the 0R selector
VIA_EXT = (31.8, -6.6)           # the external-helper SMA, coming up
VIAS = [("U3001", "10") + VIA_CLK1, ("U3001", "9") + VIA_CLK0,
        ("R3005", "1") + VIA_SRC, ("R3004", "1") + VIA_EXT]

# HELPER_SRC only has to get from the synthesiser's CLK1 pin to the 0R source
# selector 6 mm away, so it is routed here by hand on In2.Cu rather than handed
# to the maze router, which cannot start from a via boxed in by its neighbours.
# Over the top of the synthesiser, above the external-input via.  Under the
# chain it crossed both helper SMAs on their way down to In2.
IN2_ROUTES = [(("R3005", "1"), SIG, [VIA_CLK1, (27.6, -7.4), (33.5, -7.4),
                                     VIA_SRC])]
for _i, _b in enumerate(BUF):
    _offs = R_OFF4 if len(BUF_R[_i]) == 4 else R_OFF3
    for _o, _r in zip(_offs, BUF_R[_i]):
        VIAS.append((_r, "2", BUF_X[_i] + _o, VIA_Y))

# I2C leaves the block downwards, clear of everything, at these two x lanes.
I2C_Y = 9.5
# The lower pin turns down FIRST (closer in), or its escape crosses the
# other one: two pins leaving the same edge in the same direction have to
# nest, not swap.
I2C_SCL_X, I2C_SDA_X = 18.7, 20.9


def routes():
    R = []
    A = R.append
    # ---- TCXO power ---------------------------------------------------
    A((("FB3001", "1"), PWR, [(1.25, RAIL_Y), (1.25, -6.512)]))
    A((("FB3001", "2"), SIG, [(1.25, -4.688), (1.25, -2.05)]))
    A((("C3001", "1"), SIG, [(-2.6, -4.65), (-2.6, -3.4), (1.25, -3.4)]))
    A((("C3002", "1"), SIG, [(5.1, -4.65), (5.1, -3.4), (1.25, -3.4)]))
    # ---- TCXO out through the divider into XA -------------------------
    A((("X3001", "3"), SIG, [(1.25, 2.05), (6.088, 2.05)]))
    A((("R3001", "2"), SIG, [(7.912, 2.05), (11.25, 2.05)]))
    A((("R3001", "2"), SIG, [(9.4, 2.05), (9.4, 0.4)]))          # test point
    A((("R3001", "2"), SIG, [(9.4, 2.05), (9.4, 4.288)]))        # 1k to ground
    A((("C3003", "2"), SIG, [(12.55, 2.05), (12.55, -2.6), (20.3, -2.6),
                             (20.3, 0.0), (21.888, 0.0)]))
    A((("Y3001", "1"), SIG, [(14.9, 1.1), (13.6, 1.1), (13.6, -2.6)]))
    A((("Y3001", "3"), SIG, [(17.1, -0.6), (19.5, -0.6), (19.5, 0.5),
                             (21.888, 0.5)]))
    # ---- the synthesiser's two supply pins, linked over the top -------
    A((("FB3002", "1"), PWR, [(30.5, RAIL_Y), (30.5, -6.512)]))
    A((("FB3002", "2"), SIG, [(30.5, -4.688), (30.5, -3.0)]))
    A((("FB3002", "2"), SIG, [(21.888, -3.0), (31.0, -3.0)]))
    A((("FB3002", "2"), SIG, [(21.888, -3.0), (21.888, -0.5)]))     # VDD
    A((("FB3002", "2"), SIG, [(31.0, -3.0), (31.0, 1.0), (26.112, 1.0)]))  # VDDO
    A((("C3004", "1"), SIG, [(27.0, -4.65), (27.0, -3.0)]))
    A((("C3005", "1"), SIG, [(23.4, -4.65), (23.4, -3.0)]))
    # ---- both clock outputs drop to In2 within 3 mm of the package ----
    A((("U3001", "10"), SIG, [(26.112, -0.5), (27.6, -0.5), VIA_CLK1]))
    A((("U3001", "9"), SIG, [(26.112, 0.0), (29.0, 0.0), VIA_CLK0]))
    # ---- I2C leaves downwards in its own two lanes --------------------
    A((("U3001", "4"), SIG, [(21.888, 1.0), (I2C_SCL_X, 1.0),
                             (I2C_SCL_X, I2C_Y)]))
    A((("U3001", "5"), SIG, [(21.888, 1.5), (I2C_SDA_X, 1.5),
                             (I2C_SDA_X, I2C_Y)]))
    # ---- source select ------------------------------------------------
    A((("R3005", "1"), SIG, [VIA_SRC, (35.088, 0.0)]))
    A((("R3004", "1"), SIG, [VIA_EXT, (31.8, -3.4), (35.088, -3.4)]))
    A((("R3004", "1"), SIG, [VIA_EXT, (33.088, -6.6), (33.088, -6.0)]))
    A((("R3005", "2"), SIG, [(36.912, 0.0), (39.05, 0.0)]))
    A((("R3005", "2"), SIG, [(37.8, 0.0), (37.8, -3.4), (36.912, -3.4)]))
    # ---- coupling, bias and the squarer -------------------------------
    A((("C3006", "2"), SIG, [(40.95, 0.0), (42.888, 0.0)]))
    A((("R3006", "2"), SIG, [(44.712, 0.0), (X_U3002 - 1.1375, 0.0)]))
    A((("R3007", "1"), SIG, [(X_U3002 - 0.9125, 3.6), (46.0, 3.6), (46.0, 0.0)]))
    A((("R3007", "2"), SIG, [(X_U3002 + 0.9125, 3.6), (X_U3002 + 1.1375, 3.6),
                             (X_U3002 + 1.1375, 0.95)]))
    # ---- squarer to first-stage buffer --------------------------------
    A((("U3002", "4"), SIG, [(X_U3002 + 1.1375, 0.95), (53.0, 0.95), (53.0, 0.0),
                             (X_U3003 - 1.1375, 0.0)]))
    # ---- first stage to all four second-stage buffers: one straight bus
    #      that threads each package between its output and its Vcc pad,
    #      which is 0.53 mm of clearance either side and the shortest,
    #      most symmetric way to feed four inputs that are all at y = 0.
    A((("U3003", "4"), SIG, [(X_U3003 + 1.1375, 0.95), (62.0, 0.95), (62.0, 0.0),
                             (BUF_X[3] - 1.1375, 0.0)]))
    for fb, gx in (("FB3003", X_U3002), ("FB3004", X_U3003)):
        R += gate_power_routes(fb, gx)
    for i, fb in enumerate(("FB3005", "FB3006", "FB3007", "FB3008")):
        R += gate_power_routes(fb, BUF_X[i])
    # ---- each buffer into its three or four 33R series resistors ------
    for i, b in enumerate(BUF):
        gx = BUF_X[i]
        offs = R_OFF4 if len(BUF_R[i]) == 4 else R_OFF3
        A(((b, "4"), SIG, [(gx + 1.1375, 0.95), (gx + 1.1375, R_Y - 0.9125)]))
        A(((b, "4"), SIG, [(gx + offs[0], R_Y - 0.9125),
                           (gx + offs[-1], R_Y - 0.9125)]))
        for o, r in zip(offs, BUF_R[i]):
            A(((r, "2"), SIG, [(gx + o, R_Y + 0.9125), (gx + o, VIA_Y)]))
    # ---- the rail itself ----------------------------------------------
    A((("FB3001", "1"), PWR, [(1.25, RAIL_Y), (30.5, RAIL_Y)]))
    A((("FB3003", "1"), PWR, [(X_U3002 + 1.1375, RAIL_YA),
                              (BUF_X[3] + 1.1375, RAIL_YA)]))
    return R
