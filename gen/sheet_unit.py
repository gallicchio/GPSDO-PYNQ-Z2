"""One channel tile: a 10 MHz DDMTD front end plus its 1 pps front end.

Thirteen of these are generated, identical in layout and differing only in names,
per-channel population and the expected levels for that channel's source, so that
paging through the PDF shows the differences immediately.  Unit 13 is the null
channel; its pps band is replaced by a note in exactly the same place.

Page is A2 (594 x 420) so that nothing has to be crowded:
    y  14 -  34   heading
    y  38 - 190   10 MHz circuit band     signal line at y = 105.41
    y 195 - 227   notes for the 10 MHz band
    y 232 - 350   1 pps circuit band      signal line at y = 292.10
    y 353 - 379   notes for the pps band
Power always enters from the top of a symbol; signal always flows left to right;
every wire is orthogonal.
"""
import design as D
import kigen
from blocks import RefGen, gnd, rail, r_h, r_v, c_h, c_v, testpoint, decouple

# Rev B item 18: one body for both halves of the 74LVC2GU04, drawn the way the
# circuit flows (the stock symbol is three units).  Pinout from Nexperia's
# 74LVC2GU04 (SOT363) and TI's SN74LVC2GU04 (DCK), which agree:
# 1 1A, 2 GND, 3 2A, 4 2Y, 5 VCC, 6 1Y.
INV2_SYM = kigen.SYMS.define(
    "GPSDO-PYNQ-Z2:74LVC2GU04",
    [(1, "1A", "input", "l", 0.0), (3, "2A", "input", "l", -5.08),
     (6, "1Y", "output", "r", 0.0), (4, "2Y", "output", "r", -5.08),
     (5, "VCC", "power_in", "t", 0.0), (2, "GND", "power_in", "b", 0.0)],
    datasheet="datasheets/Nexperia_74LVC2GU04.pdf",
    description="Dual unbuffered inverter: half 1 squares, half 2 is its replica bias")

Y10 = 105.41
YPP = 296.00
RAIL_A = "+3V3_A"
NOTE = (255, 245, 210)
WARN = (255, 220, 220)
INFO = (220, 235, 255)
LEVEL = (226, 245, 226)


def build(s, u):
    n, beat, pps, source, term, rser, rsh2, note = u
    hclk = "HCLK_%02d" % (n - 1)
    t = "%02d" % n
    R = RefGen(n)
    L = D.levels(n, term, rser, rsh2)

    s.text(15.24, 20.32, "UNIT %d   -   %s" % (n, source), size=3.6, bold=True)
    s.text(15.24, 26.67,
           "10 MHz DDMTD front end + 1 pps front end.  Every unit sheet has this same layout; "
           "only the names, the per-channel population and the expected levels differ.",
           size=1.6, italic=True)
    s.text(15.24, 31.75,
           "OUT  %s  ->  sheet 'RPi header'%s          IN  HELPER_FANOUT  <-  sheet 'Helper'"
           % (beat, ("          OUT  %s  ->  sheet 'RPi header'" % pps) if pps
              else "          (this unit has no pps)"), size=1.6, italic=True)
    if note:
        s.note(365.76, 12.7, 213.36, 20.32, "PER-CHANNEL NOTE\n" + note,
               size=1.5, color=(255, 235, 200))

    _ten_mhz(s, R, beat, hclk, rser, rsh2, term, L)
    _ten_mhz_notes(s, L, term)
    if pps:
        _pps(s, R, pps)
        _pps_notes(s)
    else:
        s.rect(15.24, 240.0, 564.0, 114.0)
        s.note(22.86, 248.0, 548.0, 98.0,
               "1 pps front end deliberately omitted on unit 13.\n\n"
               "This is the NULL channel.  It exists to measure the instrument rather than a "
               "GPSDO, so there is no pps to time.  The circuit that would sit here on units 1 "
               "to 12 is drawn in exactly the same place on every other unit sheet, so that "
               "paging through this PDF shows only real differences.\n\n"
               "The 10 MHz half above is fully populated, and its SMA is fed by a coax patch "
               "lead from whatever you want to measure the instrument against:\n\n"
               "    the HO jack on the Helper sheet  -  Si5351C CLK2, buffered, at exactly "
               "10.000000 MHz, from PLLB in integer mode (25 MHz x 32 / 80) while the helper "
               "is PLLA: one TCXO, so the beat is exactly %.1f Hz, but two PLLs, so what this "
               "channel reports is the front end plus whatever the PLLs do not share.  An UPPER "
               "BOUND on the instrument floor.\n"
               "    a splitter off one real GPSDO into two channels  -  the other half of the "
               "floor: two real front ends, no PLL noise at all\n\n"
               "There is no jumper: a patch lead keeps every channel tile identical and puts a "
               "real connector and cable in the loop, which is the honest thing to measure."
               % D.F_BEAT,
               size=2.0, color=(225, 240, 225))


# ---------------------------------------------------------------------------
def _ten_mhz(s, R, beat, hclk, rser, rsh2, term, L):
    y = Y10
    s.rect(15.24, 38.0, 564.0, 162.0)
    s.text(19.05, 44.45, "10 MHz  DDMTD CHANNEL      terminate  ->  AC couple  ->  square  "
           "->  sample  ->  retime", size=2.6, bold=True)

    # --- SMA --------------------------------------------------------------
    p = D.P["SMA"]
    j = s.sym(p["lib"], 40.64, y, 0, ref=R("J"), value="10MHz IN", footprint=p["fp"],
              mirror="y", lcsc=p["lcsc"], ref_dxy=(-5.08, -10.16), val_dxy=(-5.08, -7.62))
    gnd(s, *j.pin(2), drop=5.08, R=R)
    s.wire(j.pin(1)[0], y, 66.04, y)
    testpoint(s, 55.88, y, R("TP"), "TP_IN")

    # --- 50 ohm terminator, jumpered --------------------------------------
    r_v(s, 66.04, y + 10.16, R("R"), "51R 1%", left=True)
    s.wire(66.04, y, 66.04, y + 6.35)
    pj = D.P["JMP3"]
    jp = s.sym(pj["lib"], 71.12, y + 22.86, 0, ref=R("JP"), value="50R/PARK",
               footprint=pj["fp"], ref_dxy=(3.81, -3.81), val_dxy=(3.81, 3.81))
    s.wire(66.04, y + 13.97, *jp.pin(1))
    g2 = jp.pin(2)
    s.wire(g2[0], g2[1], 53.34, g2[1])
    gnd(s, 53.34, g2[1], drop=6.35, R=R)
    p3 = jp.pin(3)
    s.wire(p3[0], p3[1], p3[0] - 2.54, p3[1])
    s.label(p3[0] - 2.54, p3[1], "PARK", justify="right bottom")
    s.text(78.74, y + 33.02, "1-2 = 50 ohm terminate (ON except ZED-F9T)", size=1.4, italic=True)
    s.text(78.74, y + 36.83, "2-3 = PARK: source off or unplugged (not 50R)", size=1.4,
           italic=True)
    s.text(78.74, y + 40.64, "neither = a driven, unterminated input", size=1.4, italic=True)

    # --- shunt: current limit + defined DC level ---------------------------
    s.wire(66.04, y, 96.52, y)
    r_h(s, 100.33, y, R("R"), rser)
    s.wire(104.14, y, 116.84, y)
    r_v(s, 116.84, y + 10.16, R("R"), rsh2)
    s.wire(116.84, y, 116.84, y + 6.35)
    gnd(s, 116.84, y + 13.97, drop=6.35, R=R)
    s.text(124.46, y + 12.7, "bounds the current from a", size=1.3, italic=True)
    s.text(124.46, y + 16.51, "high-Z source when the", size=1.3, italic=True)
    s.text(124.46, y + 20.32, "jumper is off, and sets the", size=1.3, italic=True)
    s.text(124.46, y + 24.13, "DC level when nothing", size=1.3, italic=True)
    s.text(124.46, y + 27.94, "is plugged in", size=1.3, italic=True)

    # --- level annotation, right above the node it describes ---------------
    s.note(76.2, y - 26.67, 46.99, 0,
           "AT THE INPUT NODE, before the coupling cap\n%s\n%s\nload %s"
           % (L["at_sma"], L["term_note"], L["load"]), size=1.4, color=LEVEL, cols=38)
    s.arrow(110.49, y - 13.97, 110.49, y - 1.905)

    # --- AC coupling -------------------------------------------------------
    s.wire(116.84, y, 137.16, y)
    c_h(s, 140.97, y, R("C"), "10n C0G")
    s.wire(144.78, y, 160.02, y)
    # under the cap: above it is the input tap's ground symbol since order day
    s.text(135.89, y + 5.08, "AC couple", size=1.4, italic=True)
    # item 19: a U.FL tap through 1k, the resistor at the node -- on the
    # SOURCE side of the 10n (2026-10-10, order day).  It was on the gate
    # side, where the only DC is the replica's 1M: a DC-coupled scope there
    # (50 ohm, or an ADALM2000's 1M) pulled the gate's bias from 1.5 V to
    # 2 mV or 0.75 V and the channel stopped squaring while it was plugged
    # in.  At 10 MHz the 10n is 1.6 ohm, so this side shows the same
    # waveform, and the scope's DC path lands on the 51R and 2k2.
    xi = 128.27
    s.junction(xi, y)
    s.wire(xi, y, xi, y - 5.08)
    r_v(s, xi, y - 8.89, "R%d21" % R.block, "1k", left=True)    # rev B: new parts from 21
    pu = D.P["UFL"]
    # Jx03, not the next number: Jx01 (10 MHz) and Jx02 (pps) keep rev A's names
    tap = s.sym(pu["lib"], xi, y - 15.24, 90, ref="J%d03" % R.block, value="TAP IN",
                footprint=pu["fp"],
                lcsc=pu["lcsc"], ref_dxy=(5.08, -2.54), val_dxy=(5.08, 0.0))
    s.wire(xi, y - 12.7, *tap.pin(1))
    gnd(s, *tap.pin(2), drop=3.81, R=R)

    # --- optional clamp (DNP) ---------------------------------------------
    s.junction(160.02, y)
    pc = D.P["CLAMP"]
    d = s.sym(pc["lib"], 165.10, y + 33.02, 270, ref=R("D"), value="BAV99",
              footprint=pc["fp"], dnp=True, lcsc=pc["lcsc"],
              ref_dxy=(6.35, -1.27), val_dxy=(6.35, 2.54))
    s.wire(160.02, y, *d.pin(3))
    s.wire(d.pin(1)[0], d.pin(1)[1], d.pin(1)[0], d.pin(1)[1] - 3.81)
    s.glabel(d.pin(1)[0], d.pin(1)[1] - 3.81, RAIL_A, shape="input", justify="left")
    gnd(s, *d.pin(2), drop=7.62, R=R)
    s.text(157.48, y + 46.99, "DNP clamp: fit only for an unterminated hot source",
           size=1.3, italic=True)

    # --- squarer ------------------------------------------------------------
    s.wire(160.02, y, 176.53, y)
    r_h(s, 180.34, y, R("R"), "330R")
    pi = D.P["INV2"]
    # names right-justified, ending left of VCC's pin 5 (2026-10-10: the
    # value ran across that pin's number)
    inv = s.sym(pi["lib"], 215.90, y, 0, ref=R("U"), value=pi["val"], footprint=pi["fp"],
                lcsc=pi["lcsc"], ref_dxy=(-8.89, -12.7), val_dxy=(-8.89, -10.16),
                justify="right")
    s.wire(184.15, y, *inv.pin(1))
    gnd(s, *inv.pin(2), drop=6.35, R=R)
    decouple(s, inv.pin(5)[0], inv.pin(5)[1], RAIL_A, R)
    a = inv.pin(1); b = inv.pin(6)
    testpoint(s, 193.04, y, R("TP"), "TP_SQ")
    # PARK (item 11): 100k from the gate to the header's pin 3, its body at the gate
    s.junction(186.69, y)
    s.wire(186.69, y, 186.69, y + 5.08)
    r_v(s, 186.69, y + 8.89, "R%d22" % R.block, "100k", left=True)
    s.wire(186.69, y + 12.7, 186.69, y + 16.51)
    s.label(186.69, y + 16.51, "PARK", justify="right bottom")
    s.note(134.62, y + 60.96, 62.23, 0,
           "WHY THE 74LVC2GU04 (rev B)\n"
           "TWO unbuffered inverters on one die: half 1 squares, half 2 is its replica bias "
           "(item 18).  U = UNBUFFERED, one gain stage: three cascaded stages inside a "
           "feedback loop oscillate, one cannot.\n"
           "LVC = 5.5 V tolerant inputs on a 3.3 V rail, so a 5 V source survives contact, "
           "and no input slew-rate limit: it is meant to run in its linear region.\n"
           "SC-70-6 (DCK): Nexperia's 74AUP2GU04GW fits the same pads (item 8).",
           size=1.4, color=INFO, cols=44)
    s.note(172.72, y - 26.67, 46.99, 0,
           "AT THE GATE, at TP_SQ\n%s\n%s\nslew %s"
           % (L["at_gate"], L["gate_range"], L["slew"]), size=1.4, color=LEVEL, cols=38)
    s.arrow(193.04, y - 13.97, 193.04, y - 7.62)

    # REPLICA BIAS (item 18): half 2's input tied to its own output sits exactly
    # at its threshold, and feeds half 1's input through the 1M
    s.junction(200.66, y)
    s.wire(200.66, y, 200.66, y + 5.08)
    r_v(s, 200.66, y + 8.89, R("R"), "1M 1%", left=True)
    a2 = inv.pin(3); y2 = inv.pin(4)
    s.wires((200.66, y + 12.7), (200.66, y + 16.51), (a2[0], y + 16.51), a2)
    s.label(a2[0] - 2.54, y + 16.51, "REPLICA", justify="right bottom")
    s.wire(y2[0], y2[1], y2[0] + 5.08, y2[1])
    s.label(y2[0] + 5.08, y2[1], "REPLICA", justify="left bottom")
    yfb = y + 27.94
    s.text(220.98, yfb + 6.35, "REPLICA BIAS.  Half 2, its input tied to its output, sits at",
           size=1.4, italic=True)
    s.text(220.98, yfb + 10.16, "its own threshold; the 1M carries that to half 1.  One die, one",
           size=1.4, italic=True)
    s.text(220.98, yfb + 13.97, "supply pin: it decides at its threshold, not 70 mV off (item 18).",
           size=1.4, italic=True)

    # --- sampler + retimer ---------------------------------------------------
    pf = D.P["FF"]
    ff1 = s.sym(pf["lib"], 300.99, y, 0, ref=R("U"), value=pf["val"], footprint=pf["fp"],
                lcsc=pf["lcsc"], ref_dxy=(-8.89, -15.24), val_dxy=(-8.89, -12.7))
    ff2 = s.sym(pf["lib"], 397.51, y, 0, ref=R("U"), value=pf["val"], footprint=pf["fp"],
                lcsc=pf["lcsc"], ref_dxy=(-8.89, -15.24), val_dxy=(-8.89, -12.7))
    for ff in (ff1, ff2):
        gnd(s, *ff.pin(3), drop=7.62, R=R)
        decouple(s, ff.pin(5)[0], ff.pin(5)[1], RAIL_A, R)
    s.note(330.2, y + 62.23, 62.23, 0,
           "WHY THE 74LVC1G80\n"
           "The simplest D flip-flop there is: D, CLK, one output and the two rails, and "
           "nothing else. "
           "No preset and no clear, so there is no asynchronous input that could reset a "
           "sampler which must never be reset, and nothing to tie off.\n"
           "Same 74LVC family and the same SOT-23-5 footprint as the squarer and the Schmitt, "
           "so the whole board is one package type at assembly.",
           size=1.4, color=INFO, cols=44)
    dx, dy = ff1.pin(D.FF_D_PIN)
    s.wires((b[0], y), (dx - 12.7, y), (dx - 12.7, dy), (dx, dy))
    # item 19 (2026-10-10): a U.FL on the SQUARED signal, the edge FF1 samples.
    # The input can be watched for as long as you like through a tee at its
    # SMA; this node could not be watched at all without holding a probe on
    # an SC-70 pin.  1k at the node: /21 into a 50 ohm scope.
    xt = 246.38
    s.junction(xt, y)
    s.wire(xt, y, xt, y - 5.08)
    r_v(s, xt, y - 8.89, "R%d23" % R.block, "1k", left=True)
    tq = s.sym(pu["lib"], xt, y - 15.24, 90, ref="J%d04" % R.block, value="TAP SQ",
               footprint=pu["fp"], lcsc=pu["lcsc"], ref_dxy=(5.08, -2.54),
               val_dxy=(5.08, 0.0))
    s.wire(xt, y - 12.7, *tq.pin(1))
    gnd(s, *tq.pin(2), drop=3.81, R=R)
    qx, qy = ff1.pin(4); d2x, d2y = ff2.pin(D.FF_D_PIN)
    s.wires((qx, qy), (d2x - 12.7, qy), (d2x - 12.7, d2y), (d2x, d2y))
    for ff in (ff1, ff2):
        cx, cy = ff.pin(D.FF_CLK_PIN)
        s.wire(cx - 22.86, cy, cx, cy)
        s.glabel(cx - 22.86, cy, hclk, shape="input", justify="right")
    ox, oy = ff2.pin(4)
    s.wires((ox, oy), (ox + 15.24, oy), (ox + 15.24, y), (ox + 40.64, y))
    testpoint(s, ox + 27.94, y, R("TP"), "TP_BEAT")
    s.glabel(ox + 40.64, y, beat, shape="output")
    s.text(288.29, y + 45.72,
           "into FF1.D:  0/3.3 V CMOS at 10 MHz, edges ~1-2 ns", size=1.5, italic=True)
    s.text(288.29, y + 50.80,
           "out of FF2:  %s, ~%.0f Hz square, 0/3.3 V  -  its EDGE TIME is the measurement"
           % (beat, D.F_BEAT), size=1.5, italic=True)
    s.text(288.29, y + 55.88,
           "%s:  %.4f MHz, 0/3.3 V, this channel's own length-matched branch off the fan-out"
           % (hclk, D.F_HELPER / 1e6), size=1.5, italic=True)


def _ten_mhz_notes(s, L, term):
    t = ''
    y = 204.0
    s.note(15.24, 148.0, 95.0, 0,
           "THE 50R TERM, THE JUMPER SHIPS REMOVED.\n"
           "Fit only if the source drives 50 ohm.  A ZED-F9T is DESTROYED by fitting it: its "
           "TIMEPULSE pin is 5 mA absolute maximum and 3.3 V into 50R asks for 66 mA.\n"
           "Conversely, leaving it out on an 8 Vpp open-circuit source floats the gate input to "
           "about +7.4 V, over the 74LVC1GU04's 6.5 V absolute maximum.  On this channel it "
           "should be %s." % ("FITTED" if term == "IN" else "REMOVED"),
           size=1.4, color=WARN, cols=62)
    s.note(15.24, y, 122.0, 0,
           "THE BAV99 CLAMP IS DNP.\n"
           "Fit only on a channel you will run UNTERMINATED with a source above about 6 Vpp "
           "open circuit.  It is not fitted by default because its reverse leakage flows in "
           "the 1M self-bias resistor: 10 nA is 10 mV of bias shift, leakage roughly doubles "
           "every 10 degC, and at %s that would swamp the whole long-tau drift budget."
           % L["slew"].split(" at ")[0], size=1.4, color=NOTE, cols=80)
    s.note(144.78, y, 122.0, 0,
           "THE SAMPLING FLIP-FLOP (FF1) IS DELIBERATELY ALLOWED TO GO METASTABLE - that is "
           "measurement.  "
           "Never put a synchronizer in front of it.\n"
           "THE RETIMER (FF2) re-clocks on the next helper edge, so what leaves the board is "
           "always a clean transition aligned to a helper edge.  It costs exactly one helper "
           "cycle of latency and destroys no phase information.\n"
           "THE 74LVC1G80 OUTPUT IS INVERTED, so the two stages restore the sense.  Both "
           "datasheets NAME pin 4 'Q' in the pinout drawing and only say otherwise in the "
           "text: TI SCES221T calls it 'Inverted output' and its Table 7-1 gives CLK up, "
           "D = H -> Q = L; Nexperia rev 17 Table 4 agrees.  Pinout confirmed from both: "
           "1 D, 2 CLK, 3 GND, 4 Q(inv), 5 VCC.",
           size=1.4, color=INFO, cols=80)


# ---------------------------------------------------------------------------
def _pps(s, R, pps):
    y = YPP
    s.rect(15.24, 240.0, 564.0, 114.0)
    s.text(19.05, 246.38, "1 pps  CHANNEL      divide  ->  Schmitt  ->  straight to the FPGA",
           size=2.6, bold=True)

    p = D.P["SMA"]
    j = s.sym(p["lib"], 40.64, y, 0, ref=R("J"), value="1pps IN", footprint=p["fp"],
              mirror="y", lcsc=p["lcsc"], ref_dxy=(-5.08, -10.16), val_dxy=(-5.08, -7.62))
    gnd(s, *j.pin(2), drop=5.08, R=R)
    s.wire(j.pin(1)[0], y, 66.04, y)

    r_v(s, 66.04, y + 10.16, R("R"), "51R", dnp=True, left=True)
    s.wire(66.04, y, 66.04, y + 6.35)
    gnd(s, 66.04, y + 13.97, drop=6.35, R=R)
    s.text(53.34, y + 30.48, "DNP: nothing here drives 50 ohm", size=1.3, italic=True)

    s.wire(66.04, y, 96.52, y)
    r_h(s, 100.33, y, R("R"), "1k")
    s.wire(104.14, y, 130.81, y)
    r_v(s, 130.81, y + 10.16, R("R"), "10k")
    s.wire(130.81, y, 130.81, y + 6.35)
    gnd(s, 130.81, y + 13.97, drop=6.35, R=R)
    s.note(58.42, y - 26.67, 43.18, 0,
           "AT THE INPUT\n3.3 V or 5 V pps\nDC coupled, no droop", size=1.4, color=LEVEL, cols=34)
    s.arrow(83.82, y - 13.97, 83.82, y - 1.905)
    s.note(140.97, y - 26.67, 43.18, 0,
           "AFTER THE 1k / 10k\n3.00 V or 4.55 V\nat the Schmitt input", size=1.4, color=LEVEL, cols=34)
    s.arrow(160.02, y - 13.97, 160.02, y - 1.905)
    s.text(143.51, y + 12.7, "1k/10k suits a 3.3 V and a 5 V", size=1.3, italic=True)
    s.text(143.51, y + 16.51, "pps alike, so no channel differs", size=1.3, italic=True)

    ps = D.P["SCHM"]
    sc = s.sym(ps["lib"], 215.90, y, 0, ref=R("U"), value=ps["val"], footprint=ps["fp"],
               lcsc=ps["lcsc"], ref_dxy=(3.81, 12.7), val_dxy=(3.81, 15.24))
    s.wire(130.81, y, *sc.pin(2))
    s.nc(*sc.pin(1))
    gnd(s, *sc.pin(3), drop=6.35, R=R)
    decouple(s, sc.pin(5)[0], sc.pin(5)[1], RAIL_A, R)
    ox, oy = sc.pin(4)
    s.wire(ox, oy, ox + 50.8, oy)
    testpoint(s, ox + 25.4, oy, R("TP"), "TP_PPS")
    s.glabel(ox + 50.8, oy, pps, shape="output")
    s.text(288.29, y + 27.94,
           "out:  %s, one rising edge per second, 0/3.3 V, straight to the RPi header" % pps,
           size=1.5, italic=True)


def _pps_notes(s):
    t = ''
    y = 358.0
    s.note(15.24, y, 122.0, 0,
           "DC-COUPLED, DELIBERATELY.\n"
           "The pps widths in this inventory span 1 us (FE-5680A) to 100 ms (ZED-F9T, "
           "LBE-1421), and no single AC-coupling RC covers five decades: a 10n/100k network "
           "passes the 1 us pulse and droops away to nothing 1% into the 100 ms one.\n"
           "The 1k/10k divider is fitted on EVERY pps channel and suits a 3.3 V and a 5 V "
           "source alike: 3.00 V and 4.55 V at the gate, both comfortably above the Schmitt's "
           "VT+ and below its 5.5 V recommended maximum.  74LVC inputs are 5 V tolerant on a "
           "3.3 V rail, so the divider is there to keep the swing sane rather than merely "
           "survivable -- and to keep every channel identically populated.",
           size=1.4, color=NOTE, cols=80)
    s.note(144.78, y, 122.0, 0,
           "SCHMITT BUFFER, NOT AN INVERTER.\n"
           "Hysteresis is wrong for the 10 MHz path - it moves the trigger off the zero "
           "crossing and turns amplitude into phase - but it is right here: a pps is a rare, "
           "fast, possibly noisy edge on a long cable, which is the chatter case hysteresis "
           "exists for.\n"
           "No self-bias: a Schmitt sets its own thresholds and must not be biased into its "
           "own linear region.\n"
           "Timestamped in the FPGA twice: against the helper counter (100 ns, the same "
           "grid as the beats) and, from gateware v1.1, against the 100 MHz PS clock (10 ns). "
           "The 10 ns one is what tells two channels' 10 MHz phases apart by whole 100 ns "
           "cycles after a power cycle or a dropped edge; the picoseconds come from the beat. "
           "(Rounds 10-27 said '200.02 MHz to 5 ns'; no such clock was ever built.)",
           size=1.4, color=INFO, cols=80)
