"""The helper oscillator and its fan-out, rev B: placement, and (not yet) its tracks.

Local coordinates: x rightwards along the chain, y = 0 is the signal line,
-y is up.  The block origin goes at (HX, HY) in board coordinates and the block
is turned so the chain runs DOWN the board's centre line, as rev A's did.

Rev B (REVB_CHANGES items 9, 10, 22) replaces rev A's block outright:

    TCXO -> 33R -> Si5351C CLKIN          (rev A: a 3k3/1k divider into XA)
    CLK0 (VDDOA) -> 0R select -> 10n -> 330R -> replica-biased squarer (U3003)
    squarer -> TWO LMK1C1108 side by side (U3004, U3005) -> 33R each -> HCLK_nn
    CLK2 (VDDOB) -> 74LVC1G125 (U3002) -> 33R -> the HO SMA   (rev A: CLK1, bare)

The two LMK1C1108 sit next to each other on one supply (FO_VDD, two 4R7 off
+3V3_D) so their delays track; rev A's five single gates were spread along the
block on +3V3_A, beside the squarers, and N1 showed their groups drifting
4-4.5 ps/K apart.

PLACEMENT ONLY, 2026-10-09: rev A's hand tracks (every one of them named by a
part that is gone) are not carried over.  routes(), VIAS and IN2_ROUTES are
empty until the block is routed again; build_pcb.py's NOHAND=1 makes a
placement preview.  The rev A version of this file is in git history
(before commit "rev B: placement preview").
"""

SIG = 0.25          # signal track
PWR = 0.5           # rail

GATE_Y = 0.0

# LMK1C1108 branch resistors, left to right under each fan-out
LMK1_R = ("R3009", "R3010", "R3011", "R3012", "R3013", "R3014", "R3015", "R3016")
LMK2_R = ("R3018", "R3019", "R3020", "R3021", "R3022", "R3023", "R3024")
X_LMK1, X_LMK2 = 56.0, 80.0
R_PITCH, R_Y = 2.2, 6.0

PARTS = {
    # ---- 25 MHz TCXO and its supply ------------------------------------
    "X3001": (0.0, 0.0, 0),
    "R3051": (1.25, -7.6, 270),
    "C3001": (-2.6, -4.9, 90),       # clear of the FT5H's 5.0 x 3.2 courtyard
    "C3002": (5.1, -4.9, 90),
    # ---- into CLKIN -------------------------------------------------------
    "R3001": (6.4, 2.0, 0),          # 33R
    "TP3001": (8.8, -1.0, 0),        # TP_REF
    "R3025": (10.6, 4.0, 90),        # 1k, item 19: TAP REF, off the CLKIN node
    "J3004": (10.6, 8.9, 0),
    # ---- the synthesiser and its two filtered supplies -----------------
    "U3001": (16.0, 0.0, 0),         # Si5351C-B-GM, QFN-20 4x4
    "R3052": (12.0, -8.4, 270),      # SI_VDD
    "C3003": (12.0, -5.0, 90),
    "C3004": (14.4, -5.0, 90),
    "R3053": (18.6, -8.4, 270),      # SI_VDDOB (HO's bank)
    "C3005": (18.6, -5.0, 90),
    "C3006": (21.0, -5.0, 90),
    "R3026": (21.0, -1.4, 90),       # 1k, item 19: TAP CLK0, at the pin
    "J3005": (25.0, -6.0, 0),
    # ---- HO: CLK2 -> buffer -> 33R -> the SMA at the top ---------------
    "U3002": (25.0, 5.0, 0),         # 74LVC1G125
    "R3054": (25.0, 9.2, 0),
    "C3007": (28.4, 8.6, 90),
    "C3008": (21.6, 8.6, 90),
    "R3002": (28.6, 3.2, 270),       # 33R to J3001
    # ---- source select: the synthesiser, or the external SMA ----------
    "R3003": (31.0, -6.0, 0),        # 51R terminator for the external input
    "R3004": (33.0, -3.2, 0),        # 0R, DNP: external in
    "R3005": (33.0, 0.0, 0),         # 0R: the synthesiser
    "C3009": (36.6, 0.0, 0),         # 10n C0G
    "R3006": (40.2, 0.0, 0),         # 330R
    # ---- the replica-biased squarer, on FO_VDD -------------------------
    "U3003": (44.6, 0.0, 0),         # 74LVC2GU04, SC-70-6
    "R3007": (44.6, 3.2, 0),         # 1M to the replica
    # ---- FO_VDD: two 4R7 off +3V3_D and four capacitors ----------------
    "R3055": (50.0, -8.4, 270),
    "R3056": (72.0, -8.4, 270),
    "C3010": (52.4, -5.4, 90),
    "C3011": (54.8, -5.4, 90),
    "C3012": (74.4, -5.4, 90),
    "C3013": (76.8, -5.4, 90),
    # ---- the two fan-outs, side by side ---------------------------------
    "U3004": (X_LMK1, 0.0, 0),       # LMK1C1108, TSSOP-16
    "R3008": (X_LMK1 - 5.6, 2.6, 270),   # 10k, 1G pull-up
    "U3005": (X_LMK2, 0.0, 0),
    "R3017": (X_LMK2 - 5.6, 2.6, 270),
    "J3003": (X_LMK2 + 22.0, 2.0, 0),    # U.FL: TAP HELPER
}
for _i, _r in enumerate(LMK1_R):
    PARTS[_r] = (X_LMK1 + 5.0 + _i * R_PITCH, R_Y, 270)
for _i, _r in enumerate(LMK2_R):
    PARTS[_r] = (X_LMK2 + 5.0 + _i * R_PITCH, R_Y, 270)

# Not routed yet (see the module note).
VIAS = []
IN2_ROUTES = []

# I2C leaves the block downwards, clear of everything, at these two x lanes.
I2C_Y = 9.5
I2C_SCL_X, I2C_SDA_X = 18.7, 20.9


def routes():
    """Rev B's helper tracks: none yet (placement preview)."""
    return []
