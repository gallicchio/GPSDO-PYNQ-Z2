#!/usr/bin/env python3
"""Write HANDBOOK.md: the one document you read with the board in your hand.

    python3 gen/handbook.py              # or just: python3 build.py

Round 29.  Everything in it is DERIVED -- from gen/design.py (the header map,
the thirteen channels, the sources and their levels), from pcb/geom.py (where
every connector physically is), from pcb/tile.py and pcb/labels.py (what the
silkscreen says), from gen/jlc.py (the design rules) and from the gateware's
own generated constants (the register and channel maps).  Nothing here is
typed twice, so nothing here can drift from the board.

Three readers, in this order, because that is the order they turn up:

  * TODAY, with no board: wiring a bare Si5351 module onto the PYNQ-Z2's own
    Raspberry Pi header and getting the software path working against it.
  * BRING-UP, with the first board: what to plug in, in what order, what each
    test point should show, and which jumper must be fitted on which channel.
  * USE: which SMA is which channel, which channel is which register, and
    what the numbers mean.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "pcb"))
sys.path.insert(0, os.path.join(ROOT, "gateware"))

import design as D                                        # noqa: E402
import jlc                                                # noqa: E402
import geom as G                                          # noqa: E402
import tile as T                                          # noqa: E402
import labels as L                                        # noqa: E402
import handbook_figs as HF                                # noqa: E402


def figs():
    """{f_<name>: markdown image} for every picture gen/handbook_figs.py draws.
    The paths are relative to HANDBOOK.md."""
    return {"f_" + n: "![%s](docs/handbook/%s.png)" % (title, n)
            for n, title, _items in HF.FIGS}


def _i2c_devices():
    """The bus map, from the driver that talks to it."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "gateware"))
        from driver.i2c_devices import EXPECTED_DEVICES
        return sorted(EXPECTED_DEVICES.items())
    except Exception as e:                                 # pragma: no cover
        return [(None, "driver/i2c_devices.py not importable: %s" % e)]


def _edge():
    """How close any SMT pad gets to the board edge, measured on the board."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "mfg"))
        import make_fab
        m = make_fab.measure()
        return m["smt_to_edge_mm"], m["smt_to_edge_ref"]
    except Exception:                                      # no board built yet
        return None, ""


def _gateware():
    try:
        from driver import dmtd_constants as C
        return C
    except Exception:                                      # pragma: no cover
        return None


# ===========================================================================
# 1.  the 40-pin header, drawn
# ===========================================================================
def _pin_role(net):
    if net == "+3V3_HOST":
        return "the PYNQ's own 3.3 V -- WE LEAVE IT OPEN"
    if net == "+5V_HDR":
        return "board power in (this is how the board is normally powered)"
    if net == "GND":
        return "ground"
    if net.startswith("I2C_"):
        return "I2C (2k2 pull-up already on the PYNQ-Z2)"
    if net == "HELPER_CLK":
        return "helper clock -> FPGA.  MRCC ball, and the one the gateware uses"
    return ""


def header_art():
    """The 2x20, drawn the way every Pi pinout is drawn: pin 1 top-left."""
    rows = []
    for odd in range(1, 41, 2):
        ln, lz = D.HEADER[odd][0], D.HEADER[odd][1]
        rn, rz = D.HEADER[odd + 1][0], D.HEADER[odd + 1][1]
        rows.append("   %14s %-4s %2d | %s   %s | %-2d %-4s %s"
                    % (ln, lz or "", odd,
                       _dot(odd), _dot(odd + 1), odd + 1, rz or "", rn))
    body = "\n".join(rows)
    return (
        "                                     +---------------+\n"
        "%s\n"
        "                                     +---------------+" % body)


# The five pins section 2 actually asks you to put a wire on.  By NUMBER, not
# by net: there are eight grounds and two 3.3 V pins, and marking all of them
# turns the drawing into a starfield.
SI_PINS = (1, 3, 5, 6, 18)


def _dot(pin):
    return "*" if pin in SI_PINS else "o"


def orientation_art():
    return r"""
    PYNQ-Z2, seen from ABOVE (component side up), its RPi header along the
    top edge.  Our board plugs onto that header and overhangs UPWARD in this
    picture -- away from the Zynq, out over the desk.

            <------------------------ 137.0 mm ------------------------>
            +----------------------------------------------------------+  ^
            |                    o  hole (4.3, 4.3)   o hole (133.3,4.3)|  |
            |  [audio][ USB-A ][  HDMI  ]  39 ........ 3 1   odd  row   |  |
            |                              40 ........ 4 2   even row   |  |
            |                                                          | 87.0
            |                                                          |  |
            |[ETH]                     Zynq                            |  |
            |[USB]                                                     |  |
            +----------------------------------------------------------+  v

    PIN 1 IS AT THE RIGHT-HAND END, on the row NEAREST the PYNQ-Z2's top edge
    (The PYNQ-Z2's own silkscreen prints "1  2" at the right end and 
    "40 39" at the left).  Odd pins are the PYNQ's OUTER row, even pins the inner.

    Our board carries the mating socket on its UNDERSIDE, so on OUR board the
    same pins run mirrored: looking down at our silkscreen, pin 1 is at the
    RIGHT of the socket, the odd row is the UPPER of the two, and every pin is
    named on the silkscreen beside its own pad -- odd names above the odd row,
    even names below the even row.
""".rstrip()


# ===========================================================================
# 2.  the board, drawn
# ===========================================================================
def board_art():
    """A plan view of our own board, plotted from pcb/geom.py.

    2 mm per column, 4 mm per row.  Every coordinate here is read from the
    same tables the board is built from, so if a jack moves, this moves.
    """
    SX, SY = 2.0, 4.0
    nx, ny = int(G.BW / SX) + 2, int(G.BH / SY) + 2
    cv = [[" "] * nx for _ in range(ny)]

    def put(x, y, s):
        cx, cy = int(x / SX + 0.5), int(y / SY + 0.5)
        if not 0 <= cy < ny:
            return
        for i, ch in enumerate(s):
            if 0 <= cx + i < nx:
                cv[cy][cx + i] = ch

    def box(x0, y0, x1, y1):
        c0, r0 = int(x0 / SX + 0.5), int(y0 / SY + 0.5)
        c1, r1 = int(x1 / SX + 0.5), int(y1 / SY + 0.5)
        for c in range(max(0, c0), min(nx, c1 + 1)):
            for r in (r0, r1):
                if 0 <= r < ny and cv[r][c] == " ":
                    cv[r][c] = "-"
        for r in range(max(0, r0), min(ny, r1 + 1)):
            for c in (c0, c1):
                if 0 <= c < nx and cv[r][c] == " ":
                    cv[r][c] = "|"
        for c, r in ((c0, r0), (c1, r0), (c0, r1), (c1, r1)):
            if 0 <= r < ny and 0 <= c < nx:
                cv[r][c] = "+"

    # ---- boxes first, then anything with words in it ----------------------
    box(0, 0, G.BW, G.BH)
    box(G.XC - G.HELPER_HW, 6.0, G.XC + G.HELPER_HW, 152.0)   # the helper band
    box(112.0, 1.0, 190.0, 32.0)                              # power
    box(4.0, 3.0, 76.0, 31.0)                                 # 1-Wire
    box(38.0, 164.0, 106.0, 178.0)                            # housekeeping
    for lab, (bx, by) in ((["HELPER", "CLOCK", "FAN-OUT"], (G.XC - 14.0, 60.0)),
                          (L.REGION["power"], (150.0, 24.0)),
                          (L.REGION["house"], (52.0, 172.0)),
                          (["1-WIRE THERMOMETERS"], (16.0, 27.0))):
        for i, s in enumerate(lab):
            put(bx, by + i * SY, s)
    # every SMA, with the label its silkscreen actually prints
    for x, y, tag, _desc in G.sma_rows():
        put(x - 1.0 * len(tag), y, "(%s)" % tag)
    # the cabled connectors
    for i, jx in enumerate(G.PROBE_X):
        put(jx - 2.0, 8.0, "[%s]" % L.PROBE_TAG(i + 1))
    put(178.0, 16.0, "[15 V JACK]")
    put(146.0, 5.0, "[+5V]")
    put(136.0, 5.0, "[GND]")
    put(26.0, 174.0, "[DEBUG 2x10]")
    put(116.0, 174.0, "[ RPi 2x20 SOCKET, UNDERSIDE ]")
    for (mx, my), kind, _note in G.MOUNT:
        put(mx - 2.0, my, "(O)" if kind == "hole" else "[=]")

    ruler = [" "] * nx
    for mm in range(0, int(G.BW) + 1, 20):
        s = "%d" % mm
        for i, ch in enumerate(s):
            if int(mm / SX) + i < nx:
                ruler[int(mm / SX) + i] = ch
    out = ["    " + "".join(ruler).rstrip()]
    for r, row in enumerate(cv):
        s = "".join(row).rstrip()
        if s:
            out.append("%3d %s" % (int(r * SY), s))
    out += ["",
            "    (n)  10 MHz SMA for unit n        (Pn)  that unit's 1 pps SMA",
            "    (HIN)/(HO)  external helper in / HO out (CLK2, buffered)",
            "    [Wn] 1-Wire screw terminal        (O) M3 hole   [=] M3 slot",
            "    numbers down the left and across the top are millimetres"]
    return "\n".join(out)


# ===========================================================================
# 3.  tables
# ===========================================================================
def header_table():
    w = ["| pin | net | Zynq | what it is |", "|---:|:---|:---|:---|"]
    for p in range(1, 41):
        net, zynq, _site, use = D.HEADER[p]
        w.append("| %d | `%s` | %s | %s |"
                 % (p, net, zynq or "--", use or _pin_role(net)))
    return "\n".join(w)


def channel_table():
    C = _gateware()
    w = ["| unit | 10 MHz SMA | 1 pps SMA | source | shunt, source running | beat net | "
         "pin | ball | pps net | pin | driver slot |",
         "|---:|:---|:---|:---|:---|:---|---:|:---|:---|---:|:---|"]
    pin_of = {}
    for p in range(1, 41):
        pin_of[D.HEADER[p][0]] = (p, D.HEADER[p][1])
    for n, beat, pps, src, term, _rs, _rsh, _note in D.UNITS:
        bp, bb = pin_of.get(beat, ("--", ""))
        pp, _ = pin_of.get(pps, ("--", "")) if pps else ("--", "")
        slot = "beat %d" % (n - 1)
        if C and pps:
            slot += ", pps %s" % C.PPS_SLOT[n - 1]
        w.append("| %d | `%s` | %s | %s | %s | `%s` | %s | %s | %s | %s | %s |"
                 % (n, "%d" % n, ("`P%d`" % n) if pps else "--", src,
                    "**50R**" if term == "IN" else "**none** (never 50R)",
                    beat, bp, bb, ("`%s`" % pps) if pps else "--", pp, slot))
    return "\n".join(w)


def levels_table():
    w = ["| unit | source | at the SMA | at the squarer input | slew rate | "
         "load | IN U.FL into 50 ohm |", "|---:|:---|:---|:---|:---|:---|:---|"]
    for n, _b, _p, src, term, rs, rsh, _note in D.UNITS:
        lv = D.levels(n, term, rs, rsh)
        # the tap's 1k into the scope's 50R: /21 (rev B item 19)
        tap = ("%.0f mVpp" % (1e3 * lv["v_sma"] * 50.0 / 1050.0) if term == "IN"
               else "leave unplugged")
        w.append("| %d | %s | %s | %s | %s | %s | %s |"
                 % (n, src, lv["at_sma"], lv["at_gate"], lv["slew"], lv["load"], tap))
    return "\n".join(w)


TP_FIG = {"In": "unit1", "S": "unit1", "B": "unit1", "P": "pps",
          "5": "rails", "A": "rails", "D": "rails", "X": "ref"}


def testpoint_table():
    w = ["| letter | net / node | where | what you should see |",
         "|:---|:---|:---|:---|"]
    for letter, value, where, expect in L.TEST_POINTS:
        if letter in TP_FIG:
            where += " ([picture](docs/handbook/%s.png))" % TP_FIG[letter]
        w.append("| **%s** | `%s` | %s | %s |" % (letter, value, where, expect))
    return "\n".join(w)


# Rev B item 19: every U.FL, what it watches, and what plugging it in does.
# (silk name, where, node, series part, into a 50 ohm scope, plugged in)
TAPS = [
    ("IN", "each 10 MHz box, between the SMA and the 50R/PARK header",
     "the input node, on the SMA side of the 10n: the same node as `In`", "1k",
     "the input /21: the last column of the levels table",
     "1050 ohm on the input, 2-5 % of its amplitude, 50-100 ps while plugged "
     "in.  Not on units 2 and 3 (the jumper note's first rule)"),
    ("SQ", "each 10 MHz box, beside the sampling flip-flop",
     "the squarer's output 1Y, the edge the flip-flop samples", "1k",
     "a 0/3.3 V square /21, ~0.15 Vpp; near 50 % duty when the input is "
     "centred on the threshold.  Parked: ~0.16 V DC",
     "~3 mA from an unbuffered gate's output: it moves that channel's edge "
     "while plugged in"),
    ("REF", "helper band, between the TCXO and the Si5351C",
     "the TCXO at the Si5351C's CLKIN", "1k",
     "25 MHz HCMOS /21, ~0.15 Vpp", "3 mA from the TCXO: common to every channel"),
    ("CLK0", "helper band, just below the Si5351C",
     "the helper at the Si5351C's pin, before the helper squarer's 10n", "1k",
     "10.0012344 MHz, 0/3.3 V /21",
     "load on the Si5351's own 2 mA output -- load on its outputs is what made "
     "rev A slip.  A look, not a long watch: use HCLK for that"),
    ("HCLK", "helper band, beside the lower LMK1C1108 (U3005)",
     "a spare LMK1C1108 output, through 33 R like every channel's branch", "33R",
     "the helper as every channel gets it: ~1.2 Vpp (the LMK's 50 ohm output "
     "and the 33 R against the scope's 50)",
     "~12 mA from the fan-out's supply, which every channel's branch shares: "
     "plug it in before a run and leave it, rather than during one"),
    ("+5V, +3V3_A, +3V3_D", "bottom edge, in the housekeeping block, left to right",
     "the rails; +3V3_A at the far end of its plane, under unit 13", "1k",
     "DC /21 (0.24, 0.16, 0.16 V) and the ripple /21; into 1 MOhm the rail itself",
     "3-5 mA: nothing"),
]


# which picture (gen/handbook_figs.py) shows each tap
TAP_FIG = {"IN": "unit1", "SQ": "unit1", "REF": "ref", "CLK0": "clk0", "HCLK": "hclk",
           "+5V, +3V3_A, +3V3_D": "rail_taps"}


def tap_table():
    w = ["| U.FL | where | node | series | into a 50 ohm scope | plugging it in |",
         "|:---|:---|:---|:---|:---|:---|"]
    for name, where, node, ser, see, cost in TAPS:
        where += " ([picture](docs/handbook/%s.png))" % TAP_FIG[name]
        w.append("| **%s** | %s | %s | %s | %s | %s |" % (name, where, node, ser, see, cost))
    return "\n".join(w)


def drc_table():
    w = ["| rule | JLCPCB minimum | our DRC | margin | why |",
         "|:---|---:|---:|:---|:---|"]
    for name, j, ours, margin, note in jlc.table():
        w.append("| %s | %.4g mm | %.4g mm | %s | %s |"
                 % (name, j, ours, margin, note))
    return "\n".join(w)


def i2c_table():
    w = ["| address | device | on the board |", "|:---|:---|:---|"]
    where = {0x18: "U6001, behind the five screw terminals",
             0x60: "U3001, on the helper block at the centre line",
             0x61: "U5009, in the housekeeping block"}
    for a, nm in _i2c_devices():
        if a is None:
            w.append("| -- | %s | |" % nm)
            continue
        if a not in where:                     # the eight TMP1075s, 0x48..0x4F
            where[a] = "U500%d, %s" % (a - 0x48 + 1, D.TMP_WHERE[a - 0x48])
        w.append("| 0x%02X | %s | %s |" % (a, nm, where[a]))
    return "\n".join(w)


# ===========================================================================
# the document
# ===========================================================================
def text():
    C = _gateware()
    si_pins = [(p, D.HEADER[p][0]) for p in SI_PINS]
    si = "\n".join("    pin %-2d  %-12s -> %s" % (p, n, L.SI5351_WIRING[n])
                   for p, n in si_pins if p in SI_PINS or p == 17)
    npads = sum(1 for _ in D.UNITS)
    return """\
# GPSDO DDMTD front end -- handbook

**rev %(rev)s, %(date)s.**  GENERATED by `gen/handbook.py`; do not edit.
Run `python3 build.py` (or `python3 gen/handbook.py`) to rebuild it.
%(revnote)s
Thirteen 10 MHz DDMTD channels and twelve 1 pps inputs on one board that plugs
onto the Raspberry Pi header of a PYNQ-Z2.  A %(fh).6f MHz helper samples every
10 MHz reference, which stretches time by %(gain).0f: one helper cycle of beat
displacement is **%(tres).2f ps** of input phase, and the FPGA measures the beat
edges with an ordinary counter.

Contents: [1 the header](#1-the-raspberry-pi-header) *
[2 a Si5351 on the bare PYNQ](#2-today-a-si5351-module-on-the-bare-pynq-z2) *
[3 the I2C bus](#3-the-i2c-bus) *
[4 the board](#4-the-board) *
[5 the thirteen channels](#5-the-thirteen-channels) *
[6 test points](#6-test-points-and-what-the-silkscreen-means) *
[7 power](#7-power-and-the-one-way-to-get-it-wrong) *
[8 bring-up](#8-bring-up-in-order) *
[9 using it](#9-using-it) *
[10 mechanical](#10-mechanical) *
[11 manufacturing](#11-manufacturing-and-the-drc)

---

## 1  The Raspberry Pi header

Every one of the forty pins is used: 8 ground, 2 x 5 V in, 2 x 3.3 V that we
deliberately leave open, I2C, the helper clock, thirteen beats and twelve pps.
Nothing is spare.  `*` marks the five pins section 2 needs.

```
%(orient)s
```

```
%(hdr)s

   *  = needed to drive a bare Si5351 module (section 2)
```

%(hdrtab)s

---

## 2  TODAY: a Si5351 module on the bare PYNQ-Z2

With no front-end board yet, a Si5351 breakout wired to five pins of the
PYNQ-Z2's own header exercises the entire software path: the I2C driver, the
synthesiser programming, the PLL lock check, the overlay, and the measurement
core's helper counter.  Everything in `gateware/driver/i2c_devices.py` except
the thermometers, the 1-Wire bridge and the heater DAC.

```
%(si)s
```

The PYNQ-Z2 already carries 2.2 kOhm pull-ups on SDA and SCL (R305-R308), so
the module's own pull-ups may be left fitted or removed; both work.

Take 3.3 V from **pin 1** or **pin 17**.  Those are the two pins the finished
board leaves open on purpose -- it makes its own 3.3 V from the 5 V pins -- so
using them now does not teach you a habit you have to unlearn.  Do not feed
the module 5 V: the Si5351 is a 3.3 V part.

CLK0 is the helper output.  Wiring it to **pin 18** puts it on `%(hclk_ball)s`,
a clock-capable (MRCC) ball and the one the gateware's constraint file is
built for, so the helper counter reads a real frequency instead of zero.  Pin
31 (`U18`) is the header's other MRCC ball; this board carries a beat on it
and fits nothing for a second helper input, but that is where a future
revision's fallback would go.

    ssh xilinx@<pynq>
    cd ~/gpsdo-dmtd
    ./pynq-run bringup.py --scan          # who answers on the bus
    ./pynq-run bringup.py --no-heater     # program the Si5351, check lock

`bringup.py` asks the chip which board it is on (`--rev auto`): a breakout's
crystal is on XA, so it reads as rev A and gets rev A's image -- the helper on
CLK0, the null on CLK1.  Add `--clk2 helper` and the third output carries a
second copy of the helper, so a scope or an ADALM2000 on CLK1 and CLK2 sees
%(fb).1f Hz of beat -- the number this whole instrument is built on -- with no
board in the system.  It is off by default, and refused on rev B, whose CLK2
is `HO`.

    ./pynq-run bringup.py --no-heater --clk2 helper   # on the PYNQ
    python3 gateware/board/m2k_beat.py                # on the laptop

`m2k_beat.py` drives an ADALM2000 over libiio (no Scopy, no libm2k) and
measures the beat from the PHASE RAMP between the two channels rather than by
subtracting two 10 MHz frequencies: both channels share one ADC clock, so the
ramp cancels it.  Round 30 measured 1234.417 Hz against %(fb).3f by design.
Leave `gateware/board/console_log.py` running during a long session -- it logs
the PYNQ's serial console across resets, and distinguishes "Linux crashed"
from "the board lost power".

Expect the scan to show **0x60** and nothing else; with no front-end board the
thermometers, the DS2482 and the DAC are all absent, and `bringup.py` says so
rather than failing.  After programming, the core's helper counter should read
%(fh).6f MHz +/- a few ppm (a Si5351 breakout's crystal is not a TCXO; the
real board's is).

---

## 3  The I2C bus

%(i2c)s

Addresses are fixed by strapping on the board; the eight TMP1075 differ only
by their address pins, and their numbering runs with their position -- see the
plan in section 4.

---

## 4  The board

```
%(boardart)s
```

Every connector is on an edge, and every edge is one kind of thing:

* **top edge, left**: five 3-way screw terminals for external 1-Wire probes.
* **top edge, right**: the 15 V heater jack, and the two bench 5 V posts that
  are normally left empty.
* **left and right columns**: the SMAs.  Each unit is a horizontal strip
  pointing inward at the helper on the centre line: 1 pps jack, 1 pps
  circuit, 10 MHz jack, 10 MHz circuit, helper.  Odd units down the left,
  even units down the right, so the numbers run 1..13 down the board.
* **bottom edge**: the 2x20 socket (on the underside), and the 2x10 debug
  header.

---

## 5  The thirteen channels

%(chan)s

The shunt column is for a RUNNING source.  **Whenever a channel's source is
off or unplugged, its shunt goes on PARK** -- the third rule below.

Unit %(nch)d is the **null channel**: no 1 pps, and its 10 MHz input is meant to be
cabled from `HO` -- the Si5351C's CLK2 at exactly 10.000000 MHz, through a
74LVC1G125 and 33 R -- into the jack marked `%(nch)d` (`%(nulltag)s`) with a short
SMA cable.  Subtracting it removes everything common to the board and leaves
the difference between the GPSDOs, which is the measurement.

### The 50R/PARK header is the one thing you can break something with

%(termnote)s

### Expected levels, channel by channel

%(levels)s

---

## 6  Test points and what the silkscreen means

Every test point is a 1.5 mm pad with its key printed beside it.  The keys are
one character each except the 10 MHz input's, which is `In`: at 1.5 mm in
KiCad's stroke font a capital `I` and a `1` are the same three strokes, and
this board has jacks called `1`.

%(tp)s

The two SMA ranges, which the board also prints along the bottom:

* 10 MHz in: %(vmin).1f to %(vmax).1f Vpp AC **at the SMA** -- that is the
  range the thirteen sources in this inventory actually present, each with its
  own jumper setting.  The board's ceiling is %(vabs).1f Vpp: R_S is a link on
  every channel, so the swing at the SMA is the swing at the gate, and the gate
  tolerates a diode drop outside each rail.  A source's OPEN-CIRCUIT rating is
  a different number and is not a limit on this connector -- the TM-4 is
  %(vopen).1f Vpp open circuit and 2.0 Vpp at the SMA through its mandatory
  50 ohm jumper.  Round 29 printed the %(vopen).1f on the silkscreen, which was
  backwards: see the jumper note above.
* 1 pps in: 0 to 5.5 V DC; it reads high above 2.3 V (the 74LVC1G17's
  worst-case 2.08 V through the 1k/10k divider; round 45 measured 1.88-1.98 V
  at the jack).
* `HO` out: 0/3.3 V from a 74LVC1G125 through 33 R: ~1.8 Vpp into 50 ohm,
  3.3 Vpp into a high impedance.  Into 50 ohm the buffer sources ~30-35 mA
  peaks, over its 24 mA rating: fine for the null channel's short cable and a
  counter, not for a long run into a 50 ohm instrument.

### The U.FL taps

Rev B puts a U.FL on every node worth watching for longer than a probe can be
held (item 19).  Each is fed through its own resistor, so the ratio is built
in: a stock U.FL-to-BNC pigtail into a **50 ohm** input reads the node /21
through 1k.  Into 1 MOhm the pigtail's ~50-100 pF and the 1k roll a 10 MHz
signal off; use 1 MOhm for the rails.  Unplugged, a tap costs its node under
0.02 %% of its amplitude.  The silkscreen names each one beside it; their J
numbers are on the assembly drawing only.

%(taps)s

---

## 7  Power, and the one way to get it wrong

The board is **normally powered from the PYNQ-Z2**, through pins 2 and 4 of
the header.  Nothing else needs to be plugged in for the measurement to run.

The 15 V barrel jack is for the **heater only**.  It never touches the analog
rails, and the board works without it; the heater is what makes the board a
thermostat rather than a thermometer.

The two bench 5 V posts are an alternative to the header's 5 V, for using the
board on a desk with no PYNQ attached.  **They are the trap**, and round 21
found it: an unpowered Zynq I/O pin has an absolute maximum of 0.55 V (PYNQ-Z2
user manual, table 15), so bench-powering the board while the PYNQ is plugged
in but switched off drives 3.3 V into twenty-six of them.

Round 28 made that impossible rather than merely warning about it: the two
LDOs' ENABLE pin is tied to the header's own 5 V through R2025, so **with the
host off, this board makes no 3.3 V at all**, whatever is on the bench posts.
R2026 (a DNP 0R link) bridges ENABLE back to the input for anyone who wants
the old behaviour on a board that will never see a host.

**The bench posts as an ammeter.**  With the PYNQ ON, a bench supply on the
posts at 5.3 V, limited to 0.5 A, carries the whole board: the posts and the
header meet at an OR-ing diode and the higher one wins.  Its display is then
the board's current, which at the first power-up is the one number that says
the thirteen squarers are parked and nothing is shorted.  Bench output off
before the PYNQ goes off.

%(f_posts)s

Order of operations, every time:

1. Everything off.  The shunts set -- the first time, **all thirteen on
   PARK**.  This board onto the PYNQ-Z2's header.  Never plug it onto, or pull
   it off, a powered PYNQ.
2. The PYNQ-Z2 on, from **its own barrel jack J9** with the jumper at `REG`,
   not from micro-USB alone.  This board's 3.3 V rails come up with it.
3. `./pynq-run bringup.py` -- which writes the heater DAC's EEPROM to zero
   BEFORE anything else, because the part ships at mid-scale and that is
   1.65 V on three FET gates.
4. The sources, one at a time: the shunt to its setting FIRST (50R, or none
   for a ZED-F9T), then the cable, then the source on.  A source that goes off
   for long puts its shunt back on PARK.
5. Only then the 15 V jack (the picture is in section 8, step 9).

Power down in reverse: the 15 V jack, the bench supply if there is one, the
PYNQ.  The sources may stay cabled to a board that is off: each reaches its
squarer through a 10n, and the squarer's inputs have no diode to their supply.

---

## 8  Bring-up, in order

Rev B's first board.  Each step says what to read and what it should be; stop
at the first one that is not.

Every picture here is cut from the board's own 3D render
(`gen/handbook_figs.py`), drawn as the board sits behind the PYNQ-Z2: **the
2x20 socket's edge nearest you**, the screw terminals and the 15 V jack
furthest away.  On the left, the whole board and a red box; on the right, that
box: the red circle is the part or pin, the yellow box the words the board
prints for it.  The build checks every one of them: those words must be beside
that part, and nearer it than any other part of its kind -- another test
point, U.FL, jack or pin.

1. **Before power, on the bench.**  Ohmmeter on the socket's pads from the
   top, where each pin's name is printed.  Pins 1 and 17 (`nc`) connect to
   nothing on this board: each reads open to pin 2 (`5V`) and to pin 6
   (`GND`).  Then the rails: the `+5V` post, test point `A` and test point
   `D` each to the `GND` post (pictures in step 2 and section 7) read high,
   not a short.

   %(f_socket_pins)s

   **All thirteen shunts on PARK**: pins 2-3, the end of each header with
   `PARK` printed beside it -- on every unit the end AWAY from its SMA.
   Thirteen shunts a board ship loose in the bag, plus spares.

   %(f_jp_left)s
   %(f_jp_right)s

2. **First power.**  Board on the header, PYNQ off; a bench supply on the
   posts at 5.3 V, 0.5 A limit, output off.  The PYNQ on, then the bench
   output on.
   * The bench display: **0.25-0.35 A** with every channel parked (+3V3_A
     160-220 mA, +3V3_D ~100 mA, both through their LDOs).  Over 0.45 A:
     everything off, and look for a channel that is not parked, or a short.
   * Test point `5` 4.9-5.3 V; `A` and `D` 3.25-3.35 V; the `+3V3_A` U.FL,
     at the far end of the plane, a few tens of mV below `A` at most (rev A
     lost 110 mV in its tracks; rev B's is a plane).

     %(f_rails)s
     %(f_rail_taps)s

   * `S` on every unit: **~0.14 V DC, still** -- parked.  The left-hand units
     (odd numbers) all look like unit 1, the right-hand ones like unit 2.

     %(f_unit1)s
     %(f_unit2)s

   * `X`: 25 MHz, 0/3.3 V.

     %(f_ref)s

3. **`./pynq-run bringup.py`.**  In order: every address in section 3
   answering; the DAC made safe; "reference seen on: CLKIN (rev B)"; both
   PLLs LOCKED; **zero helper slips**; eight thermometers within a few
   kelvin of each other; the 1-Wire bus idle high with no short; and the
   selftest with all thirteen channels quiet -- a parked squarer makes no
   beat, and that is a pass.  "Locked" is not enough on its own: round 39's
   first board cycle-slipped ~650 times a second with LOL clear, so
   `bringup.py` counts the slips and reprograms if it sees any.  It reads the
   board off the chip (`--rev auto`); if it says the reference is on NEITHER
   input, the TCXO is not running: look at `X`.
4. **The reference and the helper.**
   * `REF` U.FL into 50 ohm (beside `X`, picture in step 2): 25 MHz,
     ~0.15 Vpp; on a counter 25 MHz +/- 62 Hz (the TCXO's 2.5 ppm).
   * `HCLK` U.FL: the helper as every channel gets it, 10.0012344 MHz; the
     core's helper counter %(fh).6f MHz.  For a long look use HCLK, not CLK0
     (section 6).

     %(f_hclk)s
     %(f_clk0)s

   * `HO` on a counter: 10.000000 MHz.

     %(f_ho)s

5. **The null channel first.**  Unit %(nch)d's header from PARK to 50R, then a
   short SMA cable from `HO` to the jack marked `%(nch)d` (`%(nulltag)s`).
   `./pynq-run bringup.py --no-heater --inputs %(nch)d`, then
   `./pynq-run beats.py record 20 %(nch)d`.  Its beat should be %(fb).1f Hz and
   its phase reading flat: that is the instrument floor, and everything else
   is measured against it.  On unit %(nch)d, `S` shows the square about the
   threshold and the `SQ` U.FL a 0/3.3 V square /21 near 50 %% duty.  Judge a
   beat by `python3 beats.py analyse` on the laptop, not by the edge count:
   the core does not deglitch yet, so a real beat's edges chatter (round 39:
   2-6 rising edges a transition).  `./pynq-run si_watch.py watch 600 %(nch)d`
   is the long test of both PLLs.

   %(f_null)s

   *One comparison worth making*: the same with unit %(nch)d's shunt OFF
   instead of 50R.  HO's 33 R already back-terminates the cable, so its far
   end may be left open: the null input then sees 3.3 Vpp with twice the
   slew, and the buffer stops sourcing its ~35 mA peaks from +3V3_D.  If the
   floor is no worse, run the null channel that way.
6. **The sources, one at a time** (section 5's table, and the header's three
   rules): the shunt first, then the cable, then the source on.  For each,
   on that unit (pictures of units 1 and 2 in step 2): the board's current up
   by a few mA, not 10-15 (a driven gate is out of its linear region most of
   each cycle); the `IN` U.FL the source as it arrives, /21 (the levels
   table's last column; not on units 2 and 3); `S` the sine or triangle
   about the threshold; `SQ` a square near 50 %% duty; a beat.  A channel
   left on 50R with its source off is quiet, chatters, or oscillates at
   ~0.57 MHz, and draws its 10-15 mA: park it.
7. **One source into two channels** through a splitter: the two readings
   should differ by a constant, not a drift (`beats.py`, "pairs").
8. **Each unit's own pps** against its own 10 MHz edge.  The `P` jacks are
   the outer column on each side; `P` is the test point.

   %(f_pps)s

9. **The heater, last.**  With the DAC made safe by step 3, the 15 V jack;
   then `./pynq-run heater.py on`: ~9.6 W, and every thermometer rises.
   U5007 (0x4E), beside the fan-out and marked `T`, is the sensor rev B's
   thermostat will hold (item 20); the loop is still to be written
   (`Heater.duty_cycle` is its helper).  `heater.py off` before the jack
   comes out.

   %(f_jack15)s
   %(f_u5007)s

---

## 9  Using it

```python
from driver import attach
core = attach(overlay)
snap = core.snapshot()          # every channel, one coherent instant
```

* %(nbeat)d beat channels in slots 0..%(nbeat_1)d, %(npps)d pps returns in slots
  %(pps0)d..%(pps_last)d; slot %(null)d is the null channel.
* One helper cycle of beat displacement is %(tres).4f ps of input phase, and the
  measurement wraps at %(wrap).0f ps -- one whole 10 MHz cycle.
* The beat frequency is %(fb).1f Hz by design; in service it is re-centred in
  software from the measured helper frequency, because a +/-2.5 ppm TCXO is
  +/-25 Hz of beat.

---

## 10  Mechanical

Board: **%(bw).1f x %(bh).1f mm**, 4 layers, 1.6 mm.  It rides %(ride).1f mm above the
PYNQ-Z2 on the socket, and overlaps only the %(overlap).1f mm strip along the
PYNQ's top edge, so everything tall on the PYNQ stays in open air.

%(mount)s

A desk standoff must be clear of the PYNQ-Z2's own outline, which on this
board means clear of x 35..172 in the bottom 11 mm; the shared one is the
opposite, and screws into the host's own hole.  The PYNQ's OTHER mounting
hole, at board (39.3, 173.3), is underneath the 2x10 debug header and cannot
be drilled; the 2x20 header plus the one slot locate this board against the
host in both axes anyway.  Hardware per board: four M3 standoffs to the desk
or the base plate, one M3 screw through the slot into the PYNQ's own
standoff.

---

## 11  Manufacturing, and the DRC

The DRC this project runs is set from `gen/jlc.py`, one row per rule, and every
row asserts that our number is at least as strict as JLCPCB's published
capability for a standard 4-layer FR-4 board.  A board that passes our DRC is
inside their capability by construction.

%(drc)s

Two things KiCad does not check and this project therefore does itself:

* **silkscreen line width.**  KiCad's stock footprints draw their outlines at
  0.12 mm, below JLCPCB's 6 mil minimum, and no DRC rule looks at a graphic
  line's width -- only at text.  `pcb/build_pcb.py` raises every silkscreen
  stroke below %(silkmin).2f mm as the footprint is placed.
* **what the silkscreen SAYS.**  Every label on this board is emitted from the
  same table that places the part it refers to, so a heater's `H` cannot end
  up beside a different heater and a jack's name cannot outlive the jack.

### Assembly, and the one number to look at before ordering

%(edge)s

Everything nearer the edge than that is through hole -- the SMA jacks, the
five screw terminals, the barrel jack and the two bench posts -- and JLCPCB
fits it, with every header and the 27 SMAs.  Bottom side: the 2x20 socket,
J4001, and nothing else, and you solder it (`hand_solder_bom.csv`): on JLCPCB's
order it made the job two-sided, about $39 more per order for a $0.32 part.
The thirteen jumper shunts ship loose.
""" % dict(
        rev=D.REV, date=D.DATE, revnote=_rev_note(),
        fh=D.F_HELPER / 1e6, gain=D.N_GAIN, tres=D.T_RES_PS,
        fb=D.F_BEAT,
        orient=orientation_art(), hdr=header_art(), hdrtab=header_table(),
        si=si, hclk_ball="%s (%s)" % (D.HEADER[18][1], D.HEADER[18][2]),
        i2c=i2c_table(), boardart=board_art(), chan=channel_table(),
        levels=levels_table(), tp=testpoint_table(), drc=drc_table(),
        nch=D.UNITS[-1][0], nulltag="J%d01" % D.UNITS[-1][0],
        termnote=L.TERM_NOTE,
        vmin=D.V_SMA_MIN, vmax=D.V_SMA_MAX, vabs=D.V_SMA_ABSMAX,
        vopen=D.V_SMA_OPEN_MAX,
        nbeat=(C.N_BEAT if C else 13), nbeat_1=(C.N_BEAT - 1 if C else 12),
        npps=(C.N_PPS if C else 12), pps0=(C.PPS0 if C else 16),
        pps_last=(C.PPS0 + C.N_PPS - 1 if C else 27),
        null=(C.NULL_CHANNEL if C else 12),
        wrap=(C.WRAP_PS if C else 100000.0),
        bw=G.BW, bh=G.BH, ride=G.HDR_PIN_H, overlap=G.PZ_H - G.PZ_BOTTOM,
        mount=mount_table(), silkmin=jlc.SILK_LINE_MIN, edge=_edge_text(),
        taps=tap_table(),
        **figs(),
        npads=npads,
    )


def _rev_note():
    """Round 42: while a revision is undated it is work in progress, and the
    boards on the bench are the locked one before it."""
    if D.DATE[:2].isdigit():
        return ""
    prev = chr(ord(D.REV) - 1)
    return """
Rev %(rev)s is the design in progress and has not been ordered.  **The boards
on the bench are rev %(prev)s**, locked as JLCPCB built them: git tag
`GPSDO-PYNQ-Z2-rev%(prev)s`, with rev %(prev)s's own handbook in
`GPSDO-PYNQ-Z2-rev%(prev)s.zip`.  Until the rev %(rev)s board is rebuilt the
hardware below is still rev %(prev)s's; notes marked *rev %(prev)s* are
measurements on those boards, and `REV%(rev)s_CHANGES.md` lists what rev %(rev)s
changes.
""" % dict(rev=D.REV, prev=prev)


def _edge_text():
    d, ref = _edge()
    if d is None:
        return ("The closest-SMT-pad-to-board-edge measurement needs a built "
                "board; run `python3 build.py`.")
    return ("The closest SMT pad to the board edge is **%.2f mm**, on `%s`.  "
            "No KiCad rule checks this -- `copper_edge_clearance` is about "
            "copper, not about whether a placement nozzle and an edge clamp "
            "can both reach -- and it is the one figure in this project that "
            "is NOT comfortably inside a published capability.  JLCPCB's SMT "
            "line holds the panel by its edges; if %.2f mm is inside their "
            "rail allowance the board needs a break-away rail, which is a "
            "different panel and a different price.  Ask them rather than "
            "moving the part: `%s` is where it is because of what it "
            "decouples." % (d, ref, d, ref))


def mount_table():
    w = ["| at (mm) | kind | what it is for |", "|:---|:---|:---|"]
    for (mx, my), kind, note in G.MOUNT:
        w.append("| (%.1f, %.1f) | %s | %s |"
                 % (mx, my, "3.2 mm hole" if kind == "hole"
                    else "3.2 x 7 mm slot", note))
    return "\n".join(w)


def main():
    p = os.path.join(ROOT, "HANDBOOK.md")
    open(p, "w", encoding="utf-8").write(text())
    print("wrote HANDBOOK.md (%d lines)" % text().count("\n"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
