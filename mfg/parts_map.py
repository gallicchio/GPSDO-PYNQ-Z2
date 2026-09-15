#!/usr/bin/env python3
"""LCSC part numbers for everything the schematic does not already name.

Chosen with mfg/pick_parts.py and reviewed by hand.  The rule used throughout
was: take a BASIC part unless there is a reason not to, because JLCPCB charges
a per-DISTINCT-PART setup fee (about $3) for every Extended part and nothing
for a Basic one.  All the resistors come from one Basic series, 0805W8F...T5E,
±1% 125 mW thick film, which keeps them on the machine's standard feeders.

Keyed by the schematic Value string plus the footprint's short name, because
that pair is what distinguishes "47R 0805" from "47R 1206".
"""

# value, footprint-short-name  ->  (LCSC, why this one)
MAP = {
    # ---- capacitors ----------------------------------------------------
    ("100n", "C_0805_2012Metric"):
        ("C49678", "Basic, 50V X7R +/-10%, 18.7M in stock; the standard part"),
    ("10n", "C_0805_2012Metric"):
        ("C1710", "Basic, Samsung CL21B103KBANNNC, 50V X7R +/-10%, 2.8M in "
                  "stock.  My first pass claimed there was no Basic 10n 0805 "
                  "and picked an Extended part -- that was a bad search "
                  "keyword, not a fact about the catalogue"),
    ("10n C0G", "C_0805_2012Metric"):
        ("C237168", "50V NP0/C0G +/-5%.  C0G is deliberate: this is the "
                    "front-end AC coupling, and a C0G dielectric has no "
                    "voltage coefficient and no dielectric absorption to "
                    "modulate the zero crossing"),
    ("10u", "C_0805_2012Metric"):
        ("C15850", "Basic, Samsung CL21A106KAYNNNE, 25V X5R +/-10%, 7M in "
                   "stock.  25 V on a 5 V rail is 5x derating, which matters "
                   "for X5R because its capacitance falls with DC bias"),
    # ---- ferrite -------------------------------------------------------
    ("600R@100MHz", "L_0805_2012Metric"):
        ("C1017", "Basic, GZ2012D601TF, 600R@100MHz, 500 mA, 300 mohm DCR.  "
                  "500 mA covers FB2001, which carries the whole ~110 mA; "
                  "300 mohm there is 33 mV, negligible"),
    # ---- resistors, all one Basic series except where noted -------------
    ("0R",     "R_0805_2012Metric"): ("C17477",   "Basic 0805W8F0000T5E"),
    ("22R",    "R_0805_2012Metric"): ("C17561",   "Basic 0805W8F220JT5E"),
    ("33R",    "R_0805_2012Metric"): ("C17634",   "Basic 0805W8F330JT5E"),
    ("47R",    "R_0805_2012Metric"): ("C17714",   "Basic 0805W8F470JT5E"),
    # Checked: there is genuinely no Basic 47R in 1206, no Basic 2010 at all,
    # and no Basic C0G 10n -- unlike the 10n and 10u above, where there was.
    ("47R",    "R_1206_3216Metric"): ("C17969",   "1206W4F470JT5E, 250 mW; no "
                                                  "Basic 47R exists in 1206"),
    ("51R",    "R_0805_2012Metric"): ("C17738",   "Basic 0805W8F510JT5E"),
    ("51R 1%", "R_0805_2012Metric"): ("C17738",   "same part as '51R' -- the "
                                                  "two value strings are the "
                                                  "same 1% resistor"),
    ("100R",   "R_0805_2012Metric"): ("C17408",   "Basic 0805W8F1000T5E"),
    ("330R",   "R_0805_2012Metric"): ("C17630",   "Basic 0805W8F3300T5E"),
    ("1k",     "R_0805_2012Metric"): ("C17513",   "Basic 0805W8F1001T5E"),
    ("2k2",    "R_0805_2012Metric"): ("C17520",   "Basic 0805W8F2201T5E"),
    ("3k3",    "R_0805_2012Metric"): ("C26010",   "Basic 0805W8F3301T5E"),
    ("10k",    "R_0805_2012Metric"): ("C17414",   "Basic 0805W8F1002T5E"),
    ("100k",   "R_0805_2012Metric"): ("C149504",  "Basic 0805W8F1003T5E"),
    ("1M 1%",  "R_0805_2012Metric"): ("C17514",   "Basic 0805W8F1004T5E, +/-1%"),
    # ---- the heater ----------------------------------------------------
    ("560R", "R_2010_5025Metric"):
        ("C48997026", "CL2010FN560RB, +/-1%, 750 mW, 200 V.  The 750 mW is "
                      "the number the whole heater design rests on: 400 mW "
                      "each is 53% of rating.  1% not 5% because 24 of these "
                      "in three groups ARE the heater and their matching is "
                      "the array's uniformity"),
    # ---- the one TVS -----------------------------------------------------
    ("SMAJ18A", "D_SMA"):
        ("C908771", "18 V standoff, 20 V VBR, 29.2 V clamp at 13.7 A -- "
                    "matches the datasheet checked in round 21 exactly"),

    # ---- through-hole headers: breakable strips, snapped to length -------
    # These are hand soldered (see HAND_SOLDER_NOTE), so what matters is that
    # the code buys the right pitch and enough pins, not that it matches the
    # footprint's pin count.  One 1x40 strip covers all fifteen single-row
    # positions with pins to spare.
    ("50R TERM", "PinHeader_1x02_P2.54mm_Vertical"):
        ("C2337", "2.54 mm 1x40P breakable male strip -- snap to 1x2.  "
                  "13 needed, plus 13 jumper shunts (see EXTRAS)"),
    ("BENCH +5V", "PinHeader_1x01_P2.54mm_Vertical"):
        ("C2337", "same 1x40P strip, snapped to a single pin"),
    ("BENCH GND", "PinHeader_1x01_P2.54mm_Vertical"):
        ("C2337", "same 1x40P strip, snapped to a single pin"),
    ("debug 2x10", "PinHeader_2x10_P2.54mm_Vertical"):
        ("C29952", "2.54 mm 2x40P double-row strip -- snap to 2x10"),
}

# Things that are NOT on the board but that you cannot use it without.
EXTRAS = [
    ("C5305", 13, "2.54 mm open-top jumper shunts for the thirteen 50R TERM "
                  "headers.  The board ships with them OFF -- fitting one on a "
                  "ZED-F9T channel destroys its TIMEPULSE output (see the unit "
                  "sheet warning), so they are a separate decision per channel"),
]

# Parts that are DNP on this board but that someone might one day fit.  These
# never reach the assembly BOM; they are carried so the reason and the right
# part number are written down where the exclusion is.
DNP_NOTES = {
    "Y3001": ("C362338",
              "IF you ever fit the crystal instead of the TCXO: "
              "TXM25M0004322DBCDO00T, 25 MHz, SMD3225-4P, 10 pF load, "
              "+/-10 ppm tolerance, +/-20 ppm over -40..+85 C, 30 ohm ESR.\n"
              "Round 24 surveyed 100 distinct 25 MHz 3225 crystals against "
              "Si5351 Table 8 (CL 6-12 pF, ESR <= 150 ohm, drive >= 100 uW) "
              "and note 1 (only 6, 8 or 10 pF can use the internal load "
              "capacitance, register 183 bits 7:6).  Results: 6 pF parts all "
              "exist but every one is at 52 pieces or fewer, so 8 and 10 pF "
              "are the real choices; +/-10 ppm is the tightest tolerance made "
              "in this package, so nothing better is available.  With ESR the "
              "only remaining discriminator and a 150 ohm limit, this part's "
              "30 ohm is the lowest of any fully specified candidate.\n"
              "Alternates: C70582 (YXC X322525MMB4SI, identical but 50 ohm "
              "ESR, 58k in stock -- take it if availability matters more) and "
              "C448646 (NDK NX3225SA, a better maker, but LCSC publishes "
              "neither an ESR nor a stability figure for it).\n"
              "Do NOT take the top search hit ABM8W-25.0000MHZ-4-D1X-T3: it "
              "is a 4 pF part, below the Si5351's 6 pF minimum, and no "
              "register setting can correct it"),
    "D101": (None, "BAV99 input clamp: fit only on a channel run UNTERMINATED "
                   "above ~6 Vpp open circuit -- its reverse leakage in the 1M "
                   "self-bias is 10 mV of drift per 10 nA"),
    "R106": (None, "1 pps 50R terminator: nothing here drives 50 ohm, and "
                   "fitting it on a ZED-F9T asks 66 mA of a 5 mA pin"),
    "R3004": (None, "0R selector for the EXTERNAL helper input.  Fit it AND "
                    "remove R3005 to run off the EXT HELPER IN SMA instead of "
                    "the on-board Si5351"),
    "R2026": (None, "0R that ties LDO_EN to the LDO input, so the 3.3 V rails "
                    "come up with NO host attached (a USB-I2C dongle on the "
                    "debug header).  Fit ONLY on a board that will never sit "
                    "on a PYNQ: with it fitted, bench power on an unpowered "
                    "host drives 26 Zynq I/O past their 0.55 V absolute max, "
                    "which is the thing round 28's interlock exists to stop"),
}

# Parts deliberately NOT given an LCSC code.
NO_PART = {
    # Test points are bare copper pads, not components.
    "TestPoint_Pad_D1.5mm": "bare pad, no component",
}


# ---------------------------------------------------------------------------
# JLCPCB placement rotation, per footprint
# ---------------------------------------------------------------------------
# KiCad's zero-orientation for a footprint and JLCPCB's zero-orientation for
# the same part in their feeders are not the same thing, and the offset is a
# property of THEIR library.  It cannot be derived from anything in this repo.
# The only authority is their "Confirm parts placement" preview.
#
# ROUND 33.  Every number below was read off that preview and is a correction
# to the KiCad-NATIVE rotation in GPSDO-PYNQ-Z2_cpl.csv.  Positive is
# counter-clockwise, which is KiCad's sign and JLCPCB's sign.
#
# Round 28 took these from the JLCKicadTools table rather than from a preview,
# and got two of them wrong -- one of them 59 times:
#
#   regex ^SOT-23 -> -90   matched SOT-23-5 AND SOT-23-6 with one number,
#                          under a comment that said "SOT-23-5 and SOT-23-6
#                          both".  That was an assumption, written as a
#                          statement, and never checked.  SOT-23-5 needs +180.
#                          SOT-23-6 really does need 270, so the one the
#                          comment was guessing about is the one it got right.
#   MSOP-10, FT5H          no entry at all, so no correction, so wrong.
#
# Hence EXACT footprint names, not prefixes.  A prefix is what let one wrong
# number reach 59 of 458 placements.
#
#   footprint: (correction, the part(s) it was read off, what to look at)
JLC_ROTATION = {
    "SOT-23-5":                          (180, "U102 + 58 others",
                                          "pin 1 = the D input"),
    "SOT-23-6":                          (270, "U5009", "pin 1 dot"),
    "SOT-223-3_TabPin2":                 (180, "Q2001",
                                          "tab = drain, the wide pad"),
    "SOIC-8_3.9x4.9mm_P1.27mm":          (270, "U5001, U6001", "pin 1 dot"),
    "MSOP-10_3x3mm_P0.5mm":              (270, "U3001", "pin 1 dot"),
    "Oscillator_SMD_Fox_FT5H_5.0x3.2mm": (90,  "X3001",
                                          "pin 1 corner -- the footprint's "
                                          "marker is two 0.45 mm stubs and is "
                                          "hard to read; use the assembly "
                                          "drawing"),
}

# Looked at in the same preview and needing NO correction.  Listed rather than
# simply left out, so that "absent from both tables" can mean "nobody has
# looked at this one", which is what the release reports.
JLC_ROTATION_OK = {
    "D_SMA": ("D2001", "cathode band points south and the silkscreen's closed "
                       "side is south, so it is already right -- correcting "
                       "it would be the bug"),
}

# Two-terminal and unpolarised: which way round they go is not a question.
JLC_ROTATION_NA = (
    "C_0805_2012Metric", "R_0805_2012Metric", "L_0805_2012Metric",
    "R_2010_5025Metric", "R_1206_3216Metric", "Fuse_1206_3216Metric",
)
