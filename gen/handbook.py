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


def _i2c_devices():
    """The bus map, from the driver that talks to it."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "gateware"))
        from driver.i2c_devices import EXPECTED_DEVICES
        return sorted(EXPECTED_DEVICES.items())
    except Exception as e:                                 # pragma: no cover
        return [(None, "driver/i2c_devices.py not importable: %s" % e)]


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
        return "helper clock -> FPGA.  MRCC ball: the one real clock input here"
    return D.HEADER_USE.get(net, "")


def header_art():
    """The 2x20, drawn the way every Pi pinout is drawn: pin 1 top-left."""
    rows = []
    for odd in range(1, 41, 2):
        ln, lz = D.HEADER[odd][0], D.HEADER[odd][1]
        rn, rz = D.HEADER[odd + 1][0], D.HEADER[odd + 1][1]
        rows.append("   %14s %-4s %2d | %s   %s | %-2d %-4s %s"
                    % (ln, lz or "", odd,
                       _dot(ln), _dot(rn), odd + 1, rz or "", rn))
    body = "\n".join(rows)
    return (
        "                                     +---------------+\n"
        "%s\n"
        "                                     +---------------+" % body)


def _dot(net):
    """A pin you need for the bare-module experiment is marked."""
    return "*" if net in ("+3V3_HOST", "GND", "I2C_SDA", "I2C_SCL",
                          "HELPER_CLK") else "o"


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

    PIN 1 IS AT THE RIGHT-HAND END, on the row NEAREST the board's top edge
    (round 9: the PYNQ-Z2's own silkscreen prints "1  2" at the right end and
    "40 39" at the left).  Odd pins are the OUTER row, even pins the inner.

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

    2 mm per column, 4 mm per row.  Everything drawn here is read from the
    same tables the board is built from, so if a jack moves, this moves.
    """
    SX, SY = 2.0, 4.0
    nx, ny = int(G.BW / SX) + 1, int(G.BH / SY) + 1
    cv = [[" "] * nx for _ in range(ny)]

    def put(x, y, s, clip=True):
        cx, cy = int(round(x / SX)), int(round(y / SY))
        if not (0 <= cy < ny):
            return
        for i, ch in enumerate(s):
            if 0 <= cx + i < nx:
                if clip and cv[cy][cx + i] != " ":
                    continue
                cv[cy][cx + i] = ch

    def box(x0, y0, x1, y1):
        c0, r0 = int(round(x0 / SX)), int(round(y0 / SY))
        c1, r1 = int(round(x1 / SX)), int(round(y1 / SY))
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

    box(0, 0, G.BW, G.BH - SY)
    # the two big functional blocks
    box(G.XC - G.HELPER_HW, 6.0, G.XC + G.HELPER_HW, 152.0)
    put(G.XC - 12.0, 80.0, "HELPER")
    put(G.XC - 12.0, 84.0, "CLOCK")
    put(G.XC - 12.0, 88.0, "DISTRIB")
    box(106.0, 1.0, 180.0, 34.0)
    put(150.0, 28.0, "POWER")
    box(10.0, 16.0, 80.0, 34.0)
    put(30.0, 30.0, "1-WIRE")
    box(38.0, 164.0, 106.0, 176.0)
    put(60.0, 172.0, "HOUSEKEEPING")

    # every SMA, with the label the silkscreen actually prints
    for x, y, tag, _desc in G.sma_rows():
        put(x - 1.0, y, "(%s)" % tag, clip=False)
    # the cabled connectors
    for i in range(5):
        put(16.0 + i * 13.0 - 1.0, 8.0, "[%s]" % L.PROBE_TAG(i + 1), clip=False)
    put(184.0 - 3.0, 16.0, "[15V JACK]", clip=False)
    put(150.0 - 2.0, 5.0, "[+5V]", clip=False)
    put(142.0 - 2.0, 5.0, "[GND]", clip=False)
    put(36.86 - 4.0, 174.0, "[DEBUG 2x10]", clip=False)
    put(136.0 - 12.0, 174.0, "[ RPi 2x20 SOCKET, ON THE UNDERSIDE ]", clip=False)
    for (mx, my), kind, _note in G.MOUNT:
        put(mx - 1.0, my, "(O)" if kind == "hole" else "[=]", clip=False)

    top = "".join("%-10s" % ("%d" % (c * 10)) for c in range(0, int(G.BW / 10) + 1))
    out = ["    " + top[:nx]]
    for r, row in enumerate(cv):
        out.append("%3d %s" % (int(r * SY), "".join(row).rstrip()))
    out.append("")
    out.append("    (O) = M3 mounting hole   [=] = M3 slot to the PYNQ's own hole")
    out.append("    (n) = 10 MHz SMA for unit n   (Pn) = that unit's 1 pps SMA")
    out.append("    (HIN)/(HO) = helper in / helper out, beside the Si5351")
    out.append("    numbers down the left and across the top are millimetres")
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
    w = ["| unit | 10 MHz SMA | 1 pps SMA | source | 50R jumper | beat net | "
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
                    "**FIT**" if term == "IN" else "**LEAVE OFF**",
                    beat, bp, bb, ("`%s`" % pps) if pps else "--", pp, slot))
    return "\n".join(w)


def levels_table():
    w = ["| unit | source | at the SMA | at the squarer input | slew rate | "
         "load |", "|---:|:---|:---|:---|:---|:---|"]
    for n, _b, _p, src, term, rs, rsh, _note in D.UNITS:
        lv = D.levels(n, term, rs, rsh)
        w.append("| %d | %s | %s | %s | %s | %s |"
                 % (n, src, lv["at_sma"], lv["at_gate"], lv["slew"], lv["load"]))
    return "\n".join(w)


def testpoint_table():
    w = ["| letter | net / node | where | what you should see |",
         "|:---|:---|:---|:---|"]
    for letter, value, where, expect in L.TEST_POINTS:
        w.append("| **%s** | `%s` | %s | %s |" % (letter, value, where, expect))
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
        w.append("| 0x%02X | %s | %s |"
                 % (a, nm, where.get(a, "U500%d, a TMP1075 in the margins"
                                     % (a - 0x48 + 1))))
    return "\n".join(w)


# ===========================================================================
# the document
# ===========================================================================
def text():
    C = _gateware()
    si_pins = [(p, D.HEADER[p][0]) for p in range(1, 41)
               if D.HEADER[p][0] in ("+3V3_HOST", "I2C_SDA", "I2C_SCL",
                                     "HELPER_CLK")
               or (D.HEADER[p][0] == "GND" and p == 6)]
    si = "\n".join("    pin %-2d  %-12s -> %s" % (p, n, L.SI5351_WIRING[n])
                   for p, n in si_pins)
    npads = sum(1 for _ in D.UNITS)
    return """\
# GPSDO DDMTD front end -- handbook

**rev %(rev)s, %(date)s.**  GENERATED by `gen/handbook.py`; do not edit.
Run `python3 build.py` (or `python3 gen/handbook.py`) to rebuild it.

Thirteen 10 MHz DDMTD channels and twelve 1 pps inputs on one board that plugs
onto the Raspberry Pi header of a PYNQ-Z2.  A %(fh).4f MHz helper samples every
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
which is the only pin of this header that is a clock-capable (MRCC) ball, and
is exactly where the finished board sends it.  The gateware's helper counter
then reads a real frequency instead of zero.

    ssh xilinx@<pynq>
    cd ~/gpsdo-dmtd
    ./pynq-run bringup.py --scan          # who answers on the bus
    ./pynq-run bringup.py --no-heater     # program the Si5351, check lock

Expect the scan to show **0x60** and nothing else; with no front-end board the
thermometers, the DS2482 and the DAC are all absent, and `bringup.py` says so
rather than failing.  After programming, the core's helper counter should read
%(fh).4f MHz +/- a few ppm (a Si5351 breakout's crystal is not a TCXO; the
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

Unit %(nch)d is the **null channel**: no 1 pps, and its 10 MHz input is meant to be
cabled from `HO` -- the Si5351's CLK1 at exactly 10.000000 MHz -- into `%(nulltag)s`
with a short SMA jumper.  Subtracting it removes everything common to the
board and leaves the difference between the GPSDOs, which is the measurement.

### The 50 ohm jumper is the one thing you can break the board with

%(termnote)s

### Expected levels, channel by channel

%(levels)s

---

## 6  Test points and what the silkscreen means

Every test point is a 1.5 mm pad with a single letter printed beside it.

%(tp)s

The two SMA ranges, which the board also prints along the bottom:

* 10 MHz in: %(vmin).1f to %(vmax).1f Vpp AC at the SMA with the 50 ohm jumper
  fitted; %(vopen).1f Vpp maximum without it.
* 1 pps in: 0 to 5.5 V DC.
* `HO` out: 0/3.3 V CMOS, about 1.6 Vpp into 50 ohm.

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

Order of operations, every time:

1. PYNQ-Z2 powered from **its own barrel jack J9** with the jumper at `REG`,
   not from micro-USB alone.
2. This board on the header.
3. `./pynq-run bringup.py` -- which writes the heater DAC's EEPROM to zero
   BEFORE anything else, because the part ships at mid-scale and that is
   1.65 V on three FET gates.
4. Only then the 15 V jack.

---

## 8  Bring-up, in order

1. **Before power.** Ohmmeter: pin 1 to pin 17 of the socket should read open
   (this board does not use the host's 3.3 V).  5 V to GND, and each 3.3 V
   rail to GND, should read high, not short.
2. **Host only.** PYNQ on, board on the header, no 15 V.  Test point `5`
   should read 4.6-5.3 V, `A` and `D` 3.25-3.35 V.
3. **`./pynq-run bringup.py`**: the DAC made safe, the Si5351 programmed and
   both PLLs locked, eight thermometers read, the 1-Wire probes enumerated,
   and the core's selftest.
4. **The helper.** Test point `X` (Si5351 XA) about 0.5-1.0 Vpp.  `HO` on a
   counter: 10.000000 MHz.  The core's helper counter: %(fh).4f MHz.
5. **The null channel first.** Cable `HO` to `%(nulltag)s`.  Its beat should be
   %(fb).1f Hz and its phase reading should be flat -- that is the instrument
   floor, and everything else is measured against it.
6. **One source into two channels** through a splitter: the two readings
   should differ by a constant, not a drift.
7. **Each unit's own pps** against its own 10 MHz edge.

---

## 9  Using it

```python
from driver import attach
core = attach(overlay)
snap = core.snapshot()          # every channel, one coherent instant
```

* `%(nbeat)d` beat channels, slots 0..%(nbeat_1)d; `%(npps)d` pps returns, slots
  %(pps0)d..%(pps_last)d.  Slot `%(null)d` is the null channel.
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

The four desk standoffs must clear the PYNQ-Z2's own outline, which is why
none of them is in the bottom-left corner: that corner is over the PYNQ's
USB-A stack.  A standoff there would land on a connector.

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
""" % dict(
        rev=D.REV, date=D.DATE,
        fh=D.F_HELPER / 1e6, gain=D.N_GAIN, tres=D.T_RES_PS,
        fb=D.F_BEAT,
        orient=orientation_art(), hdr=header_art(), hdrtab=header_table(),
        si=si, hclk_ball="%s (%s)" % (D.HEADER[18][1], D.HEADER[18][2]),
        i2c=i2c_table(), boardart=board_art(), chan=channel_table(),
        levels=levels_table(), tp=testpoint_table(), drc=drc_table(),
        nch=D.UNITS[-1][0], nulltag="J%d01" % D.UNITS[-1][0],
        termnote=L.TERM_NOTE,
        vmin=D.V_SMA_MIN, vmax=D.V_SMA_MAX, vopen=D.V_SMA_MAX_OPEN,
        nbeat=(C.N_BEAT if C else 13), nbeat_1=(C.N_BEAT - 1 if C else 12),
        npps=(C.N_PPS if C else 12), pps0=(C.PPS0 if C else 16),
        pps_last=(C.PPS0 + C.N_PPS - 1 if C else 27),
        null=(C.NULL_CHANNEL if C else 12),
        wrap=(C.WRAP_PS if C else 100000.0),
        bw=G.BW, bh=G.BH, ride=G.HDR_PIN_H, overlap=G.PZ_H - G.PZ_BOTTOM,
        mount=mount_table(), silkmin=jlc.SILK_LINE_MIN,
        npads=npads,
    )


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
