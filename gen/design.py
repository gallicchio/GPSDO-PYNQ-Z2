"""
Single source of truth for the GPSDO-PYNQ-Z2 board.

The header pin table here, the schematic, the Vivado constraint file and the BOM
are all generated from this file, so they cannot drift apart.  It mirrors
section 3 of ../README.md; if you change one, change both.
"""

PROJECT = "GPSDO-PYNQ-Z2"
REV     = "A"
DATE    = "2026-09-14"     # printed on the silkscreen beside the revision
COMPANY = "Harvey Mudd College"

# --- the numbers that define the measurement -------------------------------
F_SIGNAL   = 10_000_000.0        # Hz, the references under test
F_HELPER   = 10_001_234.4        # Hz, Si5351 CLK0
F_BEAT     = F_HELPER - F_SIGNAL # 1234.4 Hz
N_GAIN     = F_SIGNAL / F_BEAT   # ~8101, the DDMTD heterodyne gain

# One helper cycle of beat-edge displacement, referred back to the 10 MHz
# input.  The divisor is the HELPER period, not the signal period.  This was
# 1e12/F_SIGNAL/N_GAIN, which is high by f_helper/f_signal = 123 ppm -- small,
# but it is a SCALE error, so it grows with the phase being measured (6 ps at a
# 50 ns reading) and it would never show up as noise.
#
# The identity that settles it: shifting an input by exactly one 10 MHz cycle
# is unobservable, so one whole beat period of displacement must be exactly
# 100 ns of input phase.  A beat period is F_HELPER/F_BEAT = 8102.1 helper
# cycles -- NOT N_GAIN = 8101.1, which is the time-stretch gain and is a
# different quantity that happens to be adjacent.  100 ns / 8102.1 = 12.3425
# ps, which is the same as T_helper/N_GAIN.
#
# It also makes the schematic's own sentence true: 12.3425 ps x N_GAIN is
# 99.988 ns, exactly one helper period, which is what "a full helper period at
# the FPGA" means.  The old value gave 100.0 ns, which is not a helper period.
T_RES_PS   = 1e12 / F_HELPER / N_GAIN   # ~12.34 ps single-shot

# --- RPi 40-pin header -----------------------------------------------------
# pin : (net, zynq_pin, site, use)
HEADER = {
 1:("+3V3_HOST", "",   "3V3",  "NOT CONNECTED - we make our own 3.3 V"),
 2:("+5V_HDR",   "",   "5V",   "board power in"),
 3:("I2C_SDA",   "W18","IO_L22P_T3_34","I2C SDA - 2k2 pull-up already on PYNQ-Z2"),
 4:("+5V_HDR",   "",   "5V",   "board power in"),
 5:("I2C_SCL",   "W19","IO_L22N_T3_34","I2C SCL - 2k2 pull-up already on PYNQ-Z2"),
 6:("GND","","GND",""),
 7:("BEAT_00","Y18","IO_L17P_T2_34","unit 1 beat"),
 8:("PPS_00","V6","IO_L22P_T3_13","unit 1 pps"),
 9:("GND","","GND",""),
10:("PPS_01","Y6","IO_L13N_T2_MRCC_13","unit 2 pps"),
11:("BEAT_01","U7","IO_L11P_T1_SRCC_13","unit 2 beat"),
12:("PPS_02","C20","IO_L1P_T0_AD0P_35","unit 3 pps"),
13:("BEAT_02","V7","IO_L11N_T1_SRCC_13","unit 3 beat - rpio_27, ABSENT from the stock XDC"),
14:("GND","","GND",""),
15:("BEAT_03","U8","IO_L17N_T2_13","unit 4 beat"),
16:("PPS_03","W6","IO_L22N_T3_13","unit 4 pps"),
17:("+3V3_HOST","","3V3","NOT CONNECTED"),
18:("HELPER_CLK","Y7","IO_L13P_T2_MRCC_13","HELPER CLOCK -> FPGA (MRCC P, bank 13)"),
19:("BEAT_04","V8","IO_L15P_T2_DQS_13","unit 5 beat"),
20:("GND","","GND",""),
21:("BEAT_05","V10","IO_L21N_T3_DQS_13","unit 6 beat"),
22:("PPS_04","F20","IO_L15N_T2_DQS_AD12N_35","unit 5 pps"),
23:("BEAT_06","W10","IO_L16P_T2_13","unit 7 beat"),
24:("PPS_05","F19","IO_L15P_T2_DQS_AD12P_35","unit 6 pps"),
25:("GND","","GND",""),
26:("PPS_06","U19","IO_L12N_T1_MRCC_34","unit 7 pps"),
27:("BEAT_07","Y16","IO_L7P_T1_34","unit 8 beat - 2k2 pull-up on PYNQ-Z2"),
28:("PPS_07","Y17","IO_L7N_T1_34","unit 8 pps - 2k2 pull-up on PYNQ-Z2"),
29:("BEAT_08","Y19","IO_L17N_T2_34","unit 9 beat"),
30:("GND","","GND",""),
31:("BEAT_09","U18","IO_L12P_T1_MRCC_34","unit 10 beat"),   # U18 is the other MRCC ball on the header: the fallback helper input for a future revision, nothing is fitted for it
32:("PPS_08","B20","IO_L1N_T0_AD0N_35","unit 9 pps"),
33:("BEAT_10","W8","IO_L15N_T2_DQS_13","unit 11 beat"),
34:("GND","","GND",""),
35:("BEAT_11","Y8","IO_L14N_T2_SRCC_13","unit 12 beat"),
36:("PPS_09","B19","IO_L2P_T0_AD8P_35","unit 10 pps"),
37:("BEAT_12","W9","IO_L16N_T2_13","unit 13 beat = NULL channel"),
38:("PPS_10","A20","IO_L2N_T0_AD8N_35","unit 11 pps"),
39:("GND","","GND",""),
40:("PPS_11","Y9","IO_L14P_T2_SRCC_13","unit 12 pps"),
}


# ---------------------------------------------------------------------------
# Which channel lands on which header pin is a LAYOUT decision, so it is made
# from the layout rather than typed here.  The pin SETS are fixed by the PYNQ:
# ground, power, I2C and pin 18 are where they are, and the schematic's own
# argument keeps every BEAT on the odd row and every PPS on the even row.  All
# that is free is which unit gets which of the remaining pins -- and choosing
# them left-to-right in the same order the tiles sit on the board turns a
# ratsnest full of crossings into thirteen straight runs.
# ---------------------------------------------------------------------------
def _reorder_header():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "pcb"))
    try:
        import geom as _G
    except Exception:
        return                      # layout not available; leave as authored
    # geom.units_by_x() carries the whole argument, including round 19's
    # correction to the order WITHIN each bundle.  Nothing here touches pin 18,
    # and nothing may: it is HELPER_CLK, and it is the one header pin that is a
    # real clock input on BOTH the PYNQ-Z2 (Y7, IO_L13P_T2_MRCC_13) and the
    # Icepi Zero (L1, PCLKT6_1).  See section 13 of the write-up.
    order = _G.units_by_x()
    beat_pins = sorted((p for p, v in HEADER.items() if v[0].startswith("BEAT")),
                       reverse=True)     # descending pin no = left to right
    pps_pins = sorted((p for p, v in HEADER.items() if v[0].startswith("PPS")),
                      reverse=True)
    for pins, pre, units in ((beat_pins, "BEAT", order),
                             (pps_pins, "PPS", [u for u in order if u != 13])):
        assert len(pins) == len(units), (pre, len(pins), len(units))
        for pin, u in zip(pins, units):
            net, zynq, site, _ = HEADER[pin]
            HEADER[pin] = ("%s_%02d" % (pre, u - 1), zynq, site,
                           "unit %d %s" % (u, "beat" if pre == "BEAT" else "pps"))


_reorder_header()
# ---------------------------------------------------------------------------
# Which pin of the 74LVC1G80 is D and which is the clock.  ROUND 22: SETTLED,
# from the manufacturers, and the answer is that this was already right.
#
#   TI SCES221T (SN74LVC1G80), Figure 4-3, DBV 5-pin SOT-23 top view, and its
#   Pin Functions table:        1 D,  2 CLK,  3 GND,  4 Q,  5 VCC
#   Nexperia 74LVC1G80 rev 17, SOT753 (SC-74A) and SOT353-1:
#                               1 D,  2 CP,   3 GND,  4 Q,  5 VCC
#
# Two manufacturers, same pinout, and it matches the stock KiCad symbol.  My
# round-22 worry came from generalising the wrong way: the SN74LVC1G175
# (SOT-23-6) and SN74LVC2G74 (8-pin) both put the clock on pin 1, but the
# single-gate SOT-23-5 flip-flops do not follow those parts -- they put D
# first.  Do not re-derive this from a sibling's pin order; it does not hold.
#
# THE OUTPUT IS INVERTED, and this is a genuine trap: BOTH datasheets NAME pin
# 4 "Q" in the pinout drawings, and only the text says otherwise.  TI's Pin
# Functions table calls it "Inverted output" and its Table 7-1 reads CLK up
# with D = H giving Q = L; Nexperia's Table 4 says the same.  So the KiCad
# symbol's "~{Q}" is more honest than the datasheets' own artwork, and the two
# flip-flops in cascade per channel restore the sense -- see round 21.13.3,
# which also shows the cascade would survive being wrong about this.
#
# Kept as a named pair anyway: it cost nothing, it documents what was checked,
# and it is the right shape if a second source ever differs.
FF_D_PIN, FF_CLK_PIN = 1, 2

assert HEADER[18][0] == "HELPER_CLK", \
    "pin 18 is the only header pin that is a clock input on both the PYNQ-Z2 " \
    "and the Icepi Zero; nothing may reassign it"

# --- the 13 channel tiles ---------------------------------------------------
# Every unit is identical except for its names and its per-channel population.
# term:  'IN'  -> fit the 50 ohm terminator jumper (source drives 50 ohm)
#        'OUT' -> remove it (high-Z source; the ZED-F9T is DESTROYED by 'IN')
# pad:   (Rser, Rsh2) population, '0R'/'DNP' by default
UNITS = [
 # n, name,               source that channel is meant for, term, Rser, Rsh2, note
 ( 1,"BEAT_00","PPS_00","Spectrum Instruments TM-4",  "IN", "0R", "2k2",
   "8.0 Vpp OPEN CIRCUIT - the hottest source here.  The 50R TERM jumper MUST be fitted on "
   "this channel: unterminated it floats the gate to about +7.4 V, over the 6.5 V absolute "
   "maximum."),
 ( 2,"BEAT_01","PPS_01","ZED-F9T #1",                "OUT","0R", "2k2",
   "NEVER fit the 50R TERM jumper: TIMEPULSE is 5 mA abs max and 3.3 V into 50R asks for "
   "66 mA.  Unterminated the load is R_SH alone, 2k2, drawing 1.5 mA."),
 ( 3,"BEAT_02","PPS_02","ZED-F9T #2",                "OUT","0R", "2k2",
   "NEVER fit the 50R TERM jumper - see unit 2"),
 ( 4,"BEAT_03","PPS_03","Leo Bodnar LBE-1421 #1",    "IN", "0R", "2k2",""),
 ( 5,"BEAT_04","PPS_04","Leo Bodnar LBE-1421 #2",    "IN", "0R", "2k2",""),
 ( 6,"BEAT_05","PPS_05","LB Precision GPS Ref 2021", "IN", "0R", "2k2",""),
 ( 7,"BEAT_06","PPS_06","LB Mini Precision",         "IN", "0R", "2k2",""),
 ( 8,"BEAT_07","PPS_07","BG7TBL GPSDO green 2019",   "IN", "0R", "2k2",""),
 ( 9,"BEAT_08","PPS_08","TM4313",                    "IN", "0R", "2k2",""),
 (10,"BEAT_09","PPS_09","ZYT GPSDO (Samsung UCCM)",  "IN", "0R", "2k2",""),
 (11,"BEAT_10","PPS_10","TF-GNSSDO-10 IRIG-B",       "IN", "0R", "2k2",""),
 (12,"BEAT_11","PPS_11","HP 10811B / FE-5680A Rb",   "IN", "0R", "2k2",
   "FE-5680A is the weakest source at 0.72 Vpp into 50R: never pad this one"),
 (13,"BEAT_12",None,    "NULL CHANNEL",              "IN", "0R", "2k2",
   "Instrument-only null.  No pps.  Round 25: this used to say the source was "
   "'selected by JP_NULL - see the helper sheet'.  There is no JP_NULL, on the "
   "helper sheet or anywhere else -- unit 13 is an ordinary channel with its "
   "own SMA (J1301).  You make it a null by CABLING J3001, the CLK1 OUT jack, "
   "into J1301.  Round 28: CLK1 is PLLB in INTEGER mode (25 MHz x 32 / 80 = "
   "10.000000 MHz) and the helper is PLLA; both lock to the one TCXO, so the "
   "beat is exactly F_BEAT, but they are two PLLs, so what this channel reads "
   "is the front end plus the PLLs' uncorrelated noise -- an UPPER BOUND on "
   "the instrument floor, not a noiseless one.  (CLK1 off PLLA would need "
   "MultiSynth 80.0099, the fractional mode the helper was steered away from.)"),
]

# --- parts ------------------------------------------------------------------
P = dict(
  INV   = dict(lib="74xGxx:74LVC1GU04", val="74LVC1GU04", lcsc="C81934",
               fp="Package_TO_SOT_SMD:SOT-23-5"),
  FF    = dict(lib="74xGxx:74LVC1G80",  val="74LVC1G80",  lcsc="C42879",
               fp="Package_TO_SOT_SMD:SOT-23-5"),
  SCHM  = dict(lib="74xGxx:74LVC1G17",  val="74LVC1G17",  lcsc="C7836",
               fp="Package_TO_SOT_SMD:SOT-23-5"),
  BUF   = dict(lib="74xGxx:74LVC1G34",  val="74LVC1G34",  lcsc="C840096",
               fp="Package_TO_SOT_SMD:SOT-23-5"),
  SMA   = dict(lib="Connector:Conn_Coaxial", val="SMA jack", lcsc="C496549",
               fp="GPSDO-PYNQ-Z2:SMA_Vertical_THT_Universal"),
  R0805 = dict(lib="Device:R", fp="Resistor_SMD:R_0805_2012Metric"),
  C0805 = dict(lib="Device:C", fp="Capacitor_SMD:C_0805_2012Metric"),
  FB    = dict(lib="Device:FerriteBead", val="600R@100MHz", lcsc="C85837",
               fp="Inductor_SMD:L_0805_2012Metric"),
  JMP2  = dict(lib="Connector_Generic:Conn_01x02", val="jumper",
               fp="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"),
  CLAMP = dict(lib="Diode:BAV99", val="BAV99", lcsc="C916421",
               fp="Package_TO_SOT_SMD:SOT-23"),
  TP    = dict(lib="Connector:TestPoint", val="TP",
               fp="TestPoint:TestPoint_Pad_D1.5mm"),
)


# --- what each channel's source actually delivers ---------------------------
# From the inventory table at the top of GPSDO-comparison/README.md.  Used to
# print the expected Vpp and center voltage at each stage of the front end on
# that unit's own schematic page, since every unit has its own page anyway.
#   shape:  'sine' = zero-centered;  'cmos' = 0 to V, so centered at V/2
#   vpp_open / vpp_50: README's "V Pk-Pk Open" and "V Pk-Pk into 50 Ohm"
SOURCES = {
  1: ("sine", 8.00, 2.00),   # Spectrum Instruments TM-4
  2: ("cmos", 3.30, None),   # ZED-F9T  - never terminate
  3: ("cmos", 3.30, None),   # ZED-F9T  - never terminate
  4: ("cmos", 3.30, 1.64),   # Leo Bodnar LBE-1421
  5: ("cmos", 3.30, 1.64),   # Leo Bodnar LBE-1421
  6: ("cmos", 3.30, 2.30),   # LB Precision GPS Reference Clock 2021
  7: ("cmos", 3.30, 1.20),   # LB Mini Precision
  8: ("sine", 4.20, 2.60),   # BG7TBL GPSDO green 2019
  9: ("sine", 4.00, 2.00),   # TM4313
 10: ("sine", 3.30, 1.50),   # ZYT GPSDO (Samsung UCCM-LPK)
 11: ("sine", 4.30, 2.20),   # TF-GNSSDO-10 IRIG-B
 12: ("sine", 2.80, 1.56),   # HP 10811B  (FE-5680A on this channel: 0.95 / 0.72)
 13: ("cmos", 3.30, 1.65),   # NULL: Si5351 CLK1 at exactly 10.000000 MHz
}

# --- what may be applied to a 10 MHz SMA ------------------------------------
# Round 29: the silkscreen and the handbook both print these, and before this
# round they were typed into the silkscreen as "0.7 - 8.0" with no derivation.
#
# The WEAKEST thing this board is asked to square is the FE-5680A rubidium on
# channel 12, 0.72 Vpp into 50 ohm.  It is not in SOURCES because SOURCES holds
# the part that is normally on each channel and channel 12 normally carries the
# HP 10811B; the FE-5680A is the alternative named in UNITS[11]'s note, and it
# is the number that sets the low end of the printed range.
#
# The HOTTEST is the TM-4 on channel 1, 8.0 Vpp open circuit, and it is only
# safe because that channel's 50R TERM jumper is fitted -- which is why the
# silkscreen prints the jumper and the voltage in the same breath.  Without a
# jumper the ceiling is a CMOS source's own rail: nothing in the inventory that
# is meant to run unterminated exceeds 3.3 Vpp, and above that the coupling
# capacitor rectifies through the gate's ESD diode and walks the input up.
V_SMA_MIN = 0.72
V_SMA_MAX = max(v for _s, v, _v50 in SOURCES.values())
V_SMA_MAX_OPEN = max(SOURCES[n][1] for n, _b, _p, _s, term, _r, _r2, _nt in UNITS
                     if term == "OUT")
assert V_SMA_MAX == 8.0 and V_SMA_MAX_OPEN == 3.3, (V_SMA_MAX, V_SMA_MAX_OPEN)

VTH = 1.65        # self-biased 74LVC1GU04 switching threshold on a 3.3 V rail
F   = 10.0e6      # Hz


def levels(unit_n, term, rser, rsh2):
    """
    Expected levels through one 10 MHz front end, for annotation on the page.

    Every channel is populated identically -- R_S is a 0R link and R_SH is 2k2 on
    all thirteen -- so the only thing that differs between units is whether the
    50R TERM jumper is pushed on.  R_SH is there to bound the current drawn from
    a high-impedance CMOS source when the jumper is out (3.3 V into 2k2 = 1.5 mA,
    against the ZED-F9T's 4 mA characterised point) and to give the input a
    defined DC level with nothing plugged in.  Against a 50 ohm source with the
    jumper in it is 51 || 2k2 = 49.8 ohm, a 0.6 % effect.
    """
    import math
    shape, vopen, v50 = SOURCES[unit_n]
    v_sma = v50 if (term == "IN" and v50 is not None) else vopen
    v_in = v_sma                       # no divider: R_S is a link on every channel
    c_in = 0.0 if shape == "sine" else v_in / 2.0
    if shape == "sine":
        slew = 2 * math.pi * F * (v_in / 2.0) * 1e-9 * 1000.0
        slew_s = "%.0f mV/ns" % slew
    else:
        slew_s = "~%.0f mV/ns" % (v_in / 2.0e-9 / 1e6)
    return dict(
        shape=shape, v_sma=v_sma, v_in=v_in, c_in=c_in,
        at_sma="%.2f Vpp, center %s" % (v_sma, "0 V" if shape == "sine" else "%.2f V" % (v_sma / 2)),
        at_gate="%.2f Vpp, center %.2f V" % (v_in, VTH),
        gate_range="%.2f to %.2f V" % (VTH - v_in / 2, VTH + v_in / 2),
        slew=slew_s,
        load=("51R || 2k2 = 49.8 ohm" if term == "IN" else
              "2k2 only (%.1f mA peak)" % (v_sma / 2.2)),
        term_note=("TERMINATED" if term == "IN" else "UNTERMINATED"),
        headroom_ok=(VTH - v_in / 2 > -0.4 and VTH + v_in / 2 < 3.7),
    )
