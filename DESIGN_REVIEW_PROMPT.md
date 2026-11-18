# Design review wanted: a 13-channel digital DMTD front end

**You are being asked to try to break this design.**  It has been through
twenty-four rounds of self-review by its author and one LLM, which means the
obvious faults are gone and the remaining ones are the kind that survive
self-review: assumptions everybody in the room already agreed with.  A fresh
reader who is willing to be blunt is worth more here than another careful pass
by the same eyes.

Please be opinionated.  "This whole approach is wrong because X" is a more
useful review than twenty notes about silkscreen.  If you think the
architecture is misconceived, say so and say what you would do instead.  If
you think it is fine, say which parts you actually checked, because a review
that approves everything is indistinguishable from one that read nothing.

Nothing has been fabricated.  Changing any of it costs only time.

---

## 1. The problem

Harvey Mudd has accumulated about thirteen GPS-disciplined oscillators — an
HP 10811B, a rubidium FE-5680A, two u-blox ZED-F9T timing receivers, several
Leo Bodnar units, some Chinese GPSDOs of varying provenance — and nobody knows
how good any of them actually are.  Each emits a 10 MHz sine or CMOS square and
a 1 pps edge.  The question is how their phase and frequency compare to one
another over seconds to weeks, at a resolution good enough to see the
differences between them.

A counter that timestamps 10 MHz zero crossings directly needs picosecond
resolution to be interesting.  Commercial instruments that do this cost more
than the entire oscillator collection.

## 2. The chosen answer: a digital dual-mixer time difference (DDMTD)

Sample each 10 MHz reference with a **helper clock** at a deliberately close
frequency, and the phase difference appears stretched in time by a large
factor.  Concretely, on this board:

| | |
|---|---|
| signal | 10.000 000 0 MHz |
| helper | **10.001 234 4 MHz** |
| beat | **1234.4 Hz** (810 µs period) |
| gain N = f<sub>helper</sub>/(f<sub>helper</sub> − f<sub>signal</sub>) | **8101** |
| single-shot resolution, one helper period / N | **12.3 ps** |

A single helper clock feeds **all thirteen channels**.  That is the whole
trick: the helper's own phase noise is common to every channel and cancels in
the channel-to-channel difference, so the measurement can be far better than
the helper is.  What leaves the board is thirteen ~1.2 kHz square waves whose
*edge times* carry the answer, plus twelve 1 pps returns, into an FPGA that
timestamps them.

**Ask hard questions about this section.**  Everything downstream is
consequence.

## 3. Architecture

### One channel (×13)

```
SMA ─┬─ 51R (DNP on 12 of 13, jumper-selectable on the 10 MHz path)
     ├─ 2k2 shunt (defines the DC level, bounds current from a CMOS source)
     └─ 10n C0G ─ 330R ─┬─ 74LVC1GU04, self-biased by 1M   ← the "squarer"
                        └─ BAV99 rail clamp (DNP)
                              │  0/3.3 V CMOS at 10 MHz
                              ▼
                         74LVC1G80  D-flip-flop,  CLK = HELPER   (FF1)
                              │      deliberately allowed to go metastable
                              ▼
                         74LVC1G80  D-flip-flop,  CLK = HELPER   (FF2, retimer)
                              │
                              └──► BEAT_n  to the FPGA   (~1.2 kHz)

1 pps ─ 51R (DNP) ─ 1k ─ 74LVC1G17 Schmitt ──► PPS_n to the FPGA
```

### The helper

```
Fox FT5H TCXO 25 MHz ─ 3k3/1k divider ─ Si5351A ─ CLK0 ─ squarer ─ fan-out tree
  ±2.5 ppm                (0.77 Vpp)     PLL              1G34 ×5   13 branches
```

The Si5351 is programmed over I²C at every power-up: PLL feedback
32 + 4142/1048575, MultiSynth 80 in integer mode, R = 1.  The fan-out buffers
are **clustered together thermally** rather than spread next to the channels
they feed — a buffer's threshold moves 5–10 ps/°C, against 0.7 ps per 100 mm
per 10 °C for the trace, so keeping them at one temperature beats shortening
the branches.  The long runs are buried on In2.Cu as stripline between two
ground planes.

### Housekeeping

Eight TMP1075 thermometers across the board, a 24-resistor distributed heater
(9.6 W, 560 Ω each, three SOT-223 pass FETs in **linear** not PWM drive), an
MCP4725 DAC for the heater setpoint, a DS2482-100 1-Wire bridge and five screw
terminals for DS18B20 probes.  The thermal loop is Python on the host, ~5 min
time constant, ~34 °C setpoint.

### Host

A **PYNQ-Z2** (Zynq-7020) via its Raspberry Pi 40-pin header.  The board is a
mezzanine that sits 8 mm above it on the header pins and overhangs on all
sides.  It draws ~110 mA at 5 V from the header; the heater has its own 15 V
barrel jack.

## 4. What the host forces on the design

These are facts about the PYNQ-Z2, verified against the TUL schematic R12 and
the Reference Manual v1.0 — not assumptions:

* **Every Raspberry Pi GPIO has a 200 Ω series resistor** to the FPGA ball.
  Unavoidable, and it slows the helper edge presented to the FPGA to ~4.4 ns.
* **2.2 kΩ pull-ups are already fitted** on the I²C pins, so this board fits
  none.
* **The header has 28 usable I/O and 8 of them are shared with Pmod A.**  This
  design uses all 28 — 13 beats + 12 pps + helper + 2 I²C — so **Pmod A becomes
  unusable**.  Pmod B and the Arduino headers are untouched.
* **Only header pin 18 is clock-capable** on both the PYNQ-Z2 and the Icepi
  Zero, so the helper clock is nailed to it by an assertion in the source.
* An **unpowered** Zynq I/O pin is absolute-max 0.55 V, so bench-powering this
  board with the host off drives 3.3 V into 26 of them.

## 5. The physical board

207 × 180 mm, 4 layers, 590 parts.  F.Cu components and routing, **In1.Cu solid
ground**, **In2.Cu helper distribution as stripline**, **B.Cu solid ground**,
plus a ground pour on F.Cu.  Thirteen channel tiles in two columns pointing at
a helper spine on the centre line; SMAs on the outer edges; the Raspberry Pi
socket on the **bottom** side in the 11 mm strip that overlaps the host.

Current state: **ERC 0, DRC 0 unfilled, DRC 0 filled, 0 unconnected,
0 silkscreen markings on pads.**

## 6. How the project is built — this is unusual and deserves its own scrutiny

**There is no hand-drawn schematic and no hand-placed layout.**  Everything is
generated by ~9 000 lines of Python: `gen/` emits the nineteen KiCad schematic
sheets from `gen/design.py`, and `pcb/` places every part and routes every
track with a purpose-built maze router.  One command rebuilds the lot:

```bash
python3 build.py --clean          # deletes 28 generated paths, rebuilds all
python3 build.py --no-pcb         # everything except the router: ~9 seconds
python3 build.py --list           # what is source, what is product
```

Verified: deleting every generated file and rebuilding produces a
**bit-for-bit identical** `.kicad_pcb` in 19.5 minutes.

```
gen/design.py ──► gen/gen.py ──► *.kicad_sch ──► (kicad-cli) ──► netlist
                                                                    │
                          pcb/*.py ──► pcb/build_pcb.py ◄───────────┘
                                            │
                                     GPSDO-PYNQ-Z2.kicad_pcb
                                            │
                          mfg/*.py ──► mfg/release/  (Gerbers, BOM, CPL, prices)
```

**This is a deliberate and arguable choice.**  It buys reproducibility, review
by `git diff`, and design rules expressed as code rather than as clicks.  It
costs the ability to nudge one part in the GUI, and it means a reviewer must
read Python to understand why the board looks the way it does.  Tell us if you
think that trade is wrong.

## 7. What I would attack first

Ordered by how much it would cost to be wrong.  These are the author's own
least-confident points, stated plainly so you do not have to find them.

1. **The gateware exists; the I²C half of it does not.**  *(Updated: this
   section previously said there was no gateware at all.  There now is --
   `gateware/`, built entirely from TCL, closing timing at WNS +1.3 ns, with a
   47-check testbench and a PYNQ driver.  What follows is what is still
   missing and what is still worth attacking.)*

   **Nothing drives the I²C bus.**  `axi_iic` is in the overlay at
   `0x4160_0000` and answers, but no code programs the Si5351, reads the eight
   thermometers, sets the DAC or talks to the 1-Wire bridge.  **The Si5351 is
   the blocker**: it generates the helper, and until it is programmed to
   10.0012344 MHz there are no beats at all and every channel reads zero.

   **Nothing has ever been plugged in.**  The gateware is verified in
   simulation and on a bare board.  No beat edge from real hardware has ever
   reached it.

   The original question still stands and is still the expensive one to get
   wrong: **does the pin assignment actually support the gateware?**  Thirteen
   asynchronous ~1.2 kHz edges and twelve 1 pps edges arrive on ordinary I/O,
   with only one clock-capable input for the helper.  The gateware as written
   needs exactly that and no more -- the helper is the only clock, everything
   else is a false-path input into a synchroniser -- so the answer appears to
   be yes.  But it is worth a second opinion before fabrication.

2. **The squarer is a self-biased unbuffered inverter (74LVC1GU04), not a
   comparator.**  This is the single most consequential component choice on the
   board: its switching threshold *is* the measurement's zero-crossing
   reference.  The argument for it is that all fourteen share one rail so
   threshold drift is common-mode and cancels; the argument against is that a
   real comparator (LTC6957, ADCMP600) has a defined, supply-independent
   threshold and far better power-supply rejection.  **Is the common-mode
   argument good enough, or is this the thing that limits the instrument?**

3. **FF1 is deliberately allowed to go metastable**, and FF2 retimes on the next
   helper edge.  The claim is that the metastable window *is* the measurement
   and that a synchroniser in front of FF1 would destroy it.  **Is the
   two-flop arrangement right?  Does FF2 quantise away information you wanted?
   What does the '1G80's metastability window actually do to the 12.3 ps
   figure?**

4. **Phase is measured modulo one 10 MHz cycle.**  The beat wraps every 810 µs,
   which is exactly 100 ns of input phase.  The intent is that the 1 pps
   channels resolve the coarse ambiguity.  **Does that actually work across a
   power cycle, a dropped beat edge, or a channel whose pps is missing?**
   Unit 13 has no pps at all.  It is the **null channel**: an ordinary channel
   whose input SMA you cable to J3001, the board's own CLK1 OUT jack.  CLK1 and
   the helper CLK0 come from the same Si5351 PLL, so their difference is exact
   and that channel's beat measures nothing but this board's own front-end
   noise.  (Reviewing this document turned up that `design.py` described the
   null source as "selected by JP_NULL"; **there is no JP_NULL** anywhere on
   the board.  The comment is now fixed.  Treat it as a sample of how much to
   trust the other comments.)

5. **The thermal design.**  9.6 W spread over 207 × 180 mm, 24 heaters, a
   ~50 mm spreading length, and a claim that heating only from the perimeter
   would leave the middle at 34 % of the edge rise — hence thirteen heaters
   *inside* the tiles.  Three SOT-223 pass FETs dissipate 0.8 W each in linear
   mode and rise ~50 °C, hotter than any heater resistor.  **Is the spreading
   model right?  Is a heated board the right answer at all, versus accepting
   ambient drift and calibrating it out?**

6. **Every signal is single-ended** and every threshold is a CMOS input.  No
   differential anything.  For a picosecond-class instrument that is a
   choice, not an oversight — but it is a choice.

7. **The beat frequency is 1234.4 Hz.**  Chosen to sit away from the 60 Hz
   harmonic comb: the 20th harmonic is at 1200 Hz (34.4 Hz below) and the 21st
   at 1260 Hz (**25.6 Hz above**).  **Is 25.6 Hz enough separation given the
   ~1 Hz measurement bandwidth and whatever sidebands the Si5351's fractional
   PLL puts on the helper?**  Note the helper is generated by a *fractional*
   MultiSynth division, which is exactly the configuration that produces
   close-in spurs.

8. **The generator-driven build.**  See §6.  Also: the maze router is
   home-grown.  The board passes DRC and has zero unconnected, but "passes DRC"
   is not "well routed".  **Look at the actual copper.**

9. **The manufacturing package.**  CPL rotations are emitted in KiCad's native
   convention with **no per-package correction applied**, because no vetted
   correction table was available; assembly drawings are provided instead.
   **Is that acceptable, or should specific packages be corrected?**  SOT-23-5
   (59 placements), SOT-223 and the SOIC-8s are the ones that would bite.

## 8. Known open items (do not spend time rediscovering these)

* **TMP1075 bypass distance is 7.0 mm**, against TI's "as close as possible",
  which they tie to *precision*.  Not fixed: the stack geometry is what made
  the thermometers routable at all.  All eight are geometric copies, so any
  resulting offset is common.  Suspect this first if the thermometers disagree
  by more than their own 0.25 °C.
* **369 reference designators sit on pads** in the silkscreen.  Normal at this
  density; the fab clips them.  Fixable on request.
* The routing grid and the analytic clearance checks do not yet agree, so the
  stricter via check is opt-in rather than default.
* Some ground pads have no via of their own and rely on the F.Cu pour.
* The DAC's EEPROM should be programmed to `PD=01`, data 0 at bring-up, with a
  General Call Reset, so the heater cannot come up full-on.

## 9. What has already been verified, but is important enough to re-check

Every IC pinout against the manufacturer datasheet **and** cross-checked
against the stock KiCad libraries; all 40 header pads against a model of the
PYNQ derived from photographs, to 0.000000 mm; every I²C address; every
channel's input headroom in both jumper positions; the power path node by node;
the heater's power budget; and the digital/analogue separation measured on the
finished board (6.08 mm minimum same-layer from any channel front end to any
helper copper, 78 % of the helper buried between ground planes).

Three real faults were found and fixed in review, which may calibrate how much
to trust the rest: **two devices at I²C address 0x60** (the Si5351A in MSOP-10
has no A0 pin and is permanently 0x60; the MCP4725A0 with A0 grounded is also
0x60 — a dead bus); **a power symbol landing on a wire shorted I²C_SCL to the
3.3 V rail** and passed ERC and three existing checks; and **a SOT-223's centre
lead was connected to nothing** because KiCad does not join two pads that share
a pad number without copper between them.

## 10. How to look at it

```bash
git clone <this repo> && cd GPSDO-PYNQ-Z2
python3 build.py --no-pcb        # schematic + all checks, ~9 s
kicad GPSDO-PYNQ-Z2.kicad_pro    # or just open the .kicad_sch / .kicad_pcb
```

* `gen/design.py` — the design in one file: frequencies, the thirteen sources,
  the header map.  **Start here.**
* `gen/sheet_unit.py` — one channel, with the reasoning in the notes that get
  plotted onto the sheet.
* `pcb/geom.py` — the floorplan and the PYNQ's measured geometry.
* `pcb/build_pcb.py` — placement and routing.  Long, and heavily commented
  with *why*, including several "this was tried and it failed because…".
* `mfg/release/` — what would be uploaded: Gerbers, BOM, CPL, assembly
  drawings, and an annotated BOM with live prices and stock.
* `datasheets/` — every datasheet cited anywhere. Nothing was taken from a web
  search result that is not in this folder.
* The full design history, including every decision and every mistake, is in
  `README.md` beside this file — 9 700 lines, twenty-seven rounds.  You are not
  expected to read it, but if you want to know why something is the way it is,
  the answer is in there.  (It lived in the DroneSDR repository as
  `GPSDO-comparison/GPSDO-DMTD-PCB.md` until 2026-09-13.)

## 11. What would be most useful back

* A verdict on §7.1 and §7.2 — the missing I²C/Si5351 software and the squarer choice —
  even if it is one paragraph each.
* Anything in the schematic that is simply wrong.  It has been checked hard,
  but by people who already believed it.
* An opinion on whether a 207 × 180 mm four-layer board with 590 parts is a
  sensible way to answer this question.
* Disagreement with the build methodology, if you have it.
* Anything you would refuse to sign off on before spending the money.

Assume nothing is sacred.  The board has not been fabricated, the author is not
attached to any of it, and "start over" is an acceptable conclusion if you can
say why.
