"""Every word this board prints on itself, in one file.

Round 29.  The silkscreen strings used to be literals scattered through
pcb/build_pcb.py, and the handbook did not exist, so the only way to know what
the board said was to read the board.  Three of them had gone stale -- the
bottom legend still explained an `n`/`Pn` notation that nothing prints, the
test-point key called the input `I` in a font where `I` and `1` are the same
glyph, and a warning ran off the edge of the board.

So: the words live here, the handbook and the board both read them from here,
and the numbers in them are computed from gen/design.py rather than typed.

The board's silkscreen is stroke text in KiCad's newstroke font.  Two rules
that come out of that and are worth knowing before adding a line:

  * there is no `Ohm` glyph anyone should rely on being plotted, so this board
    writes ohms the way its own schematic does: `50R`, `2k2`, `560R`, and
    `ohm` spelled out where a word reads better.
  * `I`, `l` and `1` are very nearly the same three strokes.  Single-letter
    keys avoid all three; `TP_IN`'s key is `In`, which round 28 had as `I`.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "gen"))
import design as D                                        # noqa: E402


# ---------------------------------------------------------------------------
# test points
# ---------------------------------------------------------------------------
# value on the schematic -> the key printed beside the pad.  `In` is two
# characters on purpose; everything else is one.
TP_LETTER = {"TP_IN": "In", "TP_SQ": "S", "TP_BEAT": "B", "TP_PPS": "P",
             "TP_5V": "5", "TP_3V3_A": "A", "TP_3V3_D": "D",
             "TP_XA": "X", "TP_1W": "W"}

# (key, schematic value, where it is, what you should see)
TEST_POINTS = [
    ("In", "TP_IN",    "10 MHz box, beside the SMA",
     "the input as it arrives: %.1f-%.1f Vpp AC, 10 MHz"
     % (D.V_SMA_MIN, D.V_SMA_MAX)),
    ("S",  "TP_SQ",    "10 MHz box, at the squarer's input",
     "AC coupled about %.2f V; 0.6-3.3 Vpp.  This is the node whose slew rate "
     "sets the channel's noise floor" % D.VTH),
    ("B",  "TP_BEAT",  "10 MHz box, at the far end",
     "0/3.3 V square at the beat frequency, %.1f Hz" % D.F_BEAT),
    ("P",  "TP_PPS",   "1 pps box",
     "0/3.3 V, one rising edge a second"),
    ("5",  "TP_5V",    "power block, by the 5 V fuse",
     "4.6-5.3 V"),
    ("A",  "TP_3V3_A", "power block, at the analog LDO",
     "3.25-3.35 V.  Absent, by design, when the host is off"),
    ("D",  "TP_3V3_D", "power block, at the digital LDO",
     "3.25-3.35 V.  Absent, by design, when the host is off"),
    ("X",  "TP_XA",    "helper block, at the Si5351's crystal",
     "0.5-1.0 Vpp, 25 MHz.  Probe this one with a 10x probe or not at all"),
    ("W",  "TP_1W",    "1-Wire block, on the bus",
     "the DS18B20 bus: idle high at 3.3 V, with the conversion traffic on it"),
]

# The bottom-of-board key, as two columns of short lines.
def legend_columns():
    return (["In  10 MHz at the SMA  %.1f-%.1f Vpp" % (D.V_SMA_MIN, D.V_SMA_MAX),
             "S  squarer  0.6-3.3 Vpp",
             "B  beat  0/3.3 V, %.1f-%.1f kHz"
             % (D.F_BEAT * 0.9e-3, D.F_BEAT * 1.15e-3),
             "5  +5 V  4.6-5.3 V"],
            ["P  pps  0/3.3 V, 1 Hz",
             "X  Si5351 XA  0.5-1.0 Vpp",
             "W  1-Wire bus",
             "A/D  +3V3  3.25-3.35 V"])


# The two lines under the key that explain the JACK names, not the test
# points.  Round 28 printed "n = 10 MHz IN ...  Pn = 1 pps IN ...", which
# invited you to look for a jack called `n`.  The jacks are called 1..13 and
# P1..P12, so say that.
def jack_key():
    return ["1-%d = 10 MHz IN   P1-P%d = 1 pps IN   %d = NULL (cable HO in)"
            % (D.UNITS[-1][0], D.UNITS[-2][0], D.UNITS[-1][0])]


def helper_key():
    """What the two helper jacks are, printed BESIDE the two helper jacks.

    Round 28 had this in the bottom-right legend, 150 mm from the jacks it
    describes, because that was where there was room.  There is room next to
    them, in the top band east of the centre line.
    """
    return ["HIN = ext helper IN, %.1f-3.3 Vpp AC" % D.V_SMA_MIN,
            "HO = CLK1 OUT, 0/3.3 V into 50R"]


# ---------------------------------------------------------------------------
# column headings, above each column of jacks
# ---------------------------------------------------------------------------
# Each returns (heading, sub-heading).  The heading is deliberately bigger
# than the 2.4 mm jack numbers under it: it is the line that stops someone
# putting 8 Vpp into an unterminated ZED-F9T channel, and a column of jacks is
# 25 to 49 mm wide, which is what sets how long the sub-heading may be.
def col_head_pps():
    return ("1 pps IN", "0 to 5.5 V DC")


def col_head_10m():
    """What may be applied to a 10 MHz SMA, from design.SOURCES.

    `50R` rather than the omega glyph: see the module docstring.  `w/ JP` is
    the two-pin jumper each channel carries; whether it is fitted is the one
    thing that differs between the thirteen, and TERM_NOTE says which.
    """
    return ("10 MHz IN",
            "AC coupled   50R w/ jumper   %.0f Vpp max" % D.V_SMA_MAX)


# ---------------------------------------------------------------------------
# region labels
# ---------------------------------------------------------------------------
# Drawn INSIDE each region's own silkscreen box, at its top.  Multi-line
# where a region is narrow: the helper band is 36 mm across and "HELPER Clock
# Distribution" on one line is 44.
REGION = {
    # Two lines, not three.  The helper band is 28 mm of clear width in the
    # only rows it has -- between the two SMAs' pads and U5007's decoupling
    # stack -- and "Distribution" alone is 13 of them, so a third line has to
    # go 16 mm further down the board and stops reading as part of the title.
    "helper": ["HELPER", "Clock Distribution"],
    "power":  ["POWER"],
    "house":  ["HOUSEKEEPING"],
}

# The 1-Wire terminals get one line rather than a region label plus a legend:
# there are exactly 2 mm of clear board between the series resistors and the
# DS2482, and the wire colours are the part you actually need in your hand.
# ("standard speed, no 4k7 pull-up needed" moved to the handbook, which is
# where a fact you read once belongs.)
PROBE_HEADING = ("1-WIRE external THERMOMETERS     "
                 "yel = DATA   red = VCC   blk = GND")


def PROBE_TAG(i):
    """The screw terminals are W1..W5, not P1..P5.

    Round 29.  They were P1..P5, and the 1 pps jacks are P1..P12, so two
    different connectors thirteen rows apart carried the same five names.
    `W` is the key this board already prints on the 1-Wire test point.
    """
    return "W%d" % i


# ---------------------------------------------------------------------------
# the warnings
# ---------------------------------------------------------------------------
# Round 29.  The old single line was 88 characters at 1 mm and ran off the
# right-hand edge of the board (DRC: silk_edge_clearance).  It is now three
# short lines that fit in the strip between the posts and the edge, and it
# says what the board normally does before it says what not to do.
# Two lines, not three: the only clear board near the posts is a 3 mm strip
# along the top edge, and the two helper SMAs' own labels break it in the
# middle, so there are exactly two full-width rows to be had.
# Two lines in the 3 mm strip along the top edge directly above the posts,
# which is the only clear board next to them: everything below is the power
# block and the strip west of it is broken in the middle by the two helper
# SMAs' own labels.
BENCH_LINES = [
    "BENCH 5 V IN - NORMALLY LEAVE OPEN.  The board is powered from the "
    "PYNQ header.",
    "Do *not* power the board here unless PYNQ is either disconnected or on!",
]

# On the PYNQ's own supply.  Round 28 printed "PYNQ: USE THE BARREL JACK,
# J9 = REG", which reads as an instruction about THIS board's jack.
PYNQ_POWER_LINE = "Power the PYNQ with its barrel jack, J9.  Not (only) through USB."

# These belong to the 15 V barrel jack and were printed 12 mm from the BENCH
# posts, where they read as a warning about the 5 V input.
BARREL_LINES = ["15 V DC, 1 A MIN", "HEATER ONLY, CENTRE +"]

TERM_NOTE = """\
Every channel is populated identically -- `R_S` is a 0R link and `R_SH` is 2k2 --
so the only thing that differs between channels is whether the **50R TERM
jumper** is pushed onto its two pins.  Fitting it on a channel that should not
have it is the only way to damage a source from this board:

* **Units 2 and 3 (ZED-F9T): NEVER fit the jumper.**  TIMEPULSE is 5 mA
  absolute maximum and 3.3 V into 50R asks for 66 mA.  Unterminated, the load
  is `R_SH` alone: 1.5 mA.
* **Unit 1 (TM-4): the jumper MUST be fitted.**  Unterminated, its 8 Vpp
  open-circuit output floats the squarer's input above the gate's 6.5 V
  absolute maximum.
* Everything else drives 50R happily and wants the jumper in."""


# ---------------------------------------------------------------------------
# section 2 of the handbook: a bare Si5351 breakout on the PYNQ's own header
# ---------------------------------------------------------------------------
# Keyed by the net the finished board puts on that pin, so if the header map
# ever moves, the wiring list moves with it.
SI5351_WIRING = {
    "+3V3_HOST": "VIN / VDD on the module.  3.3 V, NOT 5 V",
    "GND":       "GND",
    "I2C_SDA":   "SDA   (the PYNQ already has the 2k2 pull-up)",
    "I2C_SCL":   "SCL   (the PYNQ already has the 2k2 pull-up)",
    "HELPER_CLK": "CLK0  -- the helper output, and the only MRCC ball here",
}
