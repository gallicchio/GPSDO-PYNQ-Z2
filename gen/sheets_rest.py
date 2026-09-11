"""The four board-level sheets: Power, Helper, RPi header, Housekeeping.

Same conventions as the channel tiles: power enters from the top of a symbol,
signal flows left to right, every wire is orthogonal, and the reason for each
choice is written next to the thing it explains.
"""
import design as D
from blocks import RefGen, gnd, rail, r_h, r_v, c_h, c_v, testpoint, decouple
import kigen

NOTE = (255, 245, 210)
WARN = (255, 220, 220)
INFO = (220, 235, 255)
LEVEL = (226, 245, 226)

LDO = kigen.SYMS.alias("Regulator_Linear:LP5907MFX-3.3",
                       "GPSDO-PYNQ-Z2:TPS7A2033PDBVR",
                       pin_names={"4": "NR/SS"}, pin_types={"4": "passive"})
DS2482 = kigen.SYMS.define(
    "GPSDO-PYNQ-Z2:DS2482S-100",
    [(4, "SCL", "input", "l", 2.54), (5, "SDA", "bidirectional", "l", 0.0),
     (7, "AD1", "input", "l", -2.54), (8, "AD0", "input", "l", -5.08),
     (2, "IO", "bidirectional", "r", 2.54), (6, "~{PCTLZ}", "output", "r", -2.54),
     (1, "VCC", "power_in", "t", 0.0), (3, "GND", "power_in", "b", 0.0)],
    datasheet="datasheets/ds2482-100.pdf",
    description="I2C to 1-Wire bridge, single channel, SO-8")

FP_SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
FP_0805R = "Resistor_SMD:R_0805_2012Metric"
FP_0805C = "Capacitor_SMD:C_0805_2012Metric"
FP_1206R = "Resistor_SMD:R_1206_3216Metric"


def _head(s, title, sub):
    s.text(15.24, 20.32, title, size=3.6, bold=True)
    s.text(15.24, 26.67, sub, size=1.6, italic=True)


# ===========================================================================
def power(s):
    R = RefGen(20)
    _head(s, "POWER",
          "5 V from the RPi header -> two low-noise LDOs.  12 V from its own barrel jack -> "
          "the board heater, which never touches the analog rails.")

    # ---------------- 5 V entry and the two LDOs -------------------------
    y = 90.0
    s.rect(15.24, 36.0, 564.0, 150.0)
    s.text(19.05, 42.0, "3.3 V RAILS      header 5 V  ->  filter  ->  TPS7A2033 x2",
           size=2.6, bold=True)

    # ---- 5 V entry: two sources OR'd, then protection -------------------
    # Bench posts and the RPi header each get their own Schottky, so the two
    # can be connected at once without either back-feeding the other, and a
    # reversed bench supply is simply blocked.
    yb, yg = 55.88, 68.58
    jb = s.sym("Connector_Generic:Conn_01x01", 27.94, yb, 0, ref=R("J"),
               value="BENCH +5V",
               footprint="Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical",
               ref_dxy=(0, -6.35), val_dxy=(0, -3.81))
    s.wire(jb.pin(1)[0], yb, 29.21, yb)
    db = s.sym("Device:D_Schottky", 33.02, yb, 180, ref=R("D"), value="SS34",
               footprint="Diode_SMD:D_SMA", lcsc="C8678",
               ref_dxy=(0, 5.08), val_dxy=(0, 7.62), fang=0)
    s.wire(36.83, yb, 50.8, yb)
    s.wire(50.8, yb, 50.8, y)

    jg = s.sym("Connector_Generic:Conn_01x01", 27.94, yg, 0, ref=R("J"),
               value="BENCH GND",
               footprint="Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical",
               ref_dxy=(8.89, -1.27), val_dxy=(8.89, 1.27), justify="left")
    gnd(s, jg.pin(1)[0], yg, drop=6.35, R=R)
    s.text(52.07, yb - 1.27, "two posts, far enough apart for two mini-grabbers.",
           size=1.3, italic=True)
    s.text(52.07, yb + 2.54, "SILKSCREEN: 5 V ONLY - 12 V GOES TO THE BARREL JACK.",
           size=1.3, italic=True)

    s.glabel(22.86, y, "+5V_HDR", shape="input", justify="right")
    s.wire(22.86, y, 29.21, y)
    dh = s.sym("Device:D_Schottky", 33.02, y, 180, ref=R("D"), value="SS34",
               footprint="Diode_SMD:D_SMA", lcsc="C8678",
               ref_dxy=(0, 8.89), val_dxy=(0, 11.43), fang=0)
    s.wire(36.83, y, 53.34, y)
    s.junction(50.8, y)

    # resettable: a blown fuse a student cannot replace is a dead board
    f5 = s.sym("Device:Polyfuse", 57.15, y, 90, ref=R("F"), value="500mA PPTC",
               footprint="Fuse:Fuse_1206_3216Metric", lcsc="C720075",
               ref_dxy=(0, -8.89), val_dxy=(0, -5.08))
    s.wire(60.96, y, 69.85, y)
    dz = s.sym("Device:D_Zener", 69.85, y + 10.16, 270, ref=R("D"), value="5.6V 5W",
               footprint="Diode_SMD:D_SMB", lcsc="C19077494",
               ref_dxy=(3.81, -1.27), val_dxy=(3.81, 2.54))
    s.wire(69.85, y, *dz.pin(1))
    gnd(s, *dz.pin(2), drop=6.35, R=R)
    s.wire(69.85, y, 78.74, y)
    testpoint(s, 78.74, y, R("TP"), "TP_5V")
    s.wire(78.74, y, 87.63, y)
    s.wire(87.63, y, 87.63, y - 12.7)
    s.sym("power:PWR_FLAG", 87.63, y - 12.7, 0, ref=R.pwr(), value="PWR_FLAG",
          in_bom=False, on_board=True, hide_ref=True, val_dxy=(0, -3.81))
    s.text(95.25, y - 20.32, "the ferrite makes this a different net from +5V_HDR",
           size=1.3, italic=True)
    s.wire(87.63, y, 96.52, y)
    fb = s.sym("Device:FerriteBead", 100.33, y, 90, ref=R("FB"), value="600R@100MHz",
               footprint="Inductor_SMD:L_0805_2012Metric",
               ref_dxy=(0, -8.89), val_dxy=(0, -5.08))
    s.wire(*fb.pin(2), 304.8, y)                     # the 5 V bus to both LDOs
    for i, v in enumerate(("10u", "100n")):
        xc = 114.3 + i * 15.24                       # 15.24 apart: at 10.16 the
        cc = c_v(s, xc, y + 8.89, R("C"), v)         # 10u's label ran into the 100n
        s.wire(xc, y, *cc.pin(1))
        gnd(s, *cc.pin(2), drop=6.35, R=R)

    # ---- the two LDOs --------------------------------------------------
    for i, (rail_net, desc) in enumerate((("+3V3_A", "FRONT-END RAIL"),
                                          ("+3V3_D", "HOUSEKEEPING RAIL"))):
        x = 160.02 + i * 152.4
        u = s.sym(LDO, x, y + 20.32, 0, ref=R("U"), value="TPS7A2033PDBVR",
                  footprint=FP_SOT235, lcsc="C2862740",
                  ref_dxy=(-6.35, -19.05), val_dxy=(-6.35, -16.51))
        s.wire(u.pin(1)[0], y, *u.pin(1))                        # IN up to the bus
        s.wire(x - 20.32, y, x - 20.32, u.pin(3)[1])             # EN riser
        s.wire(x - 20.32, u.pin(3)[1], *u.pin(3))
        s.text(x - 20.32, y + 35.56, "EN tied high: always on", size=1.3, italic=True)
        gnd(s, *u.pin(2), drop=8.89, R=R)
        # NR/SS capacitor, hung below and clear of the output run
        nx = x + 17.78
        cn = c_v(s, nx, u.pin(4)[1] + 12.7, R("C"), "10n")
        s.wire(*u.pin(4), nx, u.pin(4)[1])
        s.wire(nx, u.pin(4)[1], *cn.pin(1))
        gnd(s, *cn.pin(2), drop=6.35, R=R)
        s.text(nx - 12.7, 141.0, "NR/SS: this 10 nF is what buys the 3.8 uV",
               size=1.3, italic=True)
        # output run, well above the NR/SS branch
        ox, oy = u.pin(5)
        s.wire(ox, oy, x + 60.96, oy)
        testpoint(s, x + 15.24, oy, R("TP"), "TP_" + rail_net[1:])
        for k, v in enumerate(("10u", "100n")):
            xc = x + 33.02 + k * 12.7
            cc = c_v(s, xc, oy + 8.89, R("C"), v)
            s.wire(xc, oy, *cc.pin(1))
            gnd(s, *cc.pin(2), drop=5.08, R=R)
        rail(s, x + 60.96, oy, rail_net, rise=7.62, R=R)

        s.text(x - 12.7, y - 8.89, desc, size=1.8, bold=True)

    s.note(15.24, 145.0, 122.0, 0,
           "ONE SHARED RAIL FOR EVERY THRESHOLD-SETTING GATE.\n"
           "+3V3_A feeds all 14 squarers, all 26 flip-flops, all 12 Schmitts and the whole "
           "helper fan-out.  A gate's switching threshold moves with its supply, so on a shared "
           "rail every channel's threshold moves TOGETHER - common mode, and it cancels in the "
           "differences we actually compute.  Fourteen separate regulators would make fourteen "
           "thresholds wander independently and turn a cancelling error into one that does not.",
           size=1.4, color=INFO, cols=80)
    s.note(144.78, 145.0, 122.0, 0,
           "WHY A SECOND RAIL AT ALL.\n"
           "+3V3_D carries only the Si5351, the TCXO and the I2C housekeeping parts.  None of "
           "them sets a comparison threshold, and they draw the lumpiest current on the board. "
           "Splitting them off halves the dissipation in each SOT-23 package - about 120 mW and "
           "50 mW instead of 170 mW in one - which matters on a board whose whole purpose is "
           "thermal stability.",
           size=1.4, color=INFO, cols=80)
    s.note(274.32, 145.0, 122.0, 0,
           "WHY THE TPS7A2033.\n"
           "3.8 uV RMS output noise, 300 mA, and 52 000 in stock at JLCPCB.  The obvious "
           "alternative, the ADP151, is 9 uV and 200 mA and is not stocked there at all - only "
           "re-marked house-brand parts are.  The 10 nF on NR/SS is what buys the low noise "
           "figure; without it the part is ordinary.",
           size=1.4, color=NOTE, cols=80)
    s.note(403.86, 145.0, 122.0, 0,
           "STUDENT-PROOFING THE 5 V INPUT.\n"
           "Bench supplies get set wrong.  Three things, in order: each source has its own "
           "SERIES SCHOTTKY, so reversed leads conduct nothing and the two sources cannot "
           "back-feed each other; a 500 mA PPTC, which RESETS ITSELF - nobody has to find the "
           "bag of spare fuses; and a 5.6 V 5 W Zener, which is the part that saves the board "
           "if 12 V lands on the 5 V posts.\n"
           "The Zener is what makes the fuse work: it clamps the rail near 6.1 V - under the "
           "TPS7A2033's 6.5 V absolute maximum - and draws the amp that trips the PPTC in "
           "about 100 ms.  It is the deliberate sacrificial part, and it is a 16-cent SMB on "
           "the board edge.\n"
           "What is NOT protected: sustained reverse voltage beyond the SS34's 40 V, and "
           "anything applied directly to an SMA or the header pins.",
           size=1.4, color=WARN, cols=80)
    s.note(403.86, 100.0, 122.0, 0,
           "CURRENT BUDGET, ~100 mA TOTAL.\n"
           "14 x 74LVC1GU04 self-biased in the linear region ~3 mA each = 42 mA;  26 x "
           "74LVC1G80 at 10 MHz ~1 mA each = 26 mA;  5 x 74LVC1G34 fan-out ~2 mA each = 10 mA; "
           "12 x 74LVC1G17 at 1 Hz ~ 1 mA total;  Si5351 ~25 mA.  The linear-region current of "
           "a self-biased unbuffered inverter is not a datasheet number - measure it on the "
           "first board.",
           size=1.4, color=NOTE, cols=80)

    # ---------------- 12 V heater ---------------------------------------
    yh = 250.0
    s.rect(15.24, 200.0, 564.0, 150.0)
    s.text(19.05, 206.0, "BOARD HEATER      12 V jack  ->  fuse  ->  distributed heaters  ->  "
           "linear pass FET", size=2.6, bold=True)

    jk = s.sym("Connector:Barrel_Jack", 40.64, yh, 0, ref=R("J"), value="15V 1A DC IN",
               footprint="Connector_BarrelJack:BarrelJack_Horizontal", lcsc="C720557",
               ref_dxy=(-7.62, -14.0), val_dxy=(-7.62, -11.43))
    yj = jk.pin(1)[1]
    f = s.sym("Device:Polyfuse", 71.12, yj, 90, ref=R("F"), value="500mA PPTC",
              footprint="Fuse:Fuse_1206_3216Metric", lcsc="C720075",
              ref_dxy=(0, -8.89), val_dxy=(0, -5.08))
    s.wire(jk.pin(1)[0], yj, f.pin(1)[0], yj)
    gnd(s, *jk.pin(2), drop=6.35, R=R)
    # rot 180 puts the ANODE on the left, facing the supply.  At rot 0 the
    # cathode faces the supply and the diode blocks the current it is meant to
    # pass; fang keeps the designator upright.
    dsch = s.sym("Device:D_Schottky", 96.52, yj, 180, ref=R("D"), value="SS34",
                 footprint="Diode_SMD:D_SMA", lcsc="C8678",
                 ref_dxy=(0, -8.89), val_dxy=(0, -5.08), fang=0)
    s.wire(f.pin(2)[0], f.pin(2)[1], dsch.pin(2)[0], dsch.pin(2)[1])
    s.wire(dsch.pin(1)[0], dsch.pin(1)[1], 121.92, yj)
    # rot 90 so the part stands up: at rot 0 the D_TVS body is horizontal and
    # both of these wires come out diagonal.
    # rot 270, not 90: pin 1 has to be the TOP one so the rail wire reaches it
    # without passing through pin 2 on the way.
    tv = s.sym("Device:D_TVS", 121.92, yj + 12.7, 270, ref=R("D"), value="SMAJ18A",
               footprint="Diode_SMD:D_SMA", ref_dxy=(3.81, -1.27), val_dxy=(3.81, 2.54))
    # Pin 1 to the RAIL, not to ground.  Device:D_TVS is the BIDIRECTIONAL
    # symbol, so its two pins look interchangeable -- but the part fitted is an
    # SMAJ18A, which is unidirectional, and on a D_SMA footprint pad 1 is the
    # banded cathode.  Wired the other way round the "protection" device is a
    # forward-biased diode across a 15 V supply.
    s.wire(121.92, yj, tv.pin(1)[0], tv.pin(1)[1])
    gnd(s, *tv.pin(2), drop=6.35, R=R)
    s.wire(121.92, yj, 137.16, yj)
    rail(s, 137.16, yj, "+15V_HTR", rise=12.7, R=R)
    s.wire(114.3, yj, 114.3, yj - 10.16)
    s.sym("power:PWR_FLAG", 114.3, yj - 10.16, 0, ref=R.pwr(), value="PWR_FLAG",
          in_bom=False, on_board=True, hide_ref=True, val_dxy=(0, -3.81))
    s.text(45.72, yj + 10.16, "reverse-polarity Schottky, RESETTABLE 500 mA fuse and a 16 V",
           size=1.3, italic=True)
    s.text(45.72, yj + 13.97, "TVS: a wrong supply trips the fuse, and it resets itself",
           size=1.3, italic=True)

    # Heater array: TWENTY-FOUR in parallel, not eight.  The copper's lateral
    # thermal spreading length is about 40 mm, so heaters 76 mm apart leave a
    # ripple between them; 24 sit about 44 mm apart, which is what uniformity
    # across the channel tiles actually requires.  2k0 keeps the TOTAL power at
    # 1.7 W, the same as before, and puts 72 mW in each 0805.
    # The array is placed clear of the input chain in X, not just in Y.  Sharing
    # a column with it put one heater's riser through the fuse pin at x = 67.31
    # and another through the TVS's ground drop at x = 121.92 -- shorting the
    # bus to the 12 V input, and then the rail to ground.  The input chain lives
    # in x 40..140, so the heaters start at 160 and nothing can coincide.
    xht, yht, ybus = 160.0, 240.0, 268.0
    NH = 24
    xs = []
    for i in range(NH):
        col, row = i % 12, i // 12
        # the second row is offset half a pitch in x: at the same x its risers
        # would run straight through the first row's resistors and short them
        x = xht + col * 21.59 + row * 10.8
        y = yht + row * 11.43
        rail(s, x, y - 7.62, "+15V_HTR", rise=5.08, R=R)
        r_v(s, x, y, R("R"), "1k5", footprint=FP_1206R)
        s.wire(x, y - 7.62, x, y - 3.81)
        s.wire(x, y + 3.81, x, ybus)
        xs.append(x)
    s.wire(min(xs), ybus, 452.12, ybus)
    q = s.sym("Transistor_FET:Q_NMOS_GDS", 462.28, ybus + 10.16, 0, ref=R("Q"),
              value="DMN6068SE-13", footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
              lcsc="C209902", ref_dxy=(7.62, -5.08), val_dxy=(7.62, -2.54))
    s.wire(452.12, ybus, 452.12, q.pin(2)[1])
    s.wire(452.12, q.pin(2)[1], *q.pin(2))
    s.glabel(q.pin(1)[0] - 20.32, q.pin(1)[1], "HTR_DRIVE", shape="input", justify="right")
    s.wire(q.pin(1)[0] - 20.32, q.pin(1)[1], *q.pin(1))
    gnd(s, *q.pin(3), drop=8.89, R=R)
    s.text(400.0, ybus + 26.67, "heater return: its own trace back to the jack, meeting board "
           "ground at exactly one point", size=1.4, italic=True)

    s.note(15.24, 312.0, 122.0, 0,
           "12 V ON ITS OWN JACK, HEATER ONLY.\n"
           "It never touches the 3.3 V rails or the FPGA.  The heater's 3.6 W comes from the "
           "15 V, not from the PYNQ-Z2's 5 V rail - which matters because it is twice what "
           "the rest of this board draws.  Full on is 240 mA, so a 1 A supply is plenty and "
           "the silkscreen says so.  A RESETTABLE 500 mA fuse, a series Schottky for reverse "
           "polarity and an 18 V TVS mean a wrong supply blows nothing; 18 V because a 15 V "
           "rail at +5 percent is 15.75 and a 16 V part would have sat 250 mV from conducting."
           "\n"
           "SILKSCREEN: 15 V DC, 1 A MIN - HEATER ONLY - CENTRE POSITIVE.",
           size=1.4, color=WARN, cols=80)
    s.note(144.78, 312.0, 122.0, 0,
           "LINEAR, NOT PWM - AND THAT IS DELIBERATE.\n"
           "We are making heat on purpose, so dissipation in the pass element is not waste.  A "
           "linear element means there is no switching edge anywhere on a board doing "
           "picosecond timing; a PWM heater is a few hundred mA of square wave circulating "
           "somewhere, which is exactly what the helper-tree work is trying to keep off the "
           "ground plane.",
           size=1.4, color=INFO, cols=80)
    s.note(274.32, 312.0, 122.0, 0,
           "EIGHT HEATERS, NOT ONE.\n"
           "24 x 1k5 in parallel is 62.5 ohm, so 3.6 W full on at 240 mA and 150 mW per "
           "resistor - 60 percent of a 1206 - inside "
           "the 1206 rating.  They are spread across the board because what hurts is not the "
           "mean temperature but the GRADIENT: a gradient is what makes channel 3 drift "
           "differently from channel 11.  The four corner TMP1075s are what tell you whether "
           "the spread is good enough.",
           size=1.4, color=INFO, cols=80)
    s.note(403.86, 312.0, 122.0, 0,
           "PASS FET WORST CASE.\n"
           "Dissipation peaks at half voltage: 6 V x 70 mA = 0.42 W, which a SOT-223 "
           "DMN6068SE (2 W, 60 V, 68 mohm) takes without complaint.  Drive comes from the "
           "MCP4725 on the housekeeping sheet, so the loop closes in Python on the PYNQ and "
           "costs no header pins.",
           size=1.4, color=NOTE, cols=80)


# ===========================================================================
def helper(s):
    R = RefGen(30)
    _head(s, "HELPER OSCILLATOR AND FAN-OUT",
          "Si5351A at %.7f MHz -> squarer -> a length-matched tree, one branch per channel.  "
          "Helper SKEW enters the measurement 1:1, not divided by N, so this tree is the most "
          "delicate net on the board." % (D.F_HELPER / 1e6))

    # =================== band 1: the synthesizer =========================
    y = 101.6
    s.rect(15.24, 36.0, 564.0, 114.0)
    s.text(19.05, 42.0, "SYNTHESIZER      25 MHz TCXO  ->  Si5351A  ->  CLK0", size=2.6, bold=True)

    # --- TCXO ------------------------------------------------------------
    x = s.sym("Oscillator:FT5HN", 45.72, y, 0, ref=R("X"), value="FT5HNBPK25.0-T1",
              footprint="Oscillator:Oscillator_SMD_Fox_FT5H_5.0x3.2mm",
              lcsc="C5742665", ref_dxy=(-21.59, -8.89), val_dxy=(-21.59, -6.35))
    gnd(s, *x.pin(2), drop=7.62, R=R)
    vx, vy = x.pin(4)
    decouple(s, vx, vy, "+3V3_D", R)

    # --- 3k3/1k divider into XA -------------------------------------------
    ox, oy = x.pin(3)
    s.text(55.88, oy + 6.35, "25.000000 MHz, 0/3.3 V CMOS, +/-0.5 ppm",
           size=1.3, italic=True)
    s.wire(ox, oy, 62.23, oy)
    r_h(s, 66.04, oy, R("R"), "3k3")
    s.wire(69.85, oy, 77.47, oy)
    r_v(s, 77.47, oy + 8.89, R("R"), "1k")
    s.wire(77.47, oy, 77.47, oy + 5.08)
    gnd(s, 77.47, oy + 12.7, drop=6.35, R=R)
    testpoint(s, 81.28, oy, R("TP"), "TP_XA")
    s.wire(77.47, oy, 92.71, oy)
    c_h(s, 96.52, oy, R("C"), "10n")
    s.wire(100.33, oy, 107.95, oy)
    s.text(88.9, oy + 20.32, "0.77 Vpp, 0 to +0.77 V at TP_XA -", size=1.3, italic=True)
    s.text(88.9, oy + 24.13, "the level the Si5351 actually sees, AC coupled", size=1.3, italic=True)
    s.note(210.82, 46.0, 122.0, 0,
           "DRIVING XA IS NOT A DOCUMENTED MODE, AND TP_XA IS WHY.\n"
           "The Si5351A has no CLKIN pin - only the Si5351C does - so an external reference "
           "has to go into the crystal oscillator input.  XA/XB are absolute-maximum -0.5 to "
           "+1.3 V, so the 3k3/1k knocks the TCXO's 3.3 V CMOS down to 0.77 Vpp FIRST and the "
           "10 nF then AC-couples it in, leaving XA's own internal bias intact.  Order matters: "
           "the 1k must sit on the divider, not on XA.\n"
           "Silicon Labs publish no level for this, so it is measured, not calculated.  Probe "
           "TP_XA, which is on the DRIVEN side of the coupling cap where 10 pF of probe does "
           "nothing; probing XA itself would pull the oscillator.  If the swing is outside the "
           "window, change the 1k - 620R gives 0.52 Vpp.  If it will not run at all, fit Y3001 "
           "and drop the TCXO: that is the documented mode, at the cost of +/-10 ppm.",
           size=1.4, color=WARN, cols=80)

    # --- Si5351 -----------------------------------------------------------
    si = s.sym("Oscillator:Si5351A-B-GT", 175.26, y, 0, ref=R("U"), value="SI5351A-B-GTR",
               footprint="Package_SO:MSOP-10_3x3mm_P0.5mm", lcsc="C504891",
               ref_dxy=(-13.97, 16.51), val_dxy=(-13.97, 19.05))
    xar = si.pin(2)[0] - 25.4                 # the XA riser, clear of XB's label
    s.wire(107.95, oy, xar, oy)
    s.wire(xar, oy, xar, si.pin(2)[1])
    s.wire(xar, si.pin(2)[1], *si.pin(2))
    s.glabel(xar, si.pin(2)[1] - 7.62, "SI_XA", shape="passive", justify="left", rot=90)
    s.wire(xar, si.pin(2)[1] - 7.62, xar, si.pin(2)[1])
    s.wire(*si.pin(3), si.pin(3)[0] - 8.89, si.pin(3)[1])
    s.glabel(si.pin(3)[0] - 8.89, si.pin(3)[1], "SI_XB", shape="passive", justify="right")
    s.text(139.7, si.pin(3)[1] + 3.81, "XB: open by design", size=1.3, italic=True)
    gnd(s, *si.pin(8), drop=7.62, R=R)

    # VDD and VDDO share ONE filtered node.  They are 5.08 mm apart on the
    # symbol, so two separate bead-and-cap stacks land on top of each other,
    # and the datasheet's own reference design runs both from the same 3.3 V.
    decouple(s, 175.26, 78.74, "+3V3_D", R, tall=False)
    s.wire(175.26, 78.74, 175.26, 84.0)
    s.wire(si.pin(1)[0], 84.0, si.pin(7)[0], 84.0)
    s.wire(*si.pin(1), si.pin(1)[0], 84.0)
    s.wire(*si.pin(7), si.pin(7)[0], 84.0)
    s.junction(175.26, 84.0)

    for pn, nm in ((4, "I2C_SCL"), (5, "I2C_SDA")):
        px, py = si.pin(pn)
        s.wire(px - 20.32, py, px, py)
        s.glabel(px - 20.32, py, nm, shape="bidirectional", justify="right")
    s.text(120.65, 132.08, "I2C address 0x60.  Programmed at every power-up from the PYNQ:",
           size=1.3, italic=True)
    s.text(120.65, 135.89, "PLL feedback 32 + 4142/1048575, MultiSynth 80 (INTEGER, low spur),",
           size=1.3, italic=True)
    s.text(120.65, 139.7, "R = 1  ->  CLK0 = %.7f MHz,  f_beat = %.1f Hz,  N = %.0f"
           % (D.F_HELPER / 1e6, D.F_BEAT, D.N_GAIN), size=1.3, italic=True)

    # --- CLK1 out to an SMA ------------------------------------------------
    c1x, c1y = si.pin(9)
    j1 = s.sym(D.P["SMA"]["lib"], c1x + 38.1, c1y, 0, ref=R("J"),
               value="CLK1 OUT 10.000000MHz", footprint=D.P["SMA"]["fp"],
               lcsc=D.P["SMA"]["lcsc"], ref_dxy=(2.54, -10.16), val_dxy=(2.54, -7.62))
    s.wire(c1x, c1y, j1.pin(1)[0], c1y)
    gnd(s, *j1.pin(2), drop=5.08, R=R)
    s.nc(*si.pin(6))

    # --- DNP crystal alternative -------------------------------------------
    xt = s.sym("Device:Crystal_GND24", 320.04, y, 0, ref=R("Y"), value="25MHz",
               footprint="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", dnp=True,
               ref_dxy=(-3.81, -8.89), val_dxy=(-3.81, -6.35))
    gnd(s, *xt.pin(2), drop=6.35, R=R)
    s.wire(*xt.pin(1), xt.pin(1)[0] - 12.7, xt.pin(1)[1])
    s.glabel(xt.pin(1)[0] - 12.7, xt.pin(1)[1], "SI_XA", shape="passive", justify="right")
    s.wire(*xt.pin(3), xt.pin(3)[0] + 12.7, xt.pin(3)[1])
    s.glabel(xt.pin(3)[0] + 12.7, xt.pin(3)[1], "SI_XB", shape="passive", justify="left")
    s.text(293.37, 126.0, "DNP alternative: a plain 25 MHz crystal on XA/XB.",
           size=1.3, italic=True)
    s.text(293.37, 129.81, "+/-10 ppm moves the beat +/-100 Hz, which cannot avoid",
           size=1.3, italic=True)
    s.text(293.37, 133.62, "the 60 Hz harmonic comb.  The TCXO can.", size=1.3, italic=True)

    s.note(400.05, 46.0, 170.0, 0,
           "CLK1 IS THE NULL-CHANNEL SOURCE.\n"
           "Set it to exactly 10.000000 MHz and patch this SMA to channel 13 with a short "
           "coax.  CLK1 and the helper CLK0 come off the same PLL, so their beat is exact and "
           "noiseless and anything channel 13 reports is this board alone.  Doing it with a "
           "cable rather than a jumper keeps every channel tile identical and puts a real "
           "connector and cable in the loop, which is the honest thing to measure.",
           size=1.4, color=INFO, cols=100)

    # =================== band 2: source select and squarer ================
    ys = 205.0
    s.rect(15.24, 156.0, 564.0, 84.0)
    s.text(19.05, 162.0, "SOURCE SELECT AND SQUARER      fit exactly one 0R", size=2.6, bold=True)

    c0x, c0y = si.pin(10)
    s.wire(c0x, c0y, c0x + 27.94, c0y)
    # Anchored at 127 so the whole tag sits well inside the SYNTHESIZER band.
    # A glabel at rot 270 hangs DOWNWARDS from its anchor, so at 148 the tag ran
    # past the band's bottom edge at 150 and into the gap below it.
    s.wire(c0x + 27.94, c0y, c0x + 27.94, 127.0)
    s.glabel(c0x + 27.94, 127.0, "HELPER_SRC", shape="output", justify="right", rot=270)

    jx = s.sym(D.P["SMA"]["lib"], 33.02, ys, 0, ref=R("J"), value="EXT HELPER IN",
               footprint=D.P["SMA"]["fp"], mirror="y", lcsc=D.P["SMA"]["lcsc"],
               ref_dxy=(-5.08, -10.16), val_dxy=(-5.08, -7.62))
    gnd(s, *jx.pin(2), drop=5.08, R=R)
    s.wire(jx.pin(1)[0], ys, 55.88, ys)
    r_v(s, 55.88, ys + 8.89, R("R"), "51R", left=True)
    s.wire(55.88, ys, 55.88, ys + 5.08)
    gnd(s, 55.88, ys + 12.7, drop=6.35, R=R)
    r_h(s, 66.04, ys, R("R"), "0R DNP", dnp=True)          # R_EXT, the SMA branch
    s.wire(55.88, ys, 62.23, ys)
    s.wire(69.85, ys, 88.9, ys)
    # The Si5351 arrives on its OWN branch with its OWN series 0R.  Drawn as one
    # node with two 0R feeding it, fitting both really does short CLK0 to the
    # SMA; drawn as two branches meeting at the selector node, it cannot.
    yh = ys - 15.24
    s.glabel(40.64, yh, "HELPER_SRC", shape="input", justify="right", rot=180)
    s.text(40.64, yh + 6.35, "10.0012344 MHz, 0/3.3 V CMOS, Si5351 CLK0",
           size=1.3, italic=True)
    s.wire(40.64, yh, 62.23, yh)
    r_h(s, 66.04, yh, R("R"), "0R")                        # R_INT, the Si5351 branch
    s.wire(69.85, yh, 88.9, yh)
    s.wire(88.9, yh, 88.9, ys)
    s.junction(88.9, ys)
    s.text(93.98, ys + 8.89, "SELECT: fit R_INT or R_EXT, never both.", size=1.3, italic=True)
    s.text(93.98, ys + 12.7, "Two branches, two resistors, one node.", size=1.3, italic=True)

    # squarer, same topology as a channel
    s.wire(88.9, ys, 105.41, ys)
    c_h(s, 109.22, ys, R("C"), "10n C0G")
    s.wire(113.03, ys, 125.73, ys)
    r_h(s, 129.54, ys, R("R"), "330R")
    inv = s.sym(D.P["INV"]["lib"], 162.56, ys, 0, ref=R("U"), value=D.P["INV"]["val"],
                footprint=D.P["INV"]["fp"], lcsc=D.P["INV"]["lcsc"],
                ref_dxy=(-3.81, 14.0), val_dxy=(-3.81, 16.51))
    s.wire(133.35, ys, *inv.pin(2))
    s.nc(*inv.pin(1))
    gnd(s, *inv.pin(3), drop=7.62, R=R)
    decouple(s, inv.pin(5)[0], inv.pin(5)[1], "+3V3_A", R, tall=False)
    a, b = inv.pin(2), inv.pin(4)
    yfb = ys + 24.13
    s.wires((a[0], ys), (a[0], yfb), (a[0] + 8.89, yfb))
    r_h(s, a[0] + 12.7, yfb, R("R"), "1M 1%", below=True)
    s.wires((a[0] + 16.51, yfb), (b[0], yfb), (b[0], ys))
    s.text(a[0] + 24.13, yfb + 2.54, "same self-biased squarer as every channel",
           size=1.3, italic=True)

    # first-stage buffer
    buf1 = s.sym(D.P["BUF"]["lib"], 216.0, ys, 0, ref=R("U"), value=D.P["BUF"]["val"],
                 footprint=D.P["BUF"]["fp"], lcsc=D.P["BUF"]["lcsc"],
                 ref_dxy=(-3.81, 14.0), val_dxy=(-3.81, 16.51))
    s.wire(b[0], ys, *buf1.pin(2))
    s.nc(*buf1.pin(1))
    gnd(s, *buf1.pin(3), drop=7.62, R=R)
    decouple(s, buf1.pin(5)[0], buf1.pin(5)[1], "+3V3_A", R, tall=False)
    obx, oby = buf1.pin(4)
    s.text(228.6, ys + 16.51, "BUFFERED, unlike the GU04 beside it", size=1.4, bold=True)
    s.note(432.0, 166.0, 140.0, 0,
           "WHY THE 74LVC1G34 HERE AND THE 74LVC1GU04 NEXT DOOR.\n"
           "They are opposites on purpose.  The squarer needs the UNBUFFERED GU04 because it "
           "is run inside a 1M feedback loop at its own threshold, and one gain stage in that "
           "loop cannot oscillate while three can.\n"
           "Everything after it wants the exact opposite: no feedback, no linear region, just "
           "the fastest, stiffest edge available into fourteen flip-flop clock inputs.  That is "
           "the BUFFERED G34 - three cascaded stages, ~30 ohm output, and an input slew-rate "
           "limit in its Recommended Operating Conditions that the squarer's clean edge already "
           "satisfies.  Using a GU04 here would give soft edges and multiply every flip-flop's "
           "threshold mismatch straight into skew.",
           size=1.4, color=INFO, cols=80)

    s.note(300.0, 166.0, 122.0, 0,
           "HELPER SKEW ENTERS AT FULL SCALE, 1:1.  A delay d in one channel's helper branch "
           "shifts that channel's beat by d x N, which referred back to the input is d.  Only "
           "DIFFERENTIAL drift survives: a constant is a per-channel calibration the null test "
           "removes, and a shift common to all fourteen branches cancels exactly.\n"
           "So the copper barely matters, and it is worth doing the arithmetic rather than "
           "reflexively length-matching.  FR4 carries about 6.9 ps/mm and its delay tempco is "
           "50-100 ppm/degC, so a branch MISMATCH of 100 mm - the worst this board could "
           "produce - drifts 0.7 ps over a 10 degC swing, against a 12.3 ps single-shot "
           "resolution.  Match the branches to 10 mm because it is free, not to 1 mm; the "
           "length itself is a per-channel constant the null test removes.\n"
           "SILICON is the whole problem, which is why the four second-stage buffers have to "
           "be physically ADJACENT so their tempcos track.  That is the layout constraint, and "
           "it is the only one on this sheet that is tight.",
           size=1.4, color=WARN, cols=80)

    # =================== band 3: the fan-out tree =========================
    s.rect(15.24, 246.0, 564.0, 120.0)
    s.text(19.05, 251.0, "LENGTH-MATCHED FAN-OUT      14 branches, series terminated",
           size=2.6, bold=True)

    yb = 300.0                       # the four second-stage buffers
    spine = 254.0
    per = (4, 4, 3, 3)               # 14 branches, as even as fourteen divides by four
    bxs = [120.65, 231.14, 341.63, 452.12]
    s.wire(obx, oby, obx + 7.62, oby)
    s.wire(obx + 7.62, oby, obx + 7.62, spine)
    s.wire(bxs[0] - 15.24, spine, bxs[-1] - 15.24, spine)
    s.junction(obx + 7.62, spine)

    branch = 0
    for k, bx in enumerate(bxs):
        s.wire(bx - 15.24, spine, bx - 15.24, yb)
        bf = s.sym(D.P["BUF"]["lib"], bx, yb, 0, ref=R("U"), value=D.P["BUF"]["val"],
                   footprint=D.P["BUF"]["fp"], lcsc=D.P["BUF"]["lcsc"],
                   ref_dxy=(-27.94, -1.27), val_dxy=(-27.94, 1.27))
        s.nc(*bf.pin(1))
        gnd(s, *bf.pin(3), drop=7.62, R=R)
        decouple(s, bf.pin(5)[0], bf.pin(5)[1], "+3V3_A", R, tall=False)
        # branches fan DOWNWARD, one column each, so no two labels share a row
        s.wire(bx + 12.7, yb, bx + 12.7 + (per[k] - 1) * 12.7, yb)
        for m in range(per[k]):
            cxb = bx + 12.7 + m * 12.7
            s.wire(cxb, yb, cxb, yb + 8.255)
            r_v(s, cxb, yb + 12.065, R("R"), "33R")
            s.wire(cxb, yb + 15.875, cxb, yb + 24.13)
            nm = "HELPER_CLK" if branch == 13 else "HCLK_%02d" % branch
            s.glabel(cxb, yb + 24.13, nm, shape="output", justify="right", rot=270)
            branch += 1

    s.note(15.24, 346.0, 340.0, 0,
           "WHY A 1:4 TREE AND NOT ONE GATE.  One 74LVC1G34 driving fourteen flip-flop inputs "
           "plus their traces is about 100 pF, which gives 5-8 ns edges.  Per-flip-flop clock "
           "threshold mismatch converts to skew as dV/slew, so a slow edge multiplies a 5 mV "
           "threshold difference into 12 ps instead of 3 ps.  Two stages keep every branch at "
           "1-2 ns.  33R at each driver is series termination: at a 1 ns edge the branch is a "
           "transmission line once it is longer than about 45 mm.",
           size=1.4, color=INFO, cols=200)


# ===========================================================================
def rpi_header(s):
    R = RefGen(40)
    _head(s, "RASPBERRY PI 40-PIN HEADER",
          "2x20 female socket on the underside.  Pin map taken from "
          "TUL_PYNQ_Schematic_R12.pdf sheet 4, cross-checked against Vivado's PIN_FUNC "
          "database.  Every signal pin has its own 200R series resistor on the PYNQ-Z2.")

    x0, y0 = 300.0, 66.0
    cn = s.sym("Connector_Generic:Conn_02x20_Odd_Even", x0, y0 + 24.13, 0,
               ref=R("J"), value="2x20 socket 2.54mm",
               footprint="GPSDO-PYNQ-Z2:RPiHeader_2x20_Socket_Underside",
               lcsc="C2977589", ref_dxy=(-15.24, -30.48), val_dxy=(-15.24, -27.94))

    for pin in range(1, 41):
        net, zynq, site, use = D.HEADER[pin]
        px, py = cn.pin(pin)
        left = (pin % 2 == 1)
        d = -1 if left else 1
        if net in ("+3V3_HOST",):
            s.nc(px, py)
            s.text(px + d * 39.37, py + 0.95,
                   "pin %d   3V3 from the host - NOT CONNECTED" % pin,
                   size=1.2, italic=True, justify="right bottom" if left else "left bottom")
            continue
        s.wire(px, py, px + d * (8.89 if net in ("GND", "+5V_HDR") else 20.32), py)
        # power symbols get their caption BESIDE them, not below: gnd()'s and
        # rail()'s usual 3.81 mm drop is 1.5 pin pitches and lands squarely on
        # the neighbouring pin's global label.
        if net in ("GND", "+5V_HDR"):
            s.sym("power:GND" if net == "GND" else "power:+5V",
                  px + d * 8.89, py, 0, ref=R.pwr(), value=net,
                  hide_ref=True, in_bom=False, on_board=False,
                  val_dxy=(d * 5.08, 0.48),
                  justify="left" if not left else "right")
        else:
            s.glabel(px + d * 20.32, py, net,
                     shape="input" if net.startswith(("BEAT", "PPS", "HELPER")) else "bidirectional",
                     justify="right" if left else "left", rot=180 if left else 0,
                     size=1.1)
        if zynq:
            # clear of the global label's BOX, not just its anchor: at 2.54 mm
            # pitch anything closer lands inside the label beside it
            s.text(px + d * 39.37, py + 0.95,
                   "%s   %s   %s" % (zynq, site, use), size=1.2, italic=True,
                   justify="right bottom" if left else "left bottom")

    s.note(15.24, 140.0, 122.0, 0,
           "PIN 1 AND PIN 17 ARE LEFT UNCONNECTED.\n"
           "Both are the host's 3.3 V.  We make our own 3.3 V from the header's 5 V, and not "
           "bridging to the host's rail means we cannot back-feed it.\n"
           "The TUL user manual's Table 22 shows pin 1 as GROUND; the schematic shows 3V3, and "
           "the schematic is right.  Leaving the pin open makes the question moot either way.",
           size=1.4, color=WARN, cols=80)
    s.note(144.78, 140.0, 122.0, 0,
           "THE HELPER GOES IN ON PIN 18.\n"
           "Y7 = rpio_24 = IO_L13P_T2_MRCC_13: an MRCC P-side pin in bank 13, the best clock "
           "input on the board.  The same physical pin is a "
           "dedicated PCLKT6_1 primary clock input on an Icepi Zero, so one choice serves both "
           "platforms.  Pin 31 (U18, MRCC bank 34) is the fallback.",
           size=1.4, color=INFO, cols=80)
    s.note(274.32, 140.0, 122.0, 0,
           "THE ROW SPLIT IS NOT A COINCIDENCE.\n"
           "After taking pins 3 and 5 for I2C the odd row has exactly 13 signal pins left, and "
           "after taking pin 18 for the helper the even row has exactly 12.  So every BEAT is "
           "on the odd row and every PPS on the even row, which separates the two families "
           "across the connector and makes the board-side fan-out a clean two-bus layout.",
           size=1.4, color=INFO, cols=80)
    s.note(403.86, 140.0, 122.0, 0,
           "PIN 13 IS REAL AND IS MISSING FROM THE STOCK XDC.\n"
           "Net RPIO_27_R, package pin V7, IO_L11N_T1_SRCC_13, fed through R87 (200R 1%).  The "
           "widely-circulated pynq-z2.xdc simply omits it, so anyone counting from that file "
           "finds 26 usable pins where the board has 28.  On this board it carries "
           + D.HEADER[13][0] + ".  Add the line by hand:\n"
           "set_property -dict {PACKAGE_PIN V7 IOSTANDARD LVCMOS33} [get_ports {"
           + D.HEADER[13][0].lower().replace("_", "[") + "]}]",
           size=1.4, color=NOTE, cols=80)
    s.note(15.24, 185.0, 251.0, 0,
           "2k2 PULL-UPS ARE ALREADY FITTED ON THE PYNQ-Z2 on header pins 3, 5, 27 and 28 "
           "(R305-R308), which is the standard Raspberry Pi I2C arrangement.  Do not add more "
           "on this board.  Pins 27 and 28 carry " + D.HEADER[27][0] + " and "
           + D.HEADER[28][0] + "; a 2k2 pull-up on a "
           "push-pull LVC output is 1.5 mA and harmless, and any rise/fall asymmetry it causes "
           "is a per-channel constant that the null test removes.",
           size=1.4, color=NOTE, cols=110)


# ===========================================================================
def housekeeping(s):
    R = RefGen(50)
    _head(s, "HOUSEKEEPING",
          "Eight board thermometers, the heater DAC and the debug header - all on the two I2C "
          "pins we already spend, so none of this costs a header pin.")

    # ---- I2C bus ---------------------------------------------------------
    s.text(35.56, 44.45, "I2C bus, 100 kHz.  Pull-ups are on the PYNQ-Z2 (2k2 on header pins 3 "
           "and 5), so none here.", size=1.4, italic=True)

    # ---- eight TMP1075D --------------------------------------------------
    s.rect(15.24, 66.0, 564.0, 134.0)
    s.text(19.05, 72.0, "EIGHT BOARD THERMOMETERS      TMP1075D, SOIC-8, 8 addresses from "
           "A2:A0", size=2.6, bold=True)
    where = ["board corner NW", "board corner NE", "board corner SW", "board corner SE",
             "helper fan-out cluster", "beside the two LDOs",
             "beside channel 0's squarer", "beside channel 12's squarer"]
    for i in range(8):
        x = 55.88 + i * 69.85
        y = 128.0
        u = s.sym("Sensor_Temperature:TMP1075D", x, y, 0, ref=R("U"), value="TMP1075D",
                  footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", lcsc="C2878381",
                  ref_dxy=(-10.16, -17.78), val_dxy=(-10.16, -15.24))
        decouple(s, u.pin(8)[0], u.pin(8)[1], "+3V3_D", R)
        gnd(s, *u.pin(4), drop=6.35, R=R)
        s.nc(*u.pin(3))
        for pn, nm, ybus in ((1, "I2C_SDA", 50.8), (2, "I2C_SCL", 55.88)):
            px, py = u.pin(pn)
            s.wire(px, py, px + 12.7, py)
            s.glabel(px + 12.7, py, nm, shape="bidirectional", justify="left")
        # address straps: A2 A1 A0 as the binary index
        for j, (bit, pn) in enumerate(((2, 5), (1, 6), (0, 7))):
            px, py = u.pin(pn)
            sx = px - 6.35 - j * 5.08          # one x per strap: shared risers short the rails
            s.wire(px, py, sx, py)
            if (i >> bit) & 1:
                rail(s, sx, py, "+3V3_D", rise=6.35, R=R)
            else:
                gnd(s, sx, py, drop=6.35, R=R)
        s.text(x - 12.7, y + 21.59, "0x%02X" % (0x48 + i), size=1.4, bold=True)
        s.text(x - 12.7, y + 25.4, where[i], size=1.3, italic=True)

    s.note(19.05, 162.0, 265.0, 0,
           "WHY EIGHT, AND WHY ON THE BOARD.\n"
           "Every threshold on this board moves with temperature, and the movement is meant to "
           "be common mode because all thirteen channels share one rail and one die family.  "
           "Common mode is a claim, not a fact, and these eight "
           "sensors are how it gets tested: four corners give the board's gradient, and the "
           "four in the middle sit on the parts that actually dissipate - the fan-out cluster, "
           "the two LDOs, and the squarers at each end of the channel row.",
           size=1.4, color=INFO, cols=116)
    s.note(294.0, 162.0, 285.0, 0,
           "THE ADDRESS MAP IS THE POSITION MAP.\n"
           "A2:A0 are strapped to the binary index, so the part at 0x48 is the leftmost here "
           "and the leftmost on the board, and the software never needs a lookup table telling "
           "it which sensor is where.  The eight span 0x48-0x4F, which is the whole TMP1075 "
           "address space: there is no room for a ninth, and that is the reason the DS18B20 "
           "probes hang off a 1-Wire bridge instead of being more of these.",
           size=1.4, color=NOTE, cols=125)

    # ---- heater DAC ------------------------------------------------------
    s.rect(15.24, 206.0, 564.0, 118.0)
    s.text(19.05, 212.0, "HEATER DAC", size=2.6, bold=True)
    dac = s.sym("Analog_DAC:MCP4725xxx-xCH", 100.33, 268.0, 0, ref=R("U"),
                value="MCP4725A0T-E/CH", footprint="Package_TO_SOT_SMD:SOT-23-6",
                lcsc="C144198", ref_dxy=(-15.24, -17.78), val_dxy=(-15.24, -15.24))
    decouple(s, dac.pin(3)[0], dac.pin(3)[1], "+3V3_D", R)
    gnd(s, *dac.pin(2), drop=6.35, R=R)
    for pn, nm in ((4, "I2C_SDA"), (5, "I2C_SCL")):
        px, py = dac.pin(pn)
        s.wire(px - 15.24, py, px, py)
        s.glabel(px - 15.24, py, nm, shape="bidirectional", justify="right")
    ax, ay = dac.pin(6)
    s.wire(ax - 7.62, ay, ax, ay)
    gnd(s, ax - 7.62, ay, drop=5.08, R=R)
    ox, oy = dac.pin(1)
    s.wire(ox, oy, ox + 25.4, oy)
    s.glabel(ox + 25.4, oy, "HTR_DRIVE", shape="output", justify="left")
    s.note(300.0, 216.0, 275.0, 0,
           "WHY A DAC AND A LINEAR PASS FET, AND NOT PWM.\n"
           "PWM is the cheap way to drive a heater and it is the wrong way here.  Switching "
           "amperes of heater current a few hundred times a second puts that fundamental and "
           "its harmonics into the ground plane and into the supply, and this board's whole "
           "job is measuring picoseconds of phase.  A 12-bit DAC into a linear pass FET "
           "dissipates more and radiates nothing.  The loop itself is Python on the PYNQ: read "
           "a TMP1075, write the DAC, integrate.",
           size=1.4, color=NOTE, cols=122)
    s.note(160.02, 218.0, 122.0, 0,
           "12-bit DAC straight onto the pass FET's gate.  The temperature loop runs in Python "
           "on the PYNQ: read a TMP1075, write the DAC, integrate.  Nothing switches, and it "
           "costs no header pins because it shares the I2C bus with the thermometers.",
           size=1.4, color=INFO, cols=80)

    # ---- debug header ----------------------------------------------------
    s.rect(15.24, 332.0, 455.0, 74.0)
    s.text(19.05, 338.0, "DEBUG HEADER      2x10, 0.1in, signal/ground alternating",
           size=2.6, bold=True)
    dh = s.sym("Connector_Generic:Conn_02x10_Odd_Even", 120.65, 371.0, 0, ref=R("J"),
               value="debug 2x10", lcsc=None,
               footprint="Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical",
               ref_dxy=(-12.7, -17.78), val_dxy=(-12.7, -15.24))
    # NO timing signals here.  This header is at the far edge of the board, so a
    # tap on it is a 150 mm unterminated stub on a 2 ns edge - and the damage is
    # not the delay (a per-channel constant the null test removes) but that it
    # would make two channels DIFFERENT from the other eleven, one of them the
    # null channel.  Every beat, pps and helper edge already has a test point
    # beside its own flip-flop, with a short ground return, which is a better
    # place to probe it anyway.
    sigs = ["+3V3_A", "+3V3_D", "+5V_HDR", "I2C_SDA", "I2C_SCL",
            "HTR_DRIVE", "ONEWIRE", None, None, None]
    for k in range(10):
        po, pe = dh.pin(2 * k + 1), dh.pin(2 * k + 2)
        if sigs[k] is None:
            s.nc(*po)
        else:
            s.wire(po[0], po[1], po[0] - 17.78, po[1])
            s.glabel(po[0] - 17.78, po[1], sigs[k], shape="input", justify="right",
                     rot=180)
        s.wire(pe[0], pe[1], pe[0] + 7.62 + k * 2.54, pe[1])
        gnd(s, pe[0] + 7.62 + k * 2.54, pe[1], drop=0, R=R)
    s.note(200.0, 341.0, 122.0, 0,
           "A ground on every even pin, so a scope probe's spring ground reaches the signal "
           "beside it without a clip lead - which would otherwise show you its own loop rather "
           "than the signal.\n"
           "WHAT IS DELIBERATELY NOT HERE: any beat, pps or clock.  This header sits at the "
           "far edge, so tapping one would hang a 150 mm unterminated stub on a 2 ns edge and "
           "make those channels behave differently from the rest.  Probe them at their own "
           "TP_BEAT and TP_PPS instead, where the ground return is millimetres long.",
           size=1.4, color=INFO, cols=80)


# ===========================================================================
def probes(s):
    """Five DS18B20 probes, one 3-way screw terminal each.

    The probes are moulded 3-wire assemblies: there is no way to daisy-chain
    them, so this is a five-branch star whether we like it or not, and the
    layout is built to make a star work rather than to pretend it is a line.
    """
    R = RefGen(60)
    _head(s, "1-WIRE TEMPERATURE PROBES",
          "Five DROK DS18B20 probes, three wires each, one screw terminal each.  "
          "I2C-to-1-Wire bridge at 0x18, so none of this costs a header pin.")

    # ---- the bridge -------------------------------------------------------
    s.rect(15.24, 36.0, 220.0, 140.0)
    s.text(19.05, 42.0, "I2C TO 1-WIRE BRIDGE      DS2482S-100, 0x18", size=2.6, bold=True)

    u = s.sym(DS2482, 90.17, 100.33, 0, ref=R("U"), value="DS2482S-100",
              footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", lcsc="C143306",
              ref_dxy=(-19.05, -11.43), val_dxy=(-19.05, -8.89))
    decouple(s, u.pin(1)[0], u.pin(1)[1], "+3V3_D", R)
    gnd(s, *u.pin(3), drop=6.35, R=R)
    for pn, nm in ((4, "I2C_SCL"), (5, "I2C_SDA")):
        px, py = u.pin(pn)
        s.wire(px - 15.24, py, px, py)
        s.glabel(px - 15.24, py, nm, shape="bidirectional", justify="right", rot=180)
    for j, pn in enumerate((7, 8)):
        px, py = u.pin(pn)
        sx = px - 6.35 - j * 5.08
        s.wire(px, py, sx, py)
        gnd(s, sx, py, drop=6.35, R=R)
    s.text(60.96, 128.27, "AD1 = AD0 = 0  ->  0x18", size=1.3, italic=True)
    s.nc(*u.pin(6))
    s.text(102.87, 128.27, "PCTLZ open: the strong pullup is for", size=1.3, italic=True)
    s.text(102.87, 132.08, "parasite-powered parts; ours get their own Vcc", size=1.3, italic=True)

    # IO out: 22R and the ESD clamp, both at the chip end of the star
    iox, ioy = u.pin(2)
    r_h(s, 107.95, ioy, R("R"), "22R")
    s.wire(iox, ioy, 104.14, ioy)
    s.wire(111.76, ioy, 137.16, ioy)
    tv = s.sym("Device:D_TVS", 124.46, ioy + 12.7, 90, ref=R("D"), value="PESD5V0S1BA",
               footprint="Diode_SMD:D_SOD-323", lcsc="C2827694",
               ref_dxy=(3.81, -1.27), val_dxy=(3.81, 2.54))
    s.wire(124.46, ioy, tv.pin(2)[0], tv.pin(2)[1])
    gnd(s, *tv.pin(1), drop=5.08, R=R)
    testpoint(s, 130.81, ioy, R("TP"), "TP_1W")
    s.glabel(137.16, ioy, "ONEWIRE", shape="bidirectional", justify="left")

    s.note(15.24, 142.0, 215.0, 0,
           "ADDRESSING IS NOT POSITIONAL, AND THAT MATTERS ON THE BENCH.\n"
           "The bridge is at I2C 0x18.  The five probes have NO addresses to set: each "
           "DS18B20 carries a unique 64-bit ROM code lasered in at the factory, and the "
           "DS2482's ROM Search walks the bus and finds all five.  So five on one bus is "
           "always electrically legal and can never collide.\n"
           "What it does NOT tell you is WHICH probe is which.  Do it once at bring-up: "
           "read the five ROM codes, dunk one probe in ice water, read again, and write the "
           "code on that probe's tail with a marker.  Then record the map in software.  "
           "Nothing on this board can do that for you.",
           size=1.4, color=NOTE, cols=140)

    # ---- five probe terminals --------------------------------------------
    s.rect(245.0, 36.0, 334.0, 262.0)
    s.text(248.81, 42.0, "FIVE PROBES, ONE TERMINAL EACH      no daisy chain, so a 5-way star",
           size=2.6, bold=True)

    # Every coordinate here is an exact multiple of 1.27 mm.  It has to be:
    # wire() snaps, and an off-grid bus end once snapped itself onto a
    # neighbouring branch wire and shorted GND to the 1-Wire line.
    XW, XV, XG, XT = 261.62, 281.94, 302.26, 378.46
    YG, YV, YW = 55.88, 68.58, 86.36          # bus entries, outermost highest
    y0, pitch = 100.33, 38.1                  # so no feed crosses another bus
    ys = [y0 + i * pitch for i in range(5)]

    js = [s.sym("Connector_Generic:Conn_01x03", XT, y, 0, ref=R("J"),
                value="PROBE %d" % (i + 1),
                footprint="TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-3-3.5-H"
                          "_1x03_P3.50mm_Horizontal", lcsc="C880555",
                ref_dxy=(5.08, -8.89), val_dxy=(5.08, -6.35), justify="left")
          for i, y in enumerate(ys)]

    gnd(s, 250.19, YG, drop=0, R=R)
    s.wire(250.19, YG, XG, YG)
    s.wire(XG, YG, XG, js[-1].pin(3)[1])
    rail(s, 255.27, YV, "+3V3_D", rise=6.35, R=R)
    s.wire(255.27, YV, XV, YV)
    s.wire(XV, YV, XV, js[-1].pin(2)[1])
    s.glabel(247.65, YW, "ONEWIRE", shape="bidirectional", justify="right", rot=180)
    s.wire(247.65, YW, XW, YW)
    s.wire(XW, YW, XW, js[-1].pin(1)[1])

    for j in js:
        pw, pv, pg = j.pin(1), j.pin(2), j.pin(3)   # 1 = DAT, 2 = VCC, 3 = GND
        # Vcc: its OWN 47R, so one pinched cable cannot pull +3V3_D down and
        # take the Si5351, the helper clock and every measurement with it.
        # 1206 because a dead short puts 0.23 W in it and it must survive that
        # rather than becoming an unplanned fuse.
        r_h(s, 342.9, pv[1], R("R"), "47R", footprint=FP_1206R)
        s.wire(XV, pv[1], 339.09, pv[1])
        s.wire(346.71, pv[1], pv[0], pv[1])
        # DATA: its OWN 47R, damping the reflection off this branch's stub
        r_h(s, 320.04, pw[1], R("R"), "47R")
        s.wire(XW, pw[1], 316.23, pw[1])
        s.wire(323.85, pw[1], pw[0], pw[1])
        s.wire(XG, pg[1], pg[0], pg[1])
        # Colours confirmed from photographs of the actual DROK 5-pack.
        for py, nm in ((pw[1], "1  DAT     probe YELLOW"),
                       (pv[1], "2  VCC     probe RED"),
                       (pg[1], "3  GND     probe BLACK")):
            s.text(XT + 14.0, py + 0.6, nm, size=1.3, italic=True)

    s.note(248.81, 264.0, 326.0, 0,
           "WHY EVERY BRANCH HAS TWO 47R, AND WHAT DECIDES WHETHER FIVE IN PARALLEL "
           "ACTUALLY WORK.\n"
           "THE BINDING LIMIT IS CAPACITANCE, NOT RESISTANCE.  DS2482 datasheet note 2: at "
           "STANDARD speed the total 1-Wire bus capacitance must not exceed 1 nF, and at "
           "OVERDRIVE 300 pF.  Budget: five DS18B20 DQ pins at their specified 25 pF is "
           "125 pF, the PCB is about 20 pF, which leaves 855 pF for five cables - about "
           "170 pF each.  DROK specify the harness at 100 cm, and a 3-wire cable runs "
           "60-100 pF/m, so this bus is 445-645 pF: between 35 and 55 percent below the "
           "limit even at the pessimistic end.  IT FITS, with margin.  The ceiling would be "
           "about 1.7 m per probe, so do not extend these cables.\n"
           "RUN STANDARD SPEED ONLY.  Overdrive is arithmetically impossible here: the silicon "
           "and the bare PCB are already 145 pF against a 300 pF limit, before any cable.  "
           "Leave the DS2482's 1WS bit at 0.\n"
           "THE 47R IN DATA damps the reflections off a five-way star, which is the topology "
           "1-Wire likes least.  Its size is set by the worst LOW anyone has to read: with the "
           "DS18B20's specified VOL of 0.4 V at 4 mA and the DS2482's weak pullup at its "
           "1000 ohm minimum, 47R puts that low at 0.53 V.  The binding threshold is the "
           "DS18B20's own VIL of 0.8 V MAX - an absolute number, not a fraction of VDD, and "
           "tighter than the DS2482's VIL1 of 0.9 V - so 270 mV of margin.  100R would have "
           "left 136 mV.  Fit 0R if a probe will not enumerate.\n"
           "THE 47R IN VCC stops one pinched cable pulling +3V3_D down and taking the Si5351, "
           "the helper clock and every measurement with it.  1.5 mA max while converting is "
           "0.07 V of drop, leaving the probe at 3.16 V against its 3.0 V minimum; a dead short "
           "is limited to 70 mA.  It is 1206 because that short puts 0.23 W in it.\n"
           "TP_1W IS HOW YOU CHECK ALL OF THIS.  Scope it during a conversion: the low should "
           "sit near 0.5 V and the rise should be well clear of the sample point.  Everything "
           "above is CALCULATED from the two datasheets; only the cable capacitance is an "
           "estimate, and that is the one number this test point settles.\n"
           "One spec corner, stated rather than hidden: the 0.07 V drop means DQ can idle up to "
           "70 mV above the probe's own VDD, where the datasheet asks for VPU <= VDD.  It is "
           "far below a diode drop and only exists during the 750 ms conversion.",
           size=1.4, color=INFO, cols=200)
