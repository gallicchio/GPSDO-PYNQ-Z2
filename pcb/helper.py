"""The helper oscillator and its fan-out, rev B: placement and every track.

Local coordinates: x rightwards along the chain, y = 0 is the signal line,
-y is up.  The block origin goes at (HX, HY) in board coordinates and the block
is turned so the chain runs DOWN the board's centre line, as rev A's did:
board = (HX - y, HY + x), so local -y is the board's right and +y its left.

Rev B (REVB_CHANGES items 9, 10, 22) replaces rev A's block outright:

    TCXO -> 33R -> Si5351C CLKIN          (rev A: a 3k3/1k divider into XA)
    CLK0 (VDDOA) -> 0R select -> 10n -> 330R -> replica-biased squarer (U3003)
    squarer -> TWO LMK1C1108 (U3004, U3005) -> 33R each -> HCLK_nn
    CLK2 (VDDOB) -> 74LVC1G125 (U3002) -> 33R -> the HO SMA   (rev A: CLK1, bare)

HOW IT IS ROUTED (2026-10-09).  The first routed build left 37 nets in pieces
here: a 0.5 mm-grid router cannot get into a 0.5 mm-pitch QFN or a 0.65 mm
TSSOP, and the draft placement had never been asked to route.  So, as on
rev A, every track inside the block is drawn here, and the placement is the
one that lets them be drawn without crossing:

  * the Si5351 (U3001): SI_VDD's capacitors and 4R7 above it, where its VDD
    and VDDOC pins are; VDDOD (pin 14) steps right and up to join them;
    VDDOA (pin 11) is cut off from them by CLK0 leaving between the two, so it
    hops over CLK0 on In2.  VDDOB's capacitors and 4R7 sit below-right, at
    pin 10.  CLK2 (pin 9) dives to In2 and comes up at the HO buffer, above
    and right of the QFN, whose output leaves the block on In2 along its top
    edge.  OEB (pin 7) goes straight into the grounded paddle.  XA/XB float.
  * the squarer (U3003): ground leaves pin 2 through the gap between the two
    pad rows, the replica pins 3-4 are tied straight across, VCC leaves pin 5
    to the right and up to FO_VDD, and 1Y (pin 6) drops to In2 to reach both
    LMKs' CLKIN from above.
  * each LMK1C1108: VDD pins 5, 10 and 14 meet on a spine UNDER the package,
    between its pin rows, which leaves it upward to the 4R7 and capacitors;
    the three ground pins drop to vias under the body; every output has its
    33R level with its own pin on its own side, so no output crosses another,
    then a via to In2.  The 1G pull-up sits level with pin 2.
  * +3V3_D runs along the block's top edge (y = SPINE_Y) and drops to each
    4R7; the one below the signal line (VDDOB's) reaches it on In2.
  * the two SMAs sit above the margin lanes (board y 25-29, all In2), so HO
    and EXT HELPER IN cross those on F.Cu and drop to In2 below them.
"""
import math

SIG = 0.25          # signal track
PWR = 0.3           # a filtered supply
GATE_Y = 0.0

X_LMK1, X_LMK2 = 59.0, 84.0        # the two LMK1C1108s
SPINE_Y = -12.4                    # +3V3_D along the top edge, clear of C3007/C3008
SQ_IN2_Y = -9.5                    # HELPER_SQ's In2 run to both LMKs

PARTS = {
    # ---- 25 MHz TCXO and its supply ------------------------------------
    "X3001": (0.0, 0.0, 0),
    "R3051": (1.25, -7.6, 270),
    "C3001": (-2.6, -4.9, 90),
    "C3002": (5.1, -4.9, 90),
    # ---- into CLKIN -------------------------------------------------------
    "R3001": (6.4, 2.0, 0),          # 33R
    "TP3001": (8.8, -1.0, 0),        # TP_REF
    "R3025": (8.8, -4.1, 270),       # 1k, item 19: TAP REF, off the CLKIN node
    "J3004": (8.55, -9.4, 90),       # its U.FL, pin 1 down toward the 1k
    # ---- the synthesiser, SI_VDD above it --------------------------------
    "U3001": (16.0, 0.0, 0),         # Si5351C-B-GM, QFN-20 4x4
    "C3003": (12.0, -5.0, 90),
    "C3004": (14.4, -5.0, 90),
    "R3052": (17.4, -4.45, 180),     # SI_VDD 4R7, pad 1 (+3V3_D) to the right
    # ---- SI_VDDOB (HO's bank) below-right of pin 10 ------------------------
    "C3005": (20.4, 3.4, 0),
    "C3006": (20.4, 5.4, 0),
    "R3053": (19.45, 8.2, 90),       # its 4R7, pad 2 (VDDOB) up
    # ---- CLK0's tap, hanging below the CLK0 line ----------------------------
    "R3026": (24.8, 1.4, 90),        # 1k, item 19: TAP CLK0
    "J3005": (24.8, 5.8, 270),       # its U.FL, pin 1 up toward the 1k
    # ---- HO: CLK2 -> buffer -> 33R, above-right; out along the top edge ---
    "U3002": (23.0, -6.5, 0),        # 74LVC1G125, A on the left
    "C3007": (24.14, -10.1, 90),
    "C3008": (26.3, -10.1, 90),
    "R3054": (29.1, -8.55, 180),     # its 4R7, pad 1 (+3V3_D) to the right
    "R3002": (26.9, -5.55, 0),       # 33R to J3001
    # ---- source select: the synthesiser, or the external SMA ----------
    "R3003": (31.0, -6.0, 0),        # 51R terminator for the external input
    "R3004": (33.0, -3.2, 0),        # 0R, DNP: external in
    "R3005": (33.0, 0.0, 0),         # 0R: the synthesiser
    "C3009": (36.6, 0.0, 0),         # 10n C0G
    "R3006": (40.2, 0.0, 0),         # 330R
    # ---- the replica-biased squarer, on FO_VDD -------------------------
    "U3003": (44.6, 0.0, 0),         # 74LVC2GU04, SC-70-6
    "R3007": (42.2, 2.6, 0),         # 1M, 1A to the replica
    # ---- the tap on the fan-out's spare output ---------------------------
    "J3003": (X_LMK2 - 1.0, 5.8, 0),
}

# Each LMK1C1108: (ref, x, 1G pull-up, capacitor a, capacitor b, 4R7,
#   {output pin: its 33R}).  Pins 3, 6, 8 are the left column, 9-16 the right.
LMKS = (
    ("U3004", X_LMK1, "R3008", "C3010", "C3011", "R3055",
     {3: "R3009", 16: "R3010", 13: "R3011", 15: "R3012",
      6: "R3013", 11: "R3014", 8: "R3015", 9: "R3016"}),
    ("U3005", X_LMK2, "R3017", "C3012", "C3013", "R3056",
     {3: "R3018", 16: "R3019", 13: "R3020", 15: "R3021",
      6: "R3022", 11: "R3023", 8: "R3024"}),
)
# each output's 33R row, by pin, and how far out its via sits from the LMK
OUT_ROW = {3: -0.4, 6: 1.8, 8: 4.0, 16: -4.4, 15: -2.2, 13: 0.0, 11: 2.2, 9: 4.4}
OUT_VIA = {3: 8.6, 6: 9.6, 8: 10.6, 16: 8.6, 15: 9.6, 13: 10.6, 11: 11.6, 9: 12.6}

for _u, _x, _pu, _ca, _cb, _rf, _outs in LMKS:
    PARTS[_u] = (_x, 0.0, 0)                       # TSSOP-16
    PARTS[_pu] = (_x - 6.5, -2.6, 0)               # 1G pull-up: pad 2 (1G) inboard
    PARTS[_ca] = (_x - 1.6, -6.55, 90)             # FO_VDD capacitors, pad 1 down
    PARTS[_cb] = (_x + 1.6, -6.55, 90)
    PARTS[_rf] = (_x + 3.8, -7.6, 270)             # FO_VDD 4R7, pad 1 (+3V3_D) up
    for _pin, _r in _outs.items():
        _side = -1 if _pin <= 8 else 1
        PARTS[_r] = (_x + _side * 6.5, OUT_ROW[_pin], 180 if _side < 0 else 0)


# ---------------------------------------------------------------------------
# Pad positions, computed from the footprints rather than copied by hand.
# ---------------------------------------------------------------------------
def _tssop(k):
    return ((-2.86, -2.275 + 0.65 * (k - 1)) if k <= 8
            else (2.86, 2.275 - 0.65 * (k - 9)))


def _qfn(k):
    if k <= 5:
        return (-1.95, -1.0 + 0.5 * (k - 1))
    if k <= 10:
        return (-1.0 + 0.5 * (k - 6), 1.95)
    if k <= 15:
        return (1.95, 1.0 - 0.5 * (k - 11))
    if k <= 20:
        return (1.0 - 0.5 * (k - 16), -1.95)
    return (0.0, 0.0)


FP = {
    "R": {1: (-0.9125, 0.0), 2: (0.9125, 0.0)},
    "C": {1: (-0.95, 0.0), 2: (0.95, 0.0)},
    "SOT23_5": {1: (-1.14, -0.95), 2: (-1.14, 0.0), 3: (-1.14, 0.95),
                4: (1.14, 0.95), 5: (1.14, -0.95)},
    "SC70_6": {1: (-0.84, -0.65), 2: (-0.84, 0.0), 3: (-0.84, 0.65),
               4: (0.84, 0.65), 5: (0.84, 0.0), 6: (0.84, -0.65)},
    "TSSOP16": {k: _tssop(k) for k in range(1, 17)},
    "QFN20": {k: _qfn(k) for k in range(1, 22)},
    "UFL": {1: (-1.525, 0.0)},
    "FT5H": {1: (-1.25, -2.05), 2: (-1.25, 2.05), 3: (1.25, 2.05), 4: (1.25, -2.05)},
    "TP": {1: (0.0, 0.0)},
}
KIND = {"X3001": "FT5H", "U3001": "QFN20", "U3002": "SOT23_5", "U3003": "SC70_6",
        "U3004": "TSSOP16", "U3005": "TSSOP16", "TP3001": "TP",
        "J3003": "UFL", "J3004": "UFL", "J3005": "UFL"}


def P(ref, pad):
    """The local position of a pad, from PARTS and the footprint (KiCad's
    rotation: counter-clockwise on screen, y down)."""
    x, y, rot = PARTS[ref]
    kind = KIND.get(ref) or ref[0]
    px, py = FP[kind][int(pad)]
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    return (round(x + px * ca + py * sa, 4), round(y - px * sa + py * ca, 4))


# ---------------------------------------------------------------------------
# Filled by routes().  VIAS get an In2 stub out to the block's edge, where the
# In2 router takes them to the tiles (build_pcb.py); LOCAL_VIAS are hops
# inside the block; IN2_ROUTES are the In2 halves of those hops.
# ---------------------------------------------------------------------------
VIAS = []
LOCAL_VIAS = []
IN2_ROUTES = []
# Ground pads the plane-via search must leave alone: U3001's paddle is tied
# to pin 7, whose own via is drawn above.
NO_PLANE_VIA = {("U3001", "21")}


def routes():
    """Every F.Cu track inside the block, as ((ref, pad), width, [points])."""
    R, I2 = [], []
    del VIAS[:], LOCAL_VIAS[:]

    def f(ref, pad, w, *pts):
        R.append(((ref, str(pad)), w, list(pts)))

    def n(ref, pad, w, *pts):
        I2.append(((ref, str(pad)), w, list(pts)))

    def lv(ref, pad, x, y):
        LOCAL_VIAS.append((ref, str(pad), x, y))

    # ---- TCXO: supply, and out through 33R into CLKIN ---------------------
    f("X3001", 4, PWR, P("X3001", 4), P("R3051", 2))
    f("X3001", 4, PWR, P("C3001", 1), P("C3002", 1))
    f("X3001", 3, SIG, P("X3001", 3), (1.25, 2.0), P("R3001", 1))
    clkin = P("U3001", 6)
    f("R3001", 2, SIG, P("R3001", 2), (clkin[0], 2.0), clkin)
    f("R3001", 2, SIG, (8.8, 2.0), P("TP3001", 1), P("R3025", 2))
    f("R3025", 1, SIG, P("R3025", 1), (8.55, -5.6), P("J3004", 1))

    # ---- U3001's supplies ---------------------------------------------------
    p20, p18, p14, p11 = P("U3001", 20), P("U3001", 18), P("U3001", 14), P("U3001", 11)
    f("U3001", 20, SIG, p20, (p20[0], -3.0), (p18[0], -3.0), p18)
    f("U3001", 20, PWR, (15.5, -3.0), (15.5, -4.05))
    f("U3001", 20, PWR, P("C3003", 1), (P("R3052", 2)[0], -4.05))
    f("U3001", 14, SIG, p14, (18.8, p14[1]), (18.8, -3.0), (p18[0], -3.0))
    # VDDOA: over CLK0 on In2
    f("U3001", 11, SIG, p11, (19.4, p11[1]), (19.8, 1.3))
    lv("U3001", 11, 19.8, 1.3)
    n("U3001", 11, SIG, (19.8, 1.3), (19.8, -3.0))
    lv("U3001", 11, 19.8, -3.0)
    f("U3001", 11, SIG, (19.8, -3.0), (18.8, -3.0))
    # OEB into the grounded paddle, and both to a via in the gap below pin 7
    # (the plane-via search would have put one 2.8 mm away, across CLKIN)
    f("U3001", 7, SIG, P("U3001", 7), (15.5, 1.2))
    f("U3001", 7, SIG, P("U3001", 7), (15.5, 2.6), (15.2, 3.15))
    lv("U3001", 7, 15.2, 3.15)
    # VDDOB down and right to its capacitors and 4R7
    p10 = P("U3001", 10)
    f("U3001", 10, SIG, p10, (p10[0], P("C3005", 1)[1]), P("C3005", 1))
    f("U3001", 10, PWR, P("C3005", 1), P("C3006", 1), P("R3053", 2))
    # I2C: a via each beside the pins; the router takes them to the bus
    p4, p5 = P("U3001", 4), P("U3001", 5)
    f("U3001", 5, SIG, p5, (12.6, p5[1]))
    lv("U3001", 5, 12.6, p5[1])
    f("U3001", 4, SIG, p4, (13.3, p4[1]), (11.6, 0.0))
    lv("U3001", 4, 11.6, 0.0)

    # ---- CLK0: along the signal line to the select resistor; its tap -----
    f("U3001", 13, SIG, P("U3001", 13), P("R3005", 1))
    f("R3026", 1, SIG, P("R3026", 1), P("J3005", 1))

    # ---- CLK2: down to In2, up at the HO buffer above-right ----------------
    p9 = P("U3001", 9)
    f("U3001", 9, SIG, p9, (p9[0], 2.9), (16.1, 3.9))
    lv("U3001", 9, 16.1, 3.9)
    n("U3001", 9, SIG, (16.1, 3.9), (16.1, -3.6), (19.0, -6.5), (20.4, -6.5))
    lv("U3001", 9, 20.4, -6.5)
    f("U3001", 9, SIG, (20.4, -6.5), P("U3002", 2))
    # its supply
    f("U3002", 5, PWR, P("U3002", 5), P("C3007", 1), P("C3008", 1), P("R3054", 2))
    # its output, 33R, then In2 along the top edge to the HO SMA
    f("U3002", 4, SIG, P("U3002", 4), P("R3002", 1))
    f("R3002", 2, SIG, P("R3002", 2), (28.85, -6.6))
    lv("R3002", 2, 28.85, -6.6)
    n("R3002", 2, SIG, (28.85, -6.6), (28.85, -13.0), (-7.0, -13.0), (-9.0, -8.7))
    lv("R3002", 2, -9.0, -8.7)
    f("R3002", 2, SIG, (-9.0, -8.7), (-28.0, -8.7))         # J3001's centre pin

    # ---- EXT HELPER IN: from its SMA on F.Cu, In2 below the lanes ----------
    f("R3003", 1, SIG, (-28.0, 8.3), (-9.0, 8.3))           # J3002's centre pin
    lv("R3003", 1, -9.0, 8.3)
    n("R3003", 1, SIG, (-9.0, 8.3), (-7.0, 7.0), (29.6, 7.0), (29.6, -4.6))
    lv("R3003", 1, 29.6, -4.6)
    r31, r41 = P("R3003", 1), P("R3004", 1)
    f("R3003", 1, SIG, (29.6, -4.6), (r31[0], -4.6), r31)
    f("R3003", 1, SIG, (r31[0], -4.6), (r31[0], r41[1]), r41)

    # ---- the select node, the coupling capacitor, 330R ---------------------
    f("R3005", 2, SIG, P("R3005", 2), P("C3009", 1))
    f("R3004", 2, SIG, P("R3004", 2), (34.7, -3.2), (34.7, 0.0))
    f("C3009", 2, SIG, P("C3009", 2), P("R3006", 1))

    # ---- the squarer --------------------------------------------------------
    a1, gnd2, a2, y2, vcc, y1 = (P("U3003", k) for k in (1, 2, 3, 4, 5, 6))
    f("R3006", 2, SIG, P("R3006", 2), (42.4, 0.0), (42.4, a1[1]), a1)
    f("R3006", 2, SIG, P("R3006", 2), P("R3007", 1))
    f("U3003", 3, SIG, a2, y2)                                  # replica tied
    f("U3003", 3, SIG, a2, (43.4, 1.3), (P("R3007", 2)[0], 1.9))
    f("U3003", 2, 0.2, gnd2, (44.6, 0.0), (44.6, -1.7))         # ground, between rows
    lv("U3003", 2, 44.6, -1.7)
    f("U3003", 5, PWR, vcc, (47.3, 0.0), (47.3, -5.6),
      (X_LMK1 - 7.4125, -5.6))                                  # VCC to FO_VDD
    f("U3003", 6, SIG, y1, (46.5, y1[1]), (46.5, -1.4))         # 1Y down to In2
    lv("U3003", 6, 46.5, -1.4)
    n("U3003", 6, SIG, (46.5, -1.4), (46.5, SQ_IN2_Y), (X_LMK2 - 3.3, SQ_IN2_Y))

    # ---- the two LMK1C1108s ---------------------------------------------------
    for u, X, pu, ca, cb, rf, outs in LMKS:
        # CLKIN from above, off the In2 run
        n("U3003", 6, SIG, (X - 3.3, SQ_IN2_Y), (X - 3.3, -3.8))
        lv(u, 1, X - 3.3, -3.8)
        f(u, 1, SIG, (X - 3.3, -3.8), (X - 3.3, P(u, 1)[1]))
        # VDD 5, 10, 14 under the body, and up to the 4R7 and capacitors
        f(u, 5, PWR, P(u, 5), (X, P(u, 5)[1]))
        f(u, 14, PWR, P(u, 14), (X, P(u, 14)[1]))
        f(u, 10, PWR, P(u, 10), (X, P(u, 10)[1]), (X, -5.6))
        f(u, 5, PWR, (P(pu, 1)[0], -5.6), (P(rf, 2)[0], -5.6), P(rf, 2))
        f(u, 5, PWR, P(pu, 1), (P(pu, 1)[0], -5.6))
        f(u, 5, PWR, P(ca, 1), (P(ca, 1)[0], -5.6))
        f(u, 5, PWR, P(cb, 1), (P(cb, 1)[0], -5.6))
        # ground pins to vias under the body
        p4g, p7g, p12g = P(u, 4), P(u, 7), P(u, 12)
        f(u, 4, SIG, p4g, (X - 1.5, p4g[1]), (X - 1.2, -0.45))
        lv(u, 4, X - 1.2, -0.45)
        f(u, 7, SIG, p7g, (X - 1.2, p7g[1]))
        lv(u, 7, X - 1.2, p7g[1])
        f(u, 12, SIG, p12g, (X + 1.2, p12g[1]))
        lv(u, 12, X + 1.2, p12g[1])
        # 1G to its pull-up
        p2 = P(u, 2)
        f(u, 2, SIG, p2, (X - 4.4, p2[1]), (X - 5.0, -2.3), P(pu, 2))
        # outputs: pin -> its 33R level with it -> a via to In2
        for pin, r in outs.items():
            side = -1 if pin <= 8 else 1
            pp, row = P(u, pin), OUT_ROW[pin]
            f(u, pin, SIG, pp, (X + side * 4.4, pp[1]), (X + side * 5.0, row), P(r, 1))
            if r == "R3024":                     # the spare output: the tap U.FL
                far = P(r, 2)
                f(r, 2, SIG, far, (far[0], 5.8), P("J3003", 1))
                continue
            vx = X + side * OUT_VIA[pin]
            f(r, 2, SIG, P(r, 2), (vx, row))
            VIAS.append((r, "2", vx, row))

    # FO_VDD is one net: the two clusters joined, above U3004's outputs
    f("U3004", 5, PWR, (P("R3055", 2)[0], -5.6), (X_LMK2 - 7.4125, -5.6))

    # ---- +3V3_D along the top edge, and down to each 4R7 ------------------
    f("R3051", 1, PWR, (P("R3051", 1)[0], SPINE_Y), (99.0, SPINE_Y))
    for ref in ("R3051", "R3052", "R3054", "R3055", "R3056"):
        p = P(ref, 1)
        f(ref, 1, PWR, (p[0], SPINE_Y), p)
    # VDDOB's 4R7 is below the signal line: up on In2
    r53 = P("R3053", 1)
    f("R3053", 1, PWR, r53, (r53[0], 9.4))
    lv("R3053", 1, r53[0], 9.4)
    n("R3053", 1, PWR, (r53[0], 9.4), (30.6, 9.4), (30.6, SPINE_Y))
    lv("R3053", 1, 30.6, SPINE_Y)

    IN2_ROUTES[:] = I2
    return R
