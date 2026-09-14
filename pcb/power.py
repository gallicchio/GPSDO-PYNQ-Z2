"""The power input block: placement and every track inside it.

Board coordinates, not local ones -- this block is pinned to the left edge by
its three cabled connectors and does not move.

Two independent supplies live here and they never touch:

  * the 15 V heater feed, barrel jack -> resettable fuse -> reverse-polarity
    Schottky -> TVS -> the low-side MOSFET that chops it;
  * the 5 V housekeeping feed, bench post OR the RPi header (two Schottkys
    OR-ing them) -> resettable fuse -> 5.6 V zener clamp -> ferrite -> two
    TPS7A2033 LDOs for +3V3_A and +3V3_D.

Above y = 58.6 only x < 27.5 is free (row A's first tile box starts there);
below it the strip widens to x < 35, which is where the LDOs live.

Both LDOs have EN tied to their own input, and on a SOT-23-5 those are pins 1
and 3 with GND (pin 2) physically between them, so neither can be reached by
running along that edge.  U2001 is fed from a lane to its LEFT and U2002 is at
rot 180 and fed from a lane to its RIGHT; each lane taps the two pins and steps
over the ground pin in between.
"""
SIG, PWR = 0.25, 0.5

# Round 15 puts this block in the top band, lying on its side: the coordinates
# below are unchanged, and the whole block is placed at rot 270 about ORIGIN,
# which maps local (lx, ly) to board (ORIGIN.x - ly, ORIGIN.y + lx).  That
# lands it in x 106..178, y 2..34 with the barrel jack opening upward at the
# board edge, without re-laying out twenty-five parts.
ORIGIN = (214.0, -1.0)
ROT = 270
LABEL_XY = (118.0, 37.0)


def place(lx, ly):
    return (ORIGIN[0] - ly, ORIGIN[1] + lx)

PARTS = {
    # ---- 15 V heater input --------------------------------------------
    "J2003": (17.0, 30.0, 0),        # barrel jack, body reaches x = 3
    "F2002": (22.5, 30.0, 0),        # 500 mA PPTC
    "D2004": (23.0, 39.0, 0),        # SS34 reverse-polarity, cathode left
    "D2005": (12.0, 45.0, 0),        # SMAJ18A, cathode (pad 1) on the RAIL
    # Q2001 used to sit here.  All three pass FETs are hand-placed now (see
    # build_pcb.hand_placed): each one goes to the centroid of the eight
    # heaters it drives, because after round 18 the groups are GEOGRAPHIC and
    # a FET beside its own heaters turns a board-spanning drain net into a
    # local one.  Its 0.8 W is wanted out there anyway.
    # ---- 5 V input and the OR-ing diodes -------------------------------
    "J2001": (6.0, 64.0, 0),         # BENCH +5V post
    "J2002": (6.0, 72.0, 0),         # BENCH GND post
    "D2001": (14.0, 64.0, 180),      # from the bench post
    "D2002": (14.0, 72.0, 0),        # from the RPi header
    "F2001": (22.0, 68.0, 270),      # 500 mA PPTC
    "TP2001": (27.0, 69.4, 0),       # TP_5V
    "D2003": (14.0, 78.0, 270),      # 5.6 V 5 W clamp, cathode up
    "FB2001": (24.0, 76.0, 270),
    "C2001": (20.0, 82.0, 0),        # 10u on the LDO input
    "C2002": (27.0, 82.0, 0),        # 100n
    # ---- the two regulators --------------------------------------------
    # BOTH at rot 180, which puts IN and EN (pins 1 and 3) on the outward
    # side and the output on the inward side.  EN is tied to IN and GND sits
    # physically between them, so each needs a lane beside the package that
    # taps both pins and steps over the ground pin in between; at rot 0 those
    # lanes would have had to cross the outputs.
    # Round 21: the two 10 nF that used to hang off pin 4 as "NR/SS" are gone
    # -- TI SBVS338H says pin 4 of the SOT-23-5 is N/C with no internal
    # connection, and that the part needs no noise-bypass capacitor.  Deleting
    # them renumbered everything after them in this block, which is why C2007
    # and C2008 no longer exist: the four output capacitors moved up two.
    "U2001": (12.0, 88.0, 180),      # +3V3_A
    "C2003": (8.0, 92.0, 180),       # 10u, +3V3_A output
    "C2004": (14.5, 92.0, 0),        # 100n, +3V3_A output
    "TP2002": (10.8625, 95.5, 0),    # TP_3V3_A
    "U2002": (28.0, 88.0, 180),      # +3V3_D
    "C2005": (23.5, 92.0, 180),      # 10u, +3V3_D output
    "C2006": (30.0, 92.0, 0),        # 100n, +3V3_D output
    "TP2003": (26.8625, 95.5, 0),    # TP_3V3_D
}

# Where each rail leaves the block, so the board-level distribution has one
# named place to start from.
EXIT_3V3A = (10.8625, 95.5)
EXIT_3V3D = (26.8625, 95.5)
EXIT_5VH = (16.0, 72.0)
EXIT_HTR = (21.0, 39.0)


def routes():
    R = []
    A = R.append
    # ---- 15 V in ------------------------------------------------------
    A((("J2003", "1"), PWR, [(17.0, 30.0), (21.1, 30.0)]))
    A((("F2002", "2"), PWR, [(23.9, 30.0), (23.9, 39.0), (25.0, 39.0)]))
    A((("D2004", "1"), PWR, [(21.0, 39.0), (21.0, 41.5), (10.0, 41.5),
                             (10.0, 45.0)]))
    # ---- 5 V in: two Schottkys OR-ing the post and the header ----------
    A((("J2001", "1"), PWR, [(6.0, 64.0), (12.0, 64.0)]))
    A((("D2001", "1"), PWR, [(16.0, 64.0), (16.0, 68.0), (12.0, 68.0),
                             (12.0, 72.0)]))
    A((("D2001", "1"), PWR, [(16.0, 64.0), (22.0, 64.0), (22.0, 66.6)]))
    # ---- fuse, clamp, test point, ferrite ------------------------------
    A((("F2001", "2"), PWR, [(22.0, 69.4), (27.0, 69.4)]))
    # y = 74.5, not 73: at 73 the run clipped the +5V_HDR pad of D2002, whose
    # SMA pad reaches 1.05 mm either side of its centre line.
    A((("F2001", "2"), PWR, [(22.0, 69.4), (22.0, 74.5), (14.0, 74.5),
                             (14.0, 75.85)]))
    A((("F2001", "2"), PWR, [(22.0, 74.5), (24.0, 74.5), (24.0, 74.94)]))
    # ---- the LDO input / enable node -----------------------------------
    # The lane runs ABOVE the two input capacitors and drops onto each one's
    # live pad from above.  Straight across at their own y it went through
    # C2001's ground pad on the way to C2002.
    A((("FB2001", "2"), SIG, [(24.0, 77.06), (24.0, 79.5)]))
    A((("FB2001", "2"), SIG, [(17.5, 79.5), (32.0, 79.5)]))
    A((("FB2001", "2"), SIG, [(19.05, 79.5), (19.05, 82.0)]))
    A((("FB2001", "2"), SIG, [(26.05, 79.5), (26.05, 82.0)]))
    A((("FB2001", "2"), SIG, [(17.5, 79.5), (17.5, 88.95)]))
    A((("FB2001", "2"), SIG, [(17.5, 88.95), (13.1375, 88.95)]))
    A((("FB2001", "2"), SIG, [(17.5, 87.05), (13.1375, 87.05)]))
    A((("FB2001", "2"), SIG, [(32.0, 79.5), (32.0, 88.95)]))
    A((("FB2001", "2"), SIG, [(32.0, 88.95), (29.1375, 88.95)]))
    A((("FB2001", "2"), SIG, [(32.0, 87.05), (29.1375, 87.05)]))
    # ---- +3V3_A --------------------------------------------------------
    A((("U2001", "4"), SIG, [(10.8625, 87.05), (7.45, 87.05)]))
    A((("U2001", "5"), PWR, [(10.8625, 88.95), (10.8625, 95.5)]))
    A((("U2001", "5"), PWR, [(10.8625, 92.0), (8.95, 92.0)]))
    A((("U2001", "5"), PWR, [(10.8625, 92.0), (13.55, 92.0)]))
    # ---- +3V3_D --------------------------------------------------------
    A((("U2002", "4"), SIG, [(26.8625, 87.05), (23.95, 87.05)]))
    A((("U2002", "5"), PWR, [(26.8625, 88.95), (26.8625, 95.5)]))
    A((("U2002", "5"), PWR, [(26.8625, 92.0), (24.45, 92.0)]))
    A((("U2002", "5"), PWR, [(26.8625, 92.0), (29.05, 92.0)]))
    return R
