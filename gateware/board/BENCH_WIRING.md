# The GPSDO-PYNQ-Z2 bench: what connects to what

> **From 2026-10-08 the bench runs on the OCXO: see `BENCH_WIRING_OCXO.md`.**
> It replaces sections A, C, D and G below; B, E1, F and H still hold.

Round 44, revised after your reply.  It needs **two solder joints' worth of
work and no more**, and everything else stays connected so that experiments can
run with nobody at the bench.  Each line is one cable or one clip.  The
machine-readable copy is `bench_wiring.csv`; the experiments read it.

Coordinates are the board's own, in mm, from the top-left corner with the board
as `HANDBOOK.md` draws it (207 × 180 mm, debug header J5001 bottom left, the
1-Wire terminals along the top left).

---

## A. Solder these two things, and nothing else

| # | What | Where | Why |
|---|---|---|---|
| A1 | **An SMA on unit 4's 10 MHz jack** (J401), like the four you fitted | right-hand edge, the jack marked `4`, at (164.1, 71.6) | Unit 4 is the one that oscillates at 557 kHz when undriven, the subject of the FB401 rework. With a jack, a source I can switch from here (the 33220A) drives it or leaves it undriven. That gives both of the rework's measurements with no cable moved: does unit 4 still oscillate undriven, and is a squarer without its bead noisier when driven? The second is rev B item 12's downside, and nothing else measures it. |
| A2 | **One 3-pin terminal block, J6001** ("PROBE 1") | top-left corner: pin 1 at (16.0, 8.0), the rounded-square pad; pins 2 and 3 at 12.5 and 9.0, going left | the external temperature probe. All five terminals share one 1-Wire bus, so J6001 is as good as any. |

**The probe's wires into J6001** (DROK DS18B20; colours from the DROK
photographs, as the schematic has them):

| J6001 pin | Signal | Wire |
|---|---|---|
| 1 (rounded-square pad) | DAT, to the 1-Wire bus through 47 Ω | **yellow** |
| 2 | VCC, +3V3_D through 47 Ω | **red** |
| 3 | GND | **black** |

**Not needed:** unit 4's pps jack, SMAs on other units, and the ten soldered test
leads of this file's first version. What those leads would have shown, I get
from the FPGA's own counts (unit 4's oscillation), from five minutes with a
hand-held probe (F4), or from a one-time DMM reading (F1).

## B. Power, network and console

| # | Connect | Notes |
|---|---|---|
| B1 | The board onto the PYNQ's Raspberry Pi header | as before |
| B2 | The PYNQ's **barrel jack** to its own supply | not USB power: the board draws ~230 mA from it |
| B3 | Nothing on the board's `BENCH +5V` posts (J2001/J2002) | the boot hiccup of round 43 |
| B4 | PYNQ Ethernet to the lab switch | it was 192.168.8.156; its address changes at each boot until its MAC is pinned (round 43) |
| B5 | PYNQ micro-USB (PROG/UART) to the laptop | its console, if SSH ever fails |
| B6 | Nothing on `15V 1A DC IN` (J2003) | the heaters stay off |

## C. The 10 MHz sources

Put a **BNC tee directly on the scope input**. One cable runs from the source to
the tee, and a second from the tee to the board's SMA (BNC-to-SMA).

| # | Source | Tee on | Board jack | Jumper on that unit |
|---|---|---|---|---|
| C1 | SDG1032X **output 1** (front) | scope **CH1** | `1` (unit 1) | JP101 **fitted** |
| C2 | SDG1032X **output 2** (front) | scope **CH2** | `2` (unit 2) | JP201 **off** (as now) |
| C3 | Agilent 33220A **OUTPUT** (front) | scope **CH4** | `4` (unit 4, the new jack) | JP401 **fitted** |
| C4 | HP 33120A **OUTPUT** (front) | no tee | `11` (unit 11) | JP1101 **fitted** |
| C5 | The board's **`HO`** (J3001, "CLK1 OUT") | scope **CH3** | `12` (unit 12) | JP1201 **fitted** |
| C6 | ~~SDG1032X rear **10MHz In/Out**~~ **the BG7TBL OCXO distribution amplifier** (from Oct 8, C7) | | HP 33120A rear **10 MHz In** (and a 33220A's, if it has Option 001) | |
| C7 | **BG7TBL OCXO**, one port each | | SDG rear `10MHz In/Out` **through a 50 Ω feed-through or 6 dB pad**; HP 33120A rear `10 MHz In` **direct** | (board units: see C7 below) |

- **C3, the 33220A.** It has an output switch, so it is the source I can turn
  off to leave unit 4 undriven. Switch it on, and leave it on the LAN; it was
  192.168.8.240.
  - **This one (MY44054664) has no Option 001**: no rear 10 MHz jacks, so C6
    cannot lock it.
  - It free-runs **18.1 ppm low** against the SDG: unit 4 beats at about
    1428 Hz, not 1243 (round 45). That is within its ±20 ppm one-year spec.
- **C4, the HP 33120A.** It goes back on unit 11, as in rounds 40-43, over the
  GPIB adapter it already uses.
- **C6** locks the HP 33120A to the SDG, so units 1, 2 and 11 share one
  clock. A 33220A with Option 001, teed in, would bring unit 4 in too.
  - It needs **Option 001** on the 33220A: are there `10 MHz In` and `10 MHz
    Out` jacks on its rear panel? Without them it cannot be locked at all.
  - **The HP 33120A has Option 001** (`*OPT?` answers `1:PLL`), and it **locks
    to the SDG**. Round 44 tested it with the HP on the SDG's rear output:
    - free-running, it drifted 0.24 ppm against the SDG's own output;
    - locked, first 2.5 ppb, the same fraction at 10 kHz and at 1 MHz, with
      the phase scatter 40 times smaller; an hour later ≤ 0.001 ppb (below).
  - Tee the SDG's rear output to both rear inputs to lock both.
  - **Until Oct 8 the SDG's `10MHz In/Out` was set to output on its panel**:
    Utility, Page 1/2, Clock, 10MOut, Enable.
    - `ROSC 10MOUT,ON` over SCPI is ignored by this firmware, and `ROSC?`
      doesn't report the state.
    - **Oct 8: 10MOut is now Disable** (Source still Internal), so the jack is
      an input, ready for C7. The HP 33120A free-runs until C7 is plugged in.
  - **What locking buys, measured** (round 44):
    - anything on the rear output locks to it: the HP to 0.006 ppb, with
      ~0.5 ns of phase wander;
    - the SDG's *own* outputs **are not always coherent** with that rear
      output, for a reason not yet known:
      - 13:20-13:45 PDT, Oct 6: they ran **2.53 ppb low** against it, three
        times by two methods (scope tee, and the HP locked to it);
      - 14:40-14:55: they agreed with it **to ≤ 0.001 ppb**, by the board's
        DDMTD (unit 1 against unit 11). That held in five settings, the
        earlier ones among them.
    - So the locked generators (units 4 and 11) are coherent with each other,
      and units 1 and 2 with each other. Between the groups, expect anywhere
      from 0 to 2.5 ns/s at 10 MHz. A run with units 1 and 11 shows which;
      G0 found 0.
    - `lab-instrument-control` (`siglent.md`, `hp.md`) has the numbers.
- **C7, the OCXO (round 45.17).** A BG7TBL 8-port distribution amplifier
  becomes the bench's one reference. Every instrument only *takes* 10 MHz:
  SDG 10MOut Disable, SDS `:SYSTem:CLOCk IN_OFF` (it was `IN_ON`).
  - **Measured (round 45.18), ports 1-3 on SDS CH1-CH3, each channel at 1 MΩ
    and then 50 Ω:**

    | Port | 1 MΩ | 50 Ω | Source | Phase vs port 1 |
    |---|---|---|---|---|
    | 1 | 6.03 Vpp | 3.53 Vpp | 35 Ω | — |
    | 2 | 5.70 | 3.42 | 33 Ω | −0.4° |
    | 3 | 5.75 | 3.39 | 35 Ω | **180.0°** |

    - **The source is ~35 Ω, not 50 Ω**, so a port gives **3.4-3.5 Vpp into
      50 Ω, +14.7 dBm**, not the 3 Vpp first estimated from 6 Vpp.
    - Harmonics ≥ 51 dB down (the scope's own floor). Ports differ by up to
      0.5 dB, which matters for AM-to-PM (item 18) if a port's level drifts.
  - **Your note: ports 1, 2, 5, 6 are 180° from ports 3, 4, 7, 8.** Port 3
    against ports 1 and 2 confirms it; 4-8 not yet looked at. It doesn't matter
    to anything that locks (a PLL takes any phase), and on the board it is a
    50 ns offset, which a pair series reads mod 100 ns. Use one bank where the
    phase is compared.
  - Where each port may go:

    | Into | What it sees from one port | Verdict |
    |---|---|---|
    | HP 33120A `10 MHz In` (50 Ω, −10..+15 dBm, abs max +25 dBm / 10 Vpp) | 3.5 Vpp, +14.9 dBm | **direct**: inside the range, at its top; a 3 dB pad puts it mid-range. The bottom HP locks on it (45.18) |
    | SDG `10MHz In/Out` (≥ 1.4 Vpp, 5 kΩ, AC; no max given) | 6 Vpp unterminated | **through a 50 Ω feed-through or 6 dB pad**: 3.5 or ~1.8 Vpp |
    | a board unit **with** its 50R jumper (JP101, JP401, JP1101, JP1201) | ~3.5 Vpp | under the 4.10 Vpp abs max but over the 3.3 Vpp rating: **through a 3 dB pad** (~2.5 Vpp) |
    | a board unit **without** it (JP201 unit 2, JP901 unit 9 now) | ~6 Vpp | **No**: over the 4.10 Vpp abs max. Fit the jumper, and a pad |
    | a scope channel, 1 MΩ / 50 Ω | 6 / 3.5 Vpp | OK (50 Ω: ≤ 5 Vrms) |
    | the 33220A | — | no `10 MHz In` (no Option 001) |
    | the SDS2104X Plus | — | **no 10 MHz jack** (you looked: front WaveGen out; rear Ext trig, pass/fail) |

  - **Then:** I choose External on the SDG (it refuses with no signal on the
    jack). The HPs lock by themselves.
- **Nothing on** `HIN` (J3002) or the pps jacks.
- **I set all the amplitudes** (`bench_setup.py on`): 10 MHz sines at **3.3 Vpp
  open circuit**.
  - That is ~1.65 Vpp at a unit with its 50R jumper fitted, and ~2.9 Vpp at
    one without.
  - 3.3 Vpp is the rating of an unterminated input, so no jumper state can
    overdrive one.
  - Until round 43 it was 4 Vpp.

### Locking to the board itself?

**Out of the board: `HO` is its only 10 MHz output.**

- It is the Si5351's CLK1, made from the board's own 25 MHz TCXO. It is 0/3.3 V
  CMOS, ~1.6 Vpp into 50 Ω.
- The TCXO free-runs: it was about 0.4 ppm high in round 40. The board is a
  measurement front end; the "GPSDO" in its name is what it measures.
- You *could* lock the SDG to it. Tee `HO` into the SDG's rear `10MHz In/Out`
  with the SDG set to External: it wants ≥ 1.4 Vpp, into 5 kΩ, AC coupled. A
  second tee would take it to the 33220A's `10 MHz In`.
  - Every source would then be coherent with the helper, with none of the
    Siglent's wander against it (round 40: 15 % of a beat period in 0.2 s).
  - But `HO` is the board's largest aggressor (round 41: 58 ps), and this
    hangs more cable on it.
  - Not for now; perhaps later, as an experiment of its own.

**Into the board: there is no 10 MHz input on rev A.**

- The Si5351A takes its reference only from the TCXO, through XA.
- `HIN` (J3002) replaces the *helper*, not the reference, and only after its
  rework (R3004 in, R3005 out).
- Rev B's Si5351C could add one: CLKIN can take an external 10 MHz instead of
  the TCXO. That is now an option in `REVB_CHANGES.md` item 9.

## D. The Siglent scope

| Channel | What | Settings (I set them) |
|---|---|---|
| CH1 | the tee of C1 (output 1, unit 1) | 1 MΩ, DC, 1×, 1 V/div |
| CH2 | the tee of C2 (output 2, unit 2) | same |
| CH3 | the tee of C5 (`HO`, unit 12) | same |
| CH4 | the tee of C3 (33220A, unit 4) | same |

**Never set a channel to 50 Ω while it sits on a tee to the board**: it would
load the line and halve what the board receives.  The PP215 10× probe stays in
the drawer except for F2 and F4.

## E. The CircuitGears: no soldering

**E1. The three rails at the debug header J5001.** Its pins are 2.54 mm posts:

- 1 = +5V_HDR;
- 5 = +3V3_A (the far end of the analog rail, 109 mV below the LDO in
  round 41);
- 7 = +3V3_D;
- every even pin is GND.

Use BNC-to-grabber (or BNC-to-Dupont) leads, 1×, with each ground clipped to the
even pin beside its signal.

| # | CircuitGear | Ch | Node | Pin | Ground |
|---|---|---|---|---|---|
| E1a | CG-1 | A | +5V_HDR | J5001 pin 1 | J5001 pin 2 |
| E1b | CG-1 | B | +3V3_A, far end | J5001 pin 5 | J5001 pin 6 |
| E1c | CG-2 | A | +3V3_D | J5001 pin 7 | J5001 pin 8 |

**DMM check (round 45).** Against Jason's DMM, the CircuitGears read about
2 % low at DC. +3V3_A is 3.185 V, which CG-1 B reads as 3.093 V; +3V3_D is
3.296 V, which CG-2 A reads as 3.238 V once zeroed. Scale the logged rails
by 1.0296 and 1.0178 (README 45.10).

**E2. Your two bonus connections (round 45).**

| # | from | to | notes |
|---|---|---|---|
| E2a | CG-1's generator | `P2` (unit 2's pps jack) | teed to CG-2's input B |
| E2b | CG-2's generator | `9` (unit 9's 10 MHz jack, which has an SMA) | JP901 off: no 50 Ω |

**The pps inputs are not terminated.**

- Each pps jack's 51 Ω (R206, R406, ...) is DNP. The input is 1 kΩ into
  10 kΩ to ground, then a 74LVC1G17 Schmitt.
- Round 44 said this was a fixed 51 Ω. That was wrong, and the CircuitGear
  does drive it:
  - a 0-3 V square counts one edge per period;
  - the 10 ns stamps give its period, 1.0225951 s for a set 0.9779 Hz;
  - its thresholds, measured through the jack, are **1.88-1.98 V rising**
    and **1.27-1.37 V falling**.
  - That is ≈1.75 V and ≈1.20 V at the gate, inside the datasheet's
    1.48-2.08 V and 0.89-1.35 V at 3.0-3.3 V.

**CG-2 on unit 9: an aggressor, not a channel.**

- Its DDS 10 MHz doesn't square cleanly (fold concentration 13-35%,
  against 70-80% for the other units).
- While it runs, every other unit's beat chatters more. At 1-2.8 Vpp, units
  1, 2 and 11 dropped from 72-81% to 59-65%, and a 1 kHz tone took two of
  them to 38-45%.
- The pair differences stayed clean (unit 2 − unit 1: 32 ps rms either way),
  so it is common mode.
- Keep its generator **off** except as G6's aggressor.

**USB.** The CircuitGears go through a **powered** hub to this laptop. Plug in
the two you use, and tell me which serial number is CG-1 and which CG-2:

- `python3 ~/lab-instrument-control/syscomp_circuit_gear/syscomp_circuit_gear.py list`
  prints the serials;
- or plug them in one at a time, in order, 10 s apart, and I will read the
  order from the kernel log.

## F. Hand tests, while you are here (about 15 minutes)

**F1. The rail, once, with the DMM.** Black on any J5001 even pin; note the time:

1. J5001 pins 1, 5 and 7;
2. test point `A` (TP2002, at (118.5, 9.9));
3. the rail-side pads of FB101 (64.2, 37.2), FB1101 (64.2, 126.2), FB201
   (142.8, 61.5) and FB1001 (142.8, 132.7).

That is round 42's test 1. It also calibrates the CircuitGears of E1 at their
working voltages, since I log them at the same moment.

**F2. `X` and the TCXO**, with the PP215 10× probe on scope CH3:

1. Move CH3's cable from the C5 tee to the probe, and set CH3 to 10× on the
   scope.
2. Hold the tip on `X` (TP3001, at (103.9, 49.4)) for **2 minutes**, with the
   ground spring on R3002's ground pad (97.2, 49.4).
3. Then hold it on the TCXO output (R3001's upper pad, (101.2, 46.1)) for
   2 minutes, on the same ground pad.
4. Put CH3 back on the C5 tee, at 1×.

I will have a slip watch and the scope logger running; the logger records the
exact times.

**F3. The temperature probe.** Screw it into J6001 (A2). Nothing else; I read
it. `./pynq-run bringup.py --no-si5351 --no-heater` on the PYNQ shows the same
thing: "presence yes", "1 probe(s)", its 64-bit ROM code and its temperature.
Hold the probe and it should climb toward 30 °C.

**F4 (optional, 5 minutes). Unit 4's oscillation, by hand**, on CH3 as in F2,
about 1 µs/div, AC coupled. Do it with the 33220A switched off, which I do from
here; say when. Hold about 30 s on each of:

- U401 pin 4 (the squarer's output), at (142.8, 70.6);
- C402 pad 1 (its supply after the bead), at (140.8, 74.5);
- FB401's rail-side pad (142.8, 79.3).

This is round 41's open question: which node carries the 557 kHz.

**F5.** Tell me the wiring is done, whether C6 is in, and the CircuitGear
serials.

## G. What I then run on my own, in order

| # | What | Result |
|---|---|---|
| G0 | **The wiring check.** Every instrument answers; units 1, 2, 4 (33220A on), 11 and 12 beat; the scope sees all four signals; the CircuitGears read their rails; the probe answers. Nothing is changed. | pass or mismatch, line by line |
| G1 | `bench_setup.py on`, scope settings, `bringup.py --inputs 1,2,4,11,12` | the standard state |
| G2 | **The before-rework battery.** `bench.sh before` with unit 4 undriven (33220A off), then units 2 and 4 recorded with unit 4 driven. | round 42's 42.4 test 5, and unit 4 as a live channel |
| G3 | **The rails against each source.** Each source off and on in turn; HO off and on; CLK0 at 2 and 4 mA. | the step at each rail: each squarer's current, driven and undriven |
| G4 | **Unit 4's oscillation.** `unplugged.py` restarts with the 33220A off, and its duty and rate. | the FB401 baseline in this wiring |
| G5 | `xcheck.py` steps and ramp on units 1-2; AM-to-PM on units 1, 2 and 4, each against the scope | item 18's numbers per unit and per termination |
| G6 | **Crosstalk.** The 33220A offset by Δ on unit 4; the HP on unit 11; HO off, on and at each drive. | the crosstalk matrix of item 13 |
| G7 | **Overnight.** Unit pairs, slips (pair register and `HO`'s beat), the board's eight thermometers and the probe, and the rails, once a minute. | channel delay against temperature and supply |

**Where they stand (Oct 6, README round 45):**

- **G0** passed once +3V3_D moved one pin.
- **G1** is G2's bring-up.
- **G2** is done: `logs/before_20261006T2325Z/` on the PYNQ, and the 60 s with
  unit 4 driven.
- **G4's baseline** is in G2: unit 4 oscillates 30 times in 30, at 560 kHz.
- **G6** has begun: channels on different frequencies make one another
  chatter (45.4, 45.5).
- **G7** runs overnight (`overnight.py`).
- **G3, G5 and the rest of G6** are next.

Then the reworks, which need your hands and come after G2-G4:

1. FB401 bridged;
2. R3001 → 1k and R3002 → 330 Ω;
3. perhaps `HIN`.

Each is followed by the same G-tests.

## H. Don'ts

- Don't set a scope channel on a tee to 50 Ω.
- **Don't run `lab-instrument-control`'s hardware tests (`test_siglent.py`) with
  this wiring.** They drive SDG output 1, here unit 1, with DC and kHz test
  signals, and switch outputs on and off. That is harmless to the board, but
  it ruins any run in progress.
- Don't connect the bench 5 V supply to the board.
- Don't feed `HIN` before its rework: it ends in 51 Ω and goes nowhere.
