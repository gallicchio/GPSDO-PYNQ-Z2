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
from blocks import RefGen, gnd, rail, r_h, r_v, c_h, c_v, testpoint, decouple

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
               "    the CLK1 OUT jack on the Helper sheet  -  Si5351 CLK1 at exactly "
               "10.000000 MHz.  CLK1 and the helper CLK0 come off the same PLL, so their beat "
               "is exact and noiseless and anything this channel reports is this board and "
               "nothing else.  This is the instrument floor.\n"
               "    a splitter off one real GPSDO  -  instrument plus one real front end\n\n"
               "There is no jumper: a patch lead keeps every channel tile identical and puts a "
               "real connector and cable in the loop, which is the honest thing to measure.",
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
    pj = D.P["JMP2"]
    jp = s.sym(pj["lib"], 71.12, y + 20.32, 0, ref=R("JP"), value="50R TERM",
               footprint=pj["fp"], ref_dxy=(3.81, -1.27), val_dxy=(3.81, 1.27))
    s.wire(66.04, y + 13.97, *jp.pin(1))
    gnd(s, *jp.pin(2), drop=8.89, R=R)
    s.text(78.74, y + 26.67, "50 ohm terminate.", size=1.4, italic=True)
    s.text(78.74, y + 30.48, "Jumper ON except ZED-F9T.", size=1.4, italic=True)

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
    s.text(132.08, y - 6.35, "AC couple", size=1.4, italic=True)

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
    pi = D.P["INV"]
    inv = s.sym(pi["lib"], 215.90, y, 0, ref=R("U"), value=pi["val"], footprint=pi["fp"],
                lcsc=pi["lcsc"], ref_dxy=(3.81, 12.7), val_dxy=(3.81, 15.24))
    s.wire(184.15, y, *inv.pin(2))
    s.nc(*inv.pin(1))
    gnd(s, *inv.pin(3), drop=6.35, R=R)
    decouple(s, inv.pin(5)[0], inv.pin(5)[1], RAIL_A, R)
    a = inv.pin(2); b = inv.pin(4)
    testpoint(s, 193.04, y, R("TP"), "TP_SQ")
    s.note(134.62, y + 60.96, 62.23, 0,
           "WHY THE 74LVC1GU04\n"
           "U = UNBUFFERED, one gain stage.  A buffered inverter is three cascaded stages, and "
           "three poles inside a feedback loop oscillate; one pole cannot.  That is what makes "
           "the 1M self-bias safe here.\n"
           "LVC = 5.5 V tolerant inputs on a 3.3 V rail (there is no clamp diode to Vcc), so a "
           "5 V source survives contact.\n"
           "It also has no input slew-rate limit in its Recommended Operating Conditions - "
           "unlike the buffered G04 - because it is meant to be run in its linear region.",
           size=1.4, color=INFO, cols=44)
    s.note(172.72, y - 26.67, 46.99, 0,
           "AT THE GATE, at TP_SQ\n%s\n%s\nslew %s"
           % (L["at_gate"], L["gate_range"], L["slew"]), size=1.4, color=LEVEL, cols=38)
    s.arrow(193.04, y - 13.97, 193.04, y - 7.62)

    # 1M self-bias, tucked just under the gate's own ground symbol
    yfb = y + 27.94
    s.wires((a[0], y), (a[0], yfb), (207.01, yfb))
    r_h(s, 210.82, yfb, R("R"), "1M 1%", below=True)
    s.wires((214.63, yfb), (b[0], yfb), (b[0], y))
    s.text(220.98, yfb + 6.35, "SELF BIAS.  The 1M parks the gate's input at its own switching",
           size=1.4, italic=True)
    s.text(220.98, yfb + 10.16, "threshold, so the decision point tracks this gate's own supply",
           size=1.4, italic=True)
    s.text(220.98, yfb + 13.97, "and temperature instead of a fixed divider.", size=1.4, italic=True)

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
           "The simplest D flip-flop there is: D, CLK, ~Q and the two rails, and nothing else. "
           "No preset and no clear, so there is no asynchronous input that could reset a "
           "sampler which must never be reset, and nothing to tie off.\n"
           "Same 74LVC family and the same SOT-23-5 footprint as the squarer and the Schmitt, "
           "so the whole board is one package type at assembly.",
           size=1.4, color=INFO, cols=44)
    dx, dy = ff1.pin(1)
    s.wires((b[0], y), (dx - 12.7, y), (dx - 12.7, dy), (dx, dy))
    qx, qy = ff1.pin(4); d2x, d2y = ff2.pin(1)
    s.wires((qx, qy), (d2x - 12.7, qy), (d2x - 12.7, d2y), (d2x, d2y))
    for ff in (ff1, ff2):
        cx, cy = ff.pin(2)
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
           "The 74LVC1G80 output is ~Q, so two stages restore the sense.",
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
           "Timed in the FPGA's 200.02 MHz domain to 5 ns, far below every GPSDO's own "
           "sawtooth.", size=1.4, color=INFO, cols=80)
