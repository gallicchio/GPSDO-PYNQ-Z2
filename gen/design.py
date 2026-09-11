"""
Single source of truth for the GPSDO-PYNQ-Z2 board.

The header pin table here, the schematic, the Vivado constraint file and the BOM
are all generated from this file, so they cannot drift apart.  It mirrors
section 3 of GPSDO-comparison/GPSDO-DMTD-PCB.md; if you change one, change both.
"""

PROJECT = "GPSDO-PYNQ-Z2"
REV     = "A"
COMPANY = "Harvey Mudd College"

# --- the numbers that define the measurement -------------------------------
F_SIGNAL   = 10_000_000.0        # Hz, the references under test
F_HELPER   = 10_001_234.4        # Hz, Si5351 CLK0
F_BEAT     = F_HELPER - F_SIGNAL # 1234.4 Hz
N_GAIN     = F_SIGNAL / F_BEAT   # ~8101, the DDMTD heterodyne gain
T_RES_PS   = 1e12 / F_SIGNAL / N_GAIN   # ~12.3 ps single-shot

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
31:("BEAT_09","U18","IO_L12P_T1_MRCC_34","unit 10 beat - DNP 0R alternate helper input"),
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
    order = _G.units_by_x()          # e.g. [1, 8, 2, 9, 3, ...] left to right
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
   "Instrument-only null. No pps. Source selected by JP_NULL - see the helper sheet"),
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
