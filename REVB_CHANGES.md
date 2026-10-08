# Rev B changes

Everything planned for the next JLCPCB order, collected in one place so it is
applied **all at once**.

**Brought up to date 2026-10-07** (README round 45). It uses everything
measured on the rev A bench board from 2026-09-30 to 2026-10-07: two nights
of logging, a crosstalk matrix, AM-to-PM, and three reworks.

## Revisions

| rev | state | what it is | where |
|---|---|---|---|
| **A** | **LOCKED** 2026-09-15 | the two boards JLCPCB built | git tag `GPSDO-PYNQ-Z2-revA` (commit `0f9a4dd`, pushed to origin), and `GPSDO-PYNQ-Z2-revA.zip` |
| **B** | open | all work since: this list | the working tree; `gen/design.py` has `REV = "B"`, `DATE = "unreleased"` |

- **Rev A.** Round 42 re-checked the archive: all 58 of its SHA-256 sums
  hold, and its 57 design files are byte-identical to the tag.
- **The committed `GPSDO-PYNQ-Z2.kicad_pcb`, the schematics and
  `mfg/release/`** are still rev A's files until rev B's board is built.
  `HANDBOOK.md` already says rev B, and says the bench boards are rev A.

### Locking rev B

Do this on the day it is ordered:

1. Set `DATE` in `gen/design.py` to the order date, then run
   `python3 build.py`.
   - Until `DATE` is a date, `mfg/build_release.py` stamps the release
     **DRAFT -- NOT FOR UPLOAD** (exit 3). `build.py` carries on past it.
   - Once `DATE` is a date, it fails any board whose silkscreen does not
     print that revision and date.
2. Upload exactly what `mfg/release/` holds. Note anything JLCPCB changes
   in their review.
3. Commit, then `git tag -a GPSDO-PYNQ-Z2-revB`, and push the tag.
4. Archive `GPSDO-PYNQ-Z2-revB.zip` the way rev A was: the project,
   `mfg/release/`, the handbook, the README and `SHA256SUMS.txt`.
5. Set `REV = "C"`, `DATE = "unreleased"`, and start `REVC_CHANGES.md`.

## The plan at a glance

Priority: **1** = don't order rev B without it; **2** = should be in rev B;
**3** = worth it if it fits.

| # | item | status | pri. | what rev A showed | rev B |
|---|---|---|---|---|---|
| 1 | Designators inside their own box | IN GENERATOR | 2 | 71 outside on rev A (r41) | the placer refuses; `check_silk_boxes.py` |
| 2 | Jumper designators beside the jumper | IN GENERATOR | 3 | | |
| 3 | 1-Wire colours and signals at each screw | PLANNED | 2 | `red` printed nearer GND than VCC (r45) | Jason's layout |
| 4 | A squarer-output test point | merged into 19 | | | |
| 5 | **A real +3V3_A plane** | PLANNED | **1** | 109 mV lost in tracks (r41). **A neighbour going driven ↔ undriven moves a channel 1.4-1.9 ps** (r45 T1). | inner-layer plane, one feed |
| 6 | Rail LEDs with "in range" | PLANNED | 3 | | TPS3700 windows |
| 7 | Rail monitor (INA3221) | PLANNED | 2 | Rails flat to 1 mV; the CircuitGears read 1-2% low and drift (r45) | on-board V and I logging |
| 8 | A lower-current squarer (74AUP) | **ON ONE OR TWO CHANNELS** | 3 | Not tested on rev A (no part to hand). Parking 3, 6, 7, 8 raised +3V3_A ~110 mV (r45.20), so the idle load is mostly gone anyway | a 74AUP2GU04 in item 18's SC-70-6 footprint on one or two channels: a BOM change |
| 9 | **Si5351C, the TCXO on CLKIN** | PLANNED, **RA1 CONFIRMS THE MECHANISM** | **1** | PLLA slips at CLK0 ≥ 4 mA; 15 h clean at 2 mA (r39-45). **RA1's faster XA edge: 0 slips in 14 of 15 drive settings (was 9 slipping), 53/s at 8+8 mA (was 1600)** (r45.20) | CLKIN, separate VDDO banks |
| 10 | **Isolate HO, drive it at 2-4 mA** | PLANNED | **1** | 58 ps on unit 11 (r41); +16 ps rms on an unrelated pair at 8 mA (r45 T2). **OCXO pairs across helper-buffer groups: 20 ps (HO off), 24 (2 mA), 33 (4 mA), 53 ps (8 mA) per transition; within a group 11-15 ps** (r45.20 O6) | buffered, filtered, own bank, away from the helper tree; RA5 |
| 11 | **Park unused channels** | PLANNED, **VALIDATED ON REV A** | **1** | 100 kΩ from S to ground held unit 5 quiet in 30 of 30 restarts (r45). **Parks on 3, 5, 6, 7, 8: all quiet 30/30, and unit 13 began oscillating (29/30): park every one** (r45.20 O2) | 3-pin header, 50R / PARK |
| 12 | **RC, not bead, gate filters** | PLANNED, **CONFIRMED ON REV A** | **1** | **FB401 bridged: unit 4 quiet in 30 of 30**, was oscillating 30 of 30 (r45) | 2.2-10 Ω on every gate; RA3 picks the value |
| 13 | Crosstalk rules | PLANNED, reprioritised | 2 | No 10 MHz tone above 0.4 ps; state changes and strong edges are what move a channel (r45 T2) | supply rules first |
| 14 | Build rev B in KiCad 10 | DECIDED | 2 | Jason views in KiCad 10 and never saves; opening rewrites the project file | port `build.py` and `gen/project.py` |
| 15 | Deglitch the beats in the gateware | PLANNED | 2 | 28-32% of transitions carry extra edges (r45) | |
| 16 | Monitor the Si5351 during long runs | PLANNED | 2 | | |
| 17 | ps per cycle from the measured beat | PLANNED | 2 | 0.8% off design (r43) | |
| 18 | **Replica-biased squarers** (AM-to-PM) | PLANNED | **1** | −147 to −231 ps/dB (r43, r45 T3); a pair drifts +4-5 ps/K (r45) | 74LVC2GU04 per channel; RA2 |
| 19 | U.FL/MMCX monitor taps | PLANNED | 2 | Every rev A question needed a hand-held probe | 25-35 taps |
| 20 | Heater and thermal layout | OPEN, RA7 decides | 2 | Heated ~11 K, the unit 1-2 pair moved +27.5/+31.1 ps; the heater runs the left edge 5 K hotter (r45, RA2) | symmetric heating, sensors at the squarers |
| 21 | pps inputs | **NO CHANGE** | | First real pulses counted; thresholds 1.93 V up, 1.32 V down at the jack (r45) | keep 1k/10k, 51R DNP |
| 22 | **The helper's distribution** | **NEW**, PLANNED | **1** | OCXO pairs on one helper buffer (U3004: units 1-4; U3006: 9-11): 11-12 ps per transition; across buffers 20 ps with HO off, 53 ps at 8 mA; a channel's state moves its whole buffer group 2-3 ps; the port swap (O8) puts it on the board, not the OCXO (r45.20) | one low-jitter fan-out on its own clean supply, equal-length lines, HO kept off it |

## Rev A boards: reworks and hand-fitted parts

The tag is the board as JLCPCB built it. Anything done to a physical board
since goes here, so that every later measurement can be read against the
right hardware. All of it is the bench board.

| date | change | why | result |
|---|---|---|---|
| before round 39 | SMAs hand-fitted on units 1, 2, 11 and 12 (10 MHz and pps), `HO` (J3001) and `HIN` (J3002) | the hand-solder BOM | |
| 2026-10-06 (r44) | SMA on unit 4 (J401); terminal block J6001 | a switchable source on unit 4; the 1-Wire probe | both work (r45) |
| before 2026-10-06 | SMA on unit 9 (J901), by Jason | | CG-2's generator cabled there (r45) |
| 2026-10-07 (r45) | **FB401 bridged** | item 12 | unit 4 quiet in 30/30 restarts (was oscillating 30/30). T1: the step on unit 2 from unit 4's state fell from 1.90 to 1.39 ps, but did not go. |
| 2026-10-07 (r45) | **100 kΩ from TP502 (unit 5's `S`) to JP501 pin 2 (GND)** | item 11 | unit 5 quiet in 30/30 (was oscillating 30/30). Unit 3 now oscillates 29-30/30 (was 7/30). |
| 2026-10-07 (r45) | **Barrel jack J2003 fitted; a 15 V 6 A supply in it** | item 20, RA2 | The heater works. No added noise (jitter +0.06 ± 0.07 ps, rails unchanged). |
| 2026-10-08 (r45.19) | **S1**: SMA J1001 and header JP1001 on unit 10; **JP201 and JP1001 fitted** | RA7's fourth corner | unit 10 beats (O0) |
| 2026-10-08 (r45.19) | **S2**: 100 kΩ parks on units 3, 6, 7 and 8 (TPx02 to JPx01 pin 2) | item 11 | all quiet 30/30 (O2). Unit 13 then oscillates 29/30 at 582 kHz |
| 2026-10-08 (r45.19) | **S3**: FB401's bridge → 4.7 Ω (RA3) | item 12 | unit 4 quiet 30/30 undriven (O2) |
| 2026-10-08 (r45.19) | **S4**: R3001 3k3 → 1k, R3002 1k → 330 Ω (RA1) | item 9 | slips gone in 14 of 15 drive settings (O3) |
| 2026-10-08 (r45.20) | **S2b**: 100 kΩ park on unit 13 (TP1302 to JP1301 pin 2), soldered with the board on | item 11 | quiet 10/10. Every channel is now driven or parked |
| not planned | HIN: R3004 in, R3005 out (an external helper) | | |

CLK0 at 2 mA (round 40) is firmware, not a rework.

**Before data**, all on the PYNQ or in `gateware/board/`:

- `logs/before_20261006T2325Z`: the battery before any rework.
- `logs/mods_20261007T2139Z`: the battery after FB401, the unit 5 park and
  the heater jack.
- `toggle_20261007T1532Z` and `toggle_20261007T2146Z`: T1 before and after
  the bridge.
- `crosstalk_20261007T1914Z` and `…1916Z`: T2.
- `xcheck_amp_20261007T19*`: T3.

## Tests still to run on rev A, before rev B is drawn

**2026-10-08: the OCXO bench.**  `gateware/board/BENCH_WIRING_OCXO.md` has the
rework, wiring and test plan that carries these out:

- S1-S4: an SMA on unit 10, parks on units 3, 6, 7 and 8, RA3 and RA1;
- O0-O8 in a day;
- N1, which is RA7 at the four corners (units 1, 2, 10 and 11);
- N2, which is RA5.

Its table maps each test to the rev B item it decides.  The RA sections below
stay as the definitions.

Each is explicit enough to do without the chat.

- **Hands** is what Jason does at the bench.
- **Runs** is the command on the laptop, with `PYNQ_SSH` and `PYNQ_SCP` set
  as for `xcheck.py`.
- **Against** is the data it is compared with.

### RA1. The XA drive: is the Si5351's reference slope the slip mechanism? (item 9)

- **Hands.** Two 0805 resistors, both beside the TCXO X3001 and the Si5351
  at the top centre:
  - R3001, 3k3 → **1 kΩ**. At (101.25, 47.0), vertical; pads at
    y = 46.09 (TCXO side) and 47.91.
  - R3002, 1k → **330 Ω**. At (98.1, 49.4), horizontal; pads at x = 99.01
    and 97.19 (GND).
  - The divider ratio barely changes (0.23 → 0.25); the source impedance
    drops from 767 Ω to 248 Ω.
- **Runs.** `night.sh xa 13`: the battery, T1, then the logged night.
- **Against.** `mods_20261007T2139Z`'s drive matrix. There, CLK0 at 4 mA
  slips 865-1711 per second whenever CLK1 is at 4 mA or more.
- **Decides.**
  - **If CLK0 at 4 mA goes clean**, the slow crossing at XA was the
    mechanism, and the Si5351C's CLKIN removes it; item 9's layout rules
    become insurance.
  - **If it still slips**, the coupling also runs through the supplies and
    ground. The separate VDDO banks, the decoupling and the guard ring
    become as important as CLKIN.

### RA2. The board's own temperature coefficient, with the heater (items 18 and 20): DONE

**Result** (README 45.16, `overnight_20261007T2201Z/`):

- Heating the board ~11 K, with the SDG at room temperature, moved unit 2 −
  unit 1 by **+27.5 and +31.1 ps**: about +2.6 ps/K of average board
  temperature.
- It settled in ~5 minutes and reversed when the heater went off.
- The heater runs the left edge ~5 K hotter than the right, so the result
  can't say whether that is two different channel coefficients, or one shared
  ~10-13 ps/K coefficient seen through the gradient. **RA7 decides.**

What was planned:


- **Hands.** Done: the 15 V supply in J2003.
- **Runs.** `night.sh mods 15`, started 2026-10-07 14:39 PDT. The heater is
  off 1 h, on 3 h, off 3 h, on 3 h, then off. The logger cuts it off for
  good above 50 °C.
- **Against.**
  - Round 45's room-temperature night: unit 2 − unit 1 drifted +4.3 to
    +5.0 ps/K, SDG included.
  - The heater warms only the board, so the drift during a step is the
    board's own.
- **Decides.**
  - **Item 18**: the size of the board's own temperature coefficient, which
    the replica bias is meant to cut.
  - **Item 20**: whether channels warm unevenly. Round 45 saw the pair move
    3 ps within seconds of switch-on, before the thermometers moved, and
    the sensors near units 1 and 2 ran 2 K warmer than the helper's.

### RA7. The OCXO on four units: per-channel temperature coefficients (items 18 and 20)

- **Hands.**
  - Four OCXO outputs to units 1, 2, 4 and 11, with the 50R jumpers fitted
    and the **same amplitude** at each, checked on the scope.
  - The SDG's rear `10MHz In/Out` from a fifth output (Source: External),
    and the SDG's output 1 onto unit 9.
  - HO stays on unit 12.
- **Runs.** `overnight.py` with the heater stepped, as RA2, for a night.
- **Against.** RA2. With every pair now a same-source pair, nothing but the
  board is in any of them.
- **Decides.** The heater's left-hot pattern and the room's even swings warm
  the four units in different proportions. That gives each channel's own
  coefficient, and whether the board responds to its mean temperature (A)
  or to gradients across it (B).
  - **(A)**: item 18's replica bias is the fix.
  - **(B)**: thermal symmetry and an even heater are (item 20).
  - It also gives the board's floor with no generator jitter in the pairs.
- **Before plugging in.** Is the splitter a distribution amplifier or a
  passive 8-way (~9 dB down per port)? And what is the OCXO's output level?

### RA3. RC instead of the bridge: what resistor, and does local RC isolate a neighbour? (item 12)

- **Hands.** Replace FB401's solder bridge with a **4.7 Ω 0805**, between
  pads (142.76, 77.14) and (142.76, 79.26).
- **Runs.** `unplugged.py` (inside the battery) and T1: `toggle_test.py 8`.
- **Against.**
  - Unit 4 quiet in 30/30 with the bridge.
  - T1's +1.39 ± 0.38 ps after the bridge, and +1.90 ps with the bead.
- **Decides.**
  - **Still quiet with 4.7 Ω**: the resistor value works, and no resonance
    comes back.
  - **T1's step smaller**: local RC isolates neighbours as well. If the step
    doesn't shrink, the shared +3V3_A path (item 5) is the coupling, and
    RA4 is the test of that.

### RA4. A +3V3_A strap: is the shared rail the coupling path? (item 5, optional)

- **Hands.** One insulated wire, AWG 22-24, about 60 mm:
  - from C2003 pad 1, the LDO's 10 µF output capacitor at (122.00, 7.95),
    top centre beside U2001 (TPS7A2033);
  - to FB201 pad 1, unit 2's +3V3_A, at (142.76, 61.46).
- **Runs.** T1 (`toggle_test.py 8`). The logged night's rails will show
  J5001's +3V3_A rise.
- **Against.** T1 after the bridge (+1.39 ps). +3V3_A at J5001 sags
  3.4 mV when unit 4 goes undriven.
- **Decides.** If the step shrinks by about the ratio the rail sag does,
  item 5's plane is the fix. Combined with RA3, that separates "the shared
  rail" from "the local filter".

### RA5. HO at 4 mA for a whole night (item 10; firmware only)

- **Hands.** None.
- **Runs.**
  1. `./pynq-run si_set.py 2 4` on the PYNQ.
  2. `overnight.py 13 --period 120`.
  3. `si_set.py standard` in the morning.
- **Against.**
  - T2: per-transition rms 29.9 ps at 4 mA, against 32.7 ps at 8 mA.
  - Round 45's 8 mA night.
- **Decides.** Whether rev A's firmware moves to CLK1 at 4 mA now. That
  needs unit 12 to stay a clean beat, no new slips, and the lower jitter to
  hold for a night. It also fixes rev B's HO drive (item 10).

### RA6. A locked source on unit 4 (items 13 and 18; needs an instrument)

- **Hands.** A 33220A with Option 001 (rear 10 MHz jacks), teed onto C6
  (BENCH_WIRING.md); or the HP moved from unit 11 to unit 4.
- **Runs.**
  - `crosstalk.py`: unit 4 then becomes a phase reference.
  - AM-to-PM on unit 4: `xcheck.py amp`, adapted to the 33220A.
- **Decides.**
  - Item 18's numbers on a third unit.
  - Whether HO's weak ~40 ps tone on unit 11 is real, which the HP's own
    600 ps wander now hides.

### Not runnable

- **T8**, a 74AUP1GU04 in one squarer's place: no part, and too fine a
  rework for the bench's iron. Item 8 is decided without it.
  - **2026-10-08: back as an optional rework.** `BENCH_WIRING_OCXO.md` S5 puts
    it on unit 6, with its own SMA and 50R header and the spare right HP as
    its source; O9 measures it.
  - The part is SC-70-5 only (Nexperia `74AUP1GU04GW`; TI makes no
    unbuffered AUP), so it has to straddle the SOT-23-5 pads.
  - `SN74AHC1GU04DBVR` is the drop-in alternative in the same footprint.

**Order** (RA2 done):

1. RA7, as soon as the OCXO's splitter and level are known.
2. RA5 (a night; no hands).
3. RA1 and RA3 in one sitting, then `night.sh xa 13`, which carries RA3's
   T1.
4. RA4 if RA3's step doesn't shrink.
5. RA6 whenever a locked source turns up.

---

Each item below says why (with the round where the evidence is), what, and
where it stands:

- **IN GENERATOR**: already changed in `gen/` or `pcb/`; takes effect when
  rev B is built.
- **PLANNED**: agreed, not yet applied.
- **VALIDATED / CONFIRMED ON REV A**: a rework on the bench board showed it
  works.
- **TEST ON REV A FIRST** / **TEST RUNNING**: a rework or measurement on the
  rev A board decides it.
- **NOT DOING**: considered and decided against, with the reason.
- **OPEN**: a choice still to make.

---

## Silkscreen

### 1. Everything that belongs to a box prints inside that box: IN GENERATOR

**Why.** Round 41 found that on rev A:

- FB401's designator printed in unit 6's box;
- unit 2's R203, C203, C207 and FB201 printed in unit 4's box;
- FB204, C209 and R208 printed outside the P2 box;
- the same happened, mirrored, on the odd side.

**71 designators** were outside their own box in all. The unit tiles are
rotated 90 or 270, so a tile's power gutter faces the neighbouring unit, and a
label pushed out of it lands in the next box.

**What.**

- `pcb/build_pcb.py` places every unit-tile designator and test-point letter
  only inside its own box. It scans the box nearest-first before giving up,
  and places ICs and connectors before passives and test pads.
- It refuses to write a board with anything outside its box.
- `pcb/check_silk_boxes.py` checks a finished board file independently, and
  `build.py` runs it after the board step.

Rebuilt without routing:

- **0 items outside their box**;
- **all 591 designators printed**, where rev A left three on F.Fab.

The routed rev B build must still pass the same check.

### 2. Jumper designators above the jumper, close to it: IN GENERATOR

- `JPn01` sits 1.65 mm off the header, on the side away from the gutter, and
  centred across its two pins.
- That is above the jumper on the right-hand (even) units and below it on the
  left, the mirror image, as everything else on that side is.

### 3. 1-Wire colour labels at each screw, just under the terminal: PLANNED, priority 2

**Why.** Rev A prints the wire colours, but not next to the pins they name.
Jason, round 45: "not right next to their pins".

- Each terminal's `blk red yel` is printed turned 90°, at y = 18.2. That is
  7 mm below the terminal's outline, which ends at y = 11.22.
- The two 47 Ω resistors sit under pins 2 and 1. Round 31's placer slid
  those two tags sideways around them, by these amounts (W1, J6001):

| pin | signal | DROK wire | pin x | tag x | how it reads |
|---|---|---|---|---|---|
| 1 | DAT | yellow | 16.0 | 17.5 | 1.5 mm outside the row |
| 2 | VCC | red | 12.5 | 10.5 | nearer pin 3, GND, than its own pin |
| 3 | GND | black | 9.0 | 9.0 | right |

- All five terminals are the same. On W2-W4 the `red` slides 2 mm the
  other way, toward the DAT pin.
- **The strip directly under each outline holds the designator `J600n`.**
  That is where the eye goes while screwing a wire down.
- Also on rev A, `R6002` and `R6005` print across their own resistors'
  outline marks. `pcb/silk_region.sh GPSDO-PYNQ-Z2.kicad_pcb 4 1 36 25 out.png`
  renders this corner as printed.
- The pin-to-signal map is unchanged:

| pin | signal | DROK probe wire |
|---|---|---|
| 1 | DAT | yellow |
| 2 | VCC | red |
| 3 | GND | black |

**What** (Jason's layout, round 45):

- **Two lines centred on each pin, directly under the terminal's outline:**
  - the colour, `YEL RED BLK`, in capitals so no descender reaches the next
    line;
  - under it, the signal: `DAT VCC GND`.
  - At 1.0 mm a three-letter word is about 2.7 mm wide. The 3.5 mm pitch
    fits it with about 0.8 mm between words.
- **Move `J6001`-`J6005` off that strip.** Either put each inside its
  terminal's outline below the screws (y ≈ 10.2, hidden under the body
  once fitted), or put it on F.Fab. The W1-W5 tags above already name the
  terminals.
- **Move the VCC resistors down about 2 mm** (R6002, R6004, R6006, R6008,
  R6010: 1206, centre y 14.6 → 16.6).
  - Their top pad now starts at y = 12.58, 1.36 mm under the outline: room
    for one line of text, not two.
  - Moved, the bottom pad ends at 18.6, 0.7 mm above FB6001.
  - The pin spurs and the +3V3_D bus height move with them. Both are
    written from `G.PROBE_X` in `pcb/build_pcb.py`.
- **The legend line** `yel = DATA   red = VCC   blk = GND` then only repeats
  what every screw says. Keep it only if it still fits without crowding.
- **Check it in code**, as item 1 does for boxes:
  - each word's centre within 0.3 mm of its pin's x;
  - its top within 0.5 mm of the outline;
  - no silk on any pad.

### 4. A test point at a squarer's output: PLANNED (optional), now part of item 19

`S` is the squarer's *input*, so it shows a sine or triangle. There is nowhere
to see the squared 10 MHz. One pad on one unit's GU04 output (its flip-flop's
D) would do. Item 19 makes it a plug-in tap on two or three units.

---

## Power

### 5. A real +3V3_A plane: PLANNED, priority 1

**Why.** Round 41 measured the rail:

| point | voltage |
|---|---|
| U2001 pin 5 (the LDO output) | **3.286 V** |
| the debug header J5001 | **3.177 V** |

That is 109 mV lost in the copper, at ~180 mA (the board draws 230 mA in
total). +3V3_D loses 7 mV.

- +3V3_A is **tracks only**: 1431 mm of 0.5 mm on F.Cu, with no pour. The
  generator's docstring says the 3.3 V rails are "poured on L1 between tiles";
  they are not.
- A resistor-network model of the tracks puts each unit's squarer supply 27
  (unit 2) to 85 mV (unit 3) below the LDO, the whole left column worst,
  because it is fed through one junction.
- Static offsets do not matter, since each squarer self-biases on its own
  supply. **Load changes** do: an unplugged squarer switching in or out of
  oscillation moves every other channel's supply by a *different* amount,
  and against a 50 mV/ns sine each millivolt is ~20 ps.
- **Measured, round 45 (T1, README 45.12 and 45.14).** Unit 4 was
  switched eight times between driven and undriven, and unit 2 (its
  neighbour) moved each time:

| unit 4 undriven is… | unit 2 − unit 1 | +3V3_A at J5001 |
|---|---|---|
| oscillating (FB401 fitted) | **+1.90 ± 0.34 ps** | −2.6 ± 1.3 mV |
| quiet (FB401 bridged) | **+1.39 ± 0.38 ps** | −3.4 ± 1.5 mV |

- So stopping the oscillation removes only part of it. A squarer switching
  at 10 MHz draws a different current from one idling at its threshold,
  and the neighbour feels the difference through the shared rail.
- In use that happens whenever a GPSDO drops out or comes back: its
  neighbours step by ~1.5 ps. That is the size of the instrument's own
  2-minute floor (1.3 ps), so it is worth removing.
- **RA4** (a strap from the LDO to unit 2's bead) tests whether the shared
  rail is the path.

**What.**

- A +3V3_A pour or plane on an inner layer, fed from the LDO at one point
  near the middle of the board.
- Keep In1 as the unbroken GND reference.
- Correct the docstring.
- Together with item 12's RC filters, every squarer then sees a stiff,
  shared rail through its own small resistor. A neighbour's current
  change is divided by the plane's milliohms, not by a track's ohms.

### 6. Rail indicators with "in range": PLANNED, priority 3

- One LED per rail to show it exists: +5 V, +3V3_A, +3V3_D and the heater
  input.
- A **TPS3700** window comparator per rail (LCSC C2869617), set by a divider to
  about ±4 %. Its open-drain outputs, wire-ORed, light a green "OK" LED only
  inside the window.
- Drive every LED from +5 V, not from the analog rail.

### 7. Rail monitoring: PLANNED, priority 2

An **INA3221** (LCSC C181255) measures three rails' voltage *and current* over
I²C, through 0.1 Ω shunts on +5 V in, +3V3_A and +3V3_D. The PYNQ then logs
rail voltages and load currents with the measurement. Round 41's question
about an overloaded LDO would have taken one read.

**Round 45 adds a reason.** Overnight, Jason's DMM found +3V3_A and +3V3_D
flat to 1 mV across a 2.5 K swing (3.185/3.296 V, then 3.186/3.297 V).

- The CircuitGears watching them read 1-2% low.
- Their zeros drift ~15 mV/K, so they need re-zeroing every reading.
- Even then, one of them drifted 28 mV in gain.

An on-board monitor removes a whole instrument's worth of calibration from
every overnight run.

### 8. LDO load and squarer current: NOT DOING (keep the 74LVC1GU04)

- Rev A's +3V3_A carries ~180 mA, within the TPS7A2033's 300 mA. The part
  was never overloaded; the 3.15 V was distribution drop (item 5).
- Most of that load is unplugged squarers biased at their threshold.
  Parking them (item 11) removes it, and round 45 showed parking works.
- The candidate lower-current squarer, the **74AUP1GU04**, is pin
  compatible. But its test (T8, one channel swapped on rev A) can't be
  done on the bench.
- Changing the squarer family would also throw away everything measured
  about this one: AM-to-PM (item 18), chatter, the temperature
  coefficient.
- **Decision**: keep the 74LVC1GU04, and let parking (11), the plane (5)
  and RC filters (12) deal with the current. Revisit only if rev B's own
  measurements ask for it.
- **2026-10-08 (r45.20): onto one or two of rev B's channels instead.**
  - T8 couldn't run on rev A: there is no AUP part on the board to take, and
    one part isn't worth an order.  The 74AUP1GU04 also comes only in SC-70-5,
    which doesn't fit the SOT-23-5 pads.
  - **The cheap route on rev B.**  Item 18 puts a dual unbuffered inverter on
    every channel (74LVC2GU04).  Draw its footprint as SC-70-6 (TI's DCK)
    and Nexperia's **74AUP2GU04GW** (SOT363) fits it.  One or two channels
    can then carry the AUP part as a BOM change, with no new footprint.
    **Confirm the two parts' pinouts match before drawing.**
  - Not on the null channel, and not on a channel meant for the best
    reference.  Silkscreen which channels carry it.
  - The idle current that motivated item 8 is mostly gone: parking units 3,
    6, 7 and 8 raised +3V3_A by ~110 mV (CG-1, r45.20).  So the AUP channels
    are an experiment in jitter and AM-to-PM, not a fix.

---

## The helper synthesiser

### 9. A Si5351 that works with margin: PLANNED, priority 1: the Si5351C with the TCXO on CLKIN

**Status, 2026-10-07.**

- **Firmware**: CLK0 at 2 mA has been clean through every test, 15.1 h
  overnight included.
- **Margin**: CLK0 at 4 mA still slips 865-1711 per second whenever CLK1 is
  at 4 mA or more (battery `mods_20261007T2139Z`, after the other
  reworks).
- **RA1** (R3001/R3002) decides how much of item 9's layout list is
  necessary beyond CLKIN itself.

**Why.** Rounds 39-40 found:

- In fractional mode, PLLA cycle-slips whole 25 MHz reference cycles when the
  chip's own outputs switch hard: ~650/s at CLK0 8 mA, and 900-1400/s at 4 mA
  once HO drove 50 Ω. Its own LOL bits never notice.
- CLK0 at 2 mA was clean in every configuration, and 600 s continuous with
  zero slips. That is the firmware fix, and it stays.
- **The margin is thin**: `TP_XA` reads 0.2-0.4 Vpp, a rounded triangle,
  against the 1 Vpp the datasheet drives XA with. The source is the HCMOS
  TCXO (10 ns edges) through a 767 Ω divider into XA's internal load.

Round 42 repeated the drive matrix, with HO into unit 12's 50 Ω:

| CLK0 \ CLK1 | 2 mA | 4 mA | 6 mA | 8 mA | off |
|---|---|---|---|---|---|
| **2 mA** | 0 | 0 | 0 | 0 | 0 |
| 4 mA | 0 | 959-971 | 1415-1421 | 1367-1372 | 0 |
| 8 mA | 2196-2214 | 2224-2228 | 2025-2026 | 1532-1540 | 1023-1053 |

Slips per second, two fresh starts each. The chip latched no LOL or LOS flag
in any of the 30.

**The likely mechanism: a slow crossing.**

- One extra or missing reference edge is exactly one 40 ns slip. A slowly
  crossing input can trigger twice, or not at all, on a few millivolts of
  the outputs' switching noise.
- XA, driven through 767 Ω into its own 10-20 pF, swings 0.4-0.55 Vpp
  unprobed and crosses its threshold at about **25-45 mV/ns**. That comes
  from an RC model fitted to your probed 300-520 mV.
- CLKIN, driven by the same TCXO, would cross at **210 mV/ns or more**. That
  is the FT5HN's slowest specified edge, 0.5 V to 2.64 V in 10 ns: five to
  nine times steeper.
- The R3001/R3002 swap on rev A tests this directly. The same model gives
  ~0.8 Vpp at XA and about twice the slope.

**The part.** JLCPCB has it. I was wrong in round 40. I had tried their
search web page, which does not render for me, instead of `mfg/jlc_api.py`,
the client that priced this whole BOM. The design log's own §6 table had
already listed `SI5351C-B-GM` (94 in stock on 2026-09-08). Queried through
`jlc_api.py` on 2026-09-30 at 16:39 PDT:

| part | LCSC | package | JLCPCB stock | price @1 / @10 |
|---|---|---|---|---|
| **`SI5351C-B-GMR`** | C2649375 | QFN-20 4×4 | **148** | $5.71 / $4.92 |
| **`SI5351C-B-GM`** | C3608122 | QFN-20 4×4 | **80** | $5.51 / $4.74 |
| `SI5351C-B-GM1` | C3608072 | QFN-16 3×3 | 1 | $5.03 |
| `SI5351A-B-GTR` (rev A's) | C504891 | MSOP-10 | 34 013 | $1.19 |

- **GM and GMR are the same part, packed differently.** The datasheet's part
  numbering (Figure 24) gives the suffix as blank = coil tape, R = tape and
  reel. They share silicon, package, footprint and registers, so they are
  interchangeable on the BOM. Order whichever JLCPCB has more of on the
  day; the BOM line takes one LCSC code.
- Both are Extended: one setup fee.
- The ~30 other `SI5351C-B*` codes on the list are factory-programmed, with
  0 in stock. They match what round 40 reported finding.
- **Mouser** (your reading, 2026-09-30):
  - `SI5351C-B-GM`: **43 288 in stock**, $5.02;
  - `-GMR`: 787, $5.11;
  - the QFN-16 `-GM1` and `-GM1R`: on order only, as at JLCPCB. So the
    QFN-20 is the package.
- **DigiKey** (your reading, 2026-09-30):
  - `-GMR`: **over 3000 in stock**;
  - `-GM`: none, with 200 expected in November.

  It lists the GM as active at $5.21. Reels at DigiKey are usually also sold
  by the piece as cut tape.
- So both distributors have plenty of the part, Mouser mostly as GM and
  DigiKey as GMR. That meets your rule.
- JLCPCB's 228 covers many two-board builds, but it is not deep. Mouser's
  stock is the backstop if JLCPCB runs out, through JLCPCB's global sourcing
  or by consigning parts. Buying a few into your JLCPCB parts library ahead
  of the order reserves them.

**What, for rev B.**

- **TCXO → CLKIN directly**, through ~33 Ω in series at the TCXO. No divider;
  R3001 and R3002 go.
  - CLKIN is a CMOS input (datasheet Table 6): V_IL ≤ 0.3 VDD, V_IH ≥ 0.7 VDD
    (2.31 V), 3.60 V max, 3.8 V absolute, 10-100 MHz.
  - The FT5HN's guaranteed levels (V_OL ≤ 0.5 V, V_OH ≥ 2.64 V) clear both
    thresholds by 0.3-0.5 V. Its near-rail typical swing clears them by
    about 1 V. Rev A's XA swings only 0.4-0.55 Vpp in total.
  - The thresholds scale with the Si5351's VDD, so keep the TCXO and the
    Si5351 on the same rail. Rev A already does: each has its own bead from
    +3V3_D (FB3001, FB3002).
- **Register 15**:
  - PLLA_SRC = PLLB_SRC = CLKIN, and CLKIN_DIV = ÷1; 25 MHz is inside the
    PLL's input range.
  - The reference-loss flag becomes LOS_CLKIN (bit 4) instead of LOS_XTAL,
    and XTAL_CL stops mattering.
- **XA/XB floating**, as the datasheet says for an unused crystal input.
  Optionally, keep a DNP 25 MHz crystal footprint there: register 15 can
  switch either PLL back to it with no rework.
- **Output banks.** On the 20-QFN, **VDDOA feeds CLK0 *and* CLK1**, so the
  helper and HO must not sit on CLK0/CLK1 as they do on rev A.
  - Put the helper on CLK0 (VDDOA, pin 13, the right side of the package)
    and HO/null on CLK4 (VDDOC, pin 19, the top side). They are then on
    separately decoupled banks, on different sides.
  - Tie unused banks' VDDO to VDD, and leave unused outputs floating and
    powered down (datasheet 7.5).
- **CLKIN** (pin 6) sits between SDA (5) and OEB (7), with CLK3 one pin
  further (8). Leave CLK2/CLK3 unused, and tie OEB to GND.
- **INTR** (pin 3; open drain, pull-up > 4.7 kΩ), optional: to a test point
  or a spare FPGA pin, a hardware record of LOL and LOS (item 16).
- **An external 10 MHz reference in**, optional. Round 44 asked how to lock
  the bench's generators to the board, and rev A cannot take a reference at
  all: the Si5351A reads only the TCXO, through XA.
  - CLKIN takes 10-100 MHz CMOS, and either PLL can be pointed at it.
  - A jumper (or a 2:1 buffer) choosing between the TCXO and an `EXT REF`
    SMA, squared like a 10 MHz input, would run the helper and `HO` from a
    house reference or a GPSDO.
  - `HO` would then be a disciplined 10 MHz to lock the bench to, and the
    helper's frequency would be known absolutely.
  - The PLL plan changes with a 10 MHz reference, which is inside the 10-40 MHz
    the PLL accepts.
- **Package**: QFN-20, 0.5 mm pitch, with an exposed pad and vias. JLCPCB
  places it; hand rework needs hot air. Round 8 kept the MSOP for its stock
  and its hand-solderable package. A reference with margin now outweighs
  both.
- **Driver**:
  - the register 15 value;
  - HO's MultiSynth, CLK_CTRL and OEB bits move with its output;
  - `sticky()` reads LOS_CLKIN;
  - `bringup.py`'s slip check stays.

**Rev A's test still decides how much else matters.** Swap R3001 to 1k and
R3002 to 330 Ω: the same ratio, a 248 Ω source. Round 42 has the bench list.

- **If CLK0 at 4 or 8 mA then runs clean**, the reference's slope was the
  mechanism, and CLKIN removes it.
- **If not**, the coupling also goes through the supplies and ground, and
  the separate VDDO banks and the layout rules below carry more of the load.

**The fallback, if the C's stock goes:** the `SI5351A-B-GTR` with XA driven
properly, at ~1 Vpp, AC coupled, with fast edges. Either:

- a clipped-sine 25 MHz TCXO into XA through 100 nF (JLCPCB has Abracon
  AST3TQ53 parts, C2031171 and C2030784); or
- the HCMOS TCXO through a stiff attenuator or a buffer.

**Either way:**

- **Every VDDO gets its own decoupling.** Rev A shares one bead-fed node
  between VDD and VDDO (round 21's choice).
- With the C, the helper and HO sit on **different VDDO banks**. The A's
  MSOP-10 has one VDDO for all three outputs, which is one more reason to
  prefer the C.
- Clock output traces go away from the reference pin, which is guarded with
  ground.
- Keep CLK0 at 2 mA.
- Keep the slip check in software.

**XTAL_CL is a register, not a part** (round 41): register 183, 6/8/10 pF,
set by the driver. Going beyond 10 pF would need a capacitor on XA, and it
would shrink the reference further. Don't.

**Round 45's night** (README 45.12):

- 15.1 h with **no PLLA slips, no HO-beat jumps and no latched LOL/LOS**,
  at CLK0 2 mA. The firmware fix holds; the Si5351C and the XA drive are for
  margin, not for a fault seen today.
- **The board's TCXO wanders 20-30 ppb between 20 s windows.** It shows
  against the SDG and against the PYNQ's own crystal alike, and it swings
  ~±250 ppb with the room.
  - It is common to every unit and cancels in every pair.
  - It matters only when one unit is read against the helper alone, which
    is what the `EXT REF` option above is for.

### 10. Isolate HO, and drive it at 2-4 mA: PLANNED, priority 1

**Why.** Round 41: HO at 8 mA into 50 Ω puts a **~58 ps** sinusoidal phase
error on unit 11, at f(unit 11) − f(HO) ≈ 10 Hz. That is about 5 mV of HO
arriving at unit 11's squarer, across the board. With HO off, unit 11 has no
chatter at all and 24 ps rms per edge; with HO on, 51 ps and 2.7× the edges.
**HO is the largest aggressor on the board.**

**What.**

- Do not run the Si5351's CLK1 pin straight to an SMA. Buffer it, and
  low-pass it to a sine at the connector.
- Route it as stripline far from every channel input, and put its jack beside
  unit 13.
- Alternatively, feed the null channel from CLK1 through an on-board, fixed,
  filtered path at a modest level, and make HO a bench output that is off by
  default.
- With the Si5351C (item 9), HO moves to CLK4. That puts it on its own output
  bank, VDDOC, with its own decoupling, on the far side of the package from
  the helper.

**Round 45 (T2, README 45.13) adds a second effect.** HO's drive level
raises the jitter of a pair it isn't even connected to. Unit 2 − unit 1,
per transition:

| HO (CLK1) | off | 2 mA | 4 mA | 6 mA | 8 mA (standard) |
|---|---|---|---|---|---|
| rms | 28.3 ps | 29.5 ps | 29.9 ps | 31.1 ps | 32.7 ps |

- At 8 mA that is ~16 ps rms added, in quadrature. Unit 12 still beat
  cleanly at 2 mA.
- So, besides the isolation above: drive HO at 2-4 mA. On rev A that is a
  firmware change (`IDRV_NULL` in `driver/i2c_devices.py`). **RA5** runs a
  whole night at 4 mA before it is made the default.
- The jitter rose steadily with drive, 28.3 ps with HO off. So whatever
  HO's output stage does on the shared chip and supply reaches every
  channel, not just its own cable. Separate output banks (item 9), the
  buffer and the filter above all act on that.
- Its coherent tone on unit 11, round 41's 58 ps, showed again only weakly
  (~40 ps at 8 mA, against a 26-34 ps floor). The HP on unit 11 wanders too
  much to resolve it better.

---

## The channels

### 11. Park an unused channel: PLANNED, priority 1, VALIDATED ON REV A

**Why.** An unplugged squarer sits still, chatters, or oscillates. Round 41,
over 30 restarts with units 1, 2, 11 and 12 driven:

- units 4, 5, 6, 8 and 9 oscillated **every time**, each at its own steady
  frequency (553.8-571.2 kHz);
- units 3 and 7 oscillated sometimes;
- units 10 and 13 never did.

The oscillation loads the rail and is a local aggressor. The squarer is AC
coupled, so grounding the SMA cannot reach it.

**What.**

- A 100 kΩ from the squarer's gate node (`S`) to a jumper pin. The resistor
  body sits at the gate, so the jumper's trace hangs off 100 kΩ, not off the
  node.
- A third pin on the existing 50R header: **1-2 = 50R, 2-3 = PARK**.
- Parked, the input sits at ~0.3 V, well below threshold. The output goes to
  the rail and the flip-flop sees a solid level: no chatter, no oscillation,
  and no crowbar current.
- Forgetting to un-park a used channel fails loudly (a quiet channel).
- **Why it matters, measured in round 45 (T1):** unit 4 going from driven
  to undriven moves its neighbour, unit 2, by +1.4-1.9 ps (item 5).
- **Validated on rev A, 2026-10-07.** A leaded 100 kΩ from TP502 (unit 5's
  `S`) to JP501 pin 2 (GND) held unit 5 **quiet in 30 of 30 Si5351
  restarts**, twice. Before, it oscillated in 30 of 30 at 559 kHz.
- **Side effect worth designing for.** With unit 5 parked and FB401
  bridged, **unit 3 began oscillating in 29-30 of 30 restarts** (it had
  oscillated in 7 of 30).
  - Which marginal units oscillate shifts with their neighbours, so parking
    alone is whack-a-mole.
  - Rev B parks every unused channel, and also removes the oscillator's
    tank on every channel (item 12).
- **Parking is for unused channels only.** 100 kΩ from `S` holds the input
  at ~0.3 V, so a driven signal would no longer cross the threshold. The
  jumper is what makes it per channel.
- **Option**: an I²C port expander driving the thirteen 100 k resistors, so
  the PYNQ parks empty channels itself.
- **Not recommended**: a permanent offset on every squarer. It brings back the
  amplitude sensitivity the self-bias removes.

### 12. No resonant supply filters on the gates: PLANNED, priority 1, CONFIRMED ON REV A

**Why.** Every gate is fed through its own 600 Ω@100 MHz bead into
100 n + 10 n. A ~0.7-1 µH bead with 110 nF resonates at ~0.5-0.6 MHz, where the
unplugged squarers oscillate.

**Test.** Bridge **FB401** (unit 4's squarer bead, at (142.8, 78.2)), then run
`./pynq-run unplugged.py 30 1,2,11,12`. The baseline is unit 4 oscillating
30/30 at 557.1 kHz (round 41). If it goes quiet 30/30, the bead is the cause.

**Then.** Feed the gates through 2.2-10 Ω resistors (RC, no resonance),
especially the squarers.

**Result, 2026-10-07 (README 45.14).**

- With FB401 bridged, **unit 4 was quiet in 30 of 30 restarts**, twice. It
  had oscillated in 30 of 30 at 557-560 kHz in rounds 41, 42 and 45.
- **The bead with its 110 nF is the oscillator's tank.** Remove the
  resonance and the self-biased squarer has nothing to oscillate with.
- **T1 after the bridge**: unit 4's change of state still moves unit 2, by
  +1.39 ps (+1.90 before). The filter stops the oscillation; it doesn't
  isolate the neighbour. That is item 5's job, or a resistor's (RA3).
- **Unit 3 started oscillating** once unit 5 was parked and FB401 bridged
  (item 11). So the fix goes on **every** gate, not just the units that
  oscillate today.

**For rev B.**

- Every squarer's (and flip-flop's) supply through a small resistor into
  its 100 n + 10 n: **RC, no inductor**.
- **RA3** picks the value: 4.7 Ω in FB401's place, then the battery and T1
  again.
  - 2.2 Ω gives a 0.66 MHz corner with 110 nF; 4.7 Ω gives 0.31 MHz; 10 Ω
    gives 0.14 MHz.
  - The squarer's few mA drop only millivolts, and a static offset doesn't
    matter: the squarer self-biases on its own supply.
- If a bead is wanted anywhere for EMI, it goes on the rail's feed, never
  on a single gate with its own capacitor.

### 13. Crosstalk: PLANNED, priority 2 (reprioritised by round 45)

Measured on rev A (round 41):

| path | effect |
|---|---|
| HO → unit 11 | ~58 ps at their difference frequency (item 10) |
| Siglent on units 1-2 → unit 11 | **3.3 ps** at their difference (4.83 Hz), above a 0.5 ps floor |
| HP → the unit 1 − unit 2 difference | at the floor (1 ps): common to both, so it cancels in a same-source pair |
| the Si5351's outputs → its own reference | item 9 |

Between two GPSDOs a mHz apart, channel crosstalk appears as a slow periodic
phase error with a ~1000 s period. It looks like wander, so it has to be
small, not merely averaged.

**Rules for rev B**, in the order round 45's measurements rank them:

- **First, the supplies**: the +3V3_A plane (item 5), RC gate filters on
  every channel (12), parked unused channels (11), and HO at 2-4 mA on its
  own output bank (10, 9). These address what was actually seen to move a
  channel: state changes (~1.5 ps) and strong edges (~16-19 ps rms of
  jitter).
- Then the isolation rules, which round 45 found already sufficient for
  10 MHz tones (no tone above 0.4 ps on the unit 1-unit 2 pair). They stay
  because rev B's taps (19) and the Si5351C's routing will change the
  layout:
- No near-10 MHz aggressor on the board beyond what is needed (item 10).
- Every clock (helper tree, HO, the Si5351's outputs) as stripline between
  ground planes, in its own corridor. The helper is already stripline.
- Each squarer's input node as small as possible, ringed with ground and
  stitching vias. No clock within a few mm of it.
- Via fences between channel strips.
- The +3V3_A plane (item 5), and RC rather than bead supply filters
  (item 12).
- Park unused channels (item 11).
- Series resistors on the beat and pps outputs to the header, to slow their
  edges.
- The pps Schmitts onto +3V3_D, so their once-a-second edges do not share the
  rail that sets the 10 MHz thresholds.

**Verify with a crosstalk matrix**: drive an aggressor at f + Δ and a victim at
f, and read the victim's phase at Δ with `beats.py`. Rev A's numbers above are
the baseline.

**Round 45** found no crosstalk by a cruder measure, and that measure turned
out not to measure crosstalk.

- A CircuitGear on unit 9 and an offset SDG output changed no unit's chatter
  (edges per transition).
- `top` dips by itself, so it cannot show crosstalk either way (README 45.11).
- The matrix above, read as phase, is still the test (45.12's T2).

**T2 ran (README 45.13).**

- No aggressor put a coherent tone above ~0.4 ps on the unit 1-unit 2
  pair: not the 33220A on unit 4 (unit 2's neighbour, −183.5 Hz), not the
  HP on unit 11 (+0.5 and +5 Hz, exact), not HO at any drive, not a
  CircuitGear's 10 MHz on unit 9.
- Units 1 and 2 couple to each other at 2.3 ps, both ways, including the
  SDG's own (`xcheck.py ramp 0.5 30`).
- **What does move a channel** is a neighbour's change of state (T1:
  +1.9 ps when unit 4 starts oscillating) and strong edges. HO at 8 mA adds
  ~16 ps rms of jitter (item 10), and a squarer toggling at 1 kHz on unit 9
  added ~19 ps rms.
- So for rev B, the rules about supplies (item 5), parking (11), filters
  (12) and HO's drive (10) matter more than the 10 MHz isolation rules.

---

### 22. The helper's distribution: NEW, PLANNED, priority 1

**Why (r45.20, the OCXO bench).**

- **The helper reaches the thirteen samplers through five 74LVC1G34 buffers**,
  each driving a block: U3004 units 1-4, U3005 units 5-8, U3006 units 9-11,
  U3007 unit 12, unit 13 and J4001.
- **With every unit on one OCXO, a pair sharing a buffer** (2 − 1, 11 − 10) is
  at 11-12 ps per transition, the DDMTD's own 12.3 ps step.  **A pair across
  buffers is 20 ps with HO off**, 24 at 2 mA, 33 at 4 mA and 53 at 8 mA.
- **O8 swapped the OCXO ports of units 1 and 11.**  The quiet pairs stayed
  quiet, so this is the board, not the source.
- **O7: a channel switching between driven and undriven moves its own
  buffer's whole group 2-3 ps** against the other groups.
- **What it means.**  A comparison between two GPSDOs on different buffers
  carries ~17 ps per transition of the helper tree's own jitter, plus
  whatever HO and the neighbours put into each buffer.  Averaging hides it
  (0.1-0.4 ps at 10 s), but it is the board's floor between any two channels
  that aren't neighbours.

**What.**

- **One fan-out** for all thirteen samplers, from one low-jitter clock-buffer
  part, rather than a cascade of single gates.
- **Its own LDO or filtered supply**, which no squarer's current shares.
- **Equal-length lines** to every sampler; ground under all of them.
- **HO's CLK1 trace and output kept away from the fan-out** (item 10).
- **Check before ordering:** the fan-out's additive jitter (well under 1 ps)
  and its output skew, which only adds a fixed offset per channel.

---

## Build environment

### 14. Tools on this machine: DECIDED, build rev B in KiCad 10

- `build.py` expects KiCad 9 extracted at `~/.local/kicad9/squashfs-root`.
  This machine has the AppImage (`~/.local/bin/kicad-9.0.9.1-x86_64.AppImage`),
  whose kicad-cli runs directly.
- `pcb/build_pcb.py` now takes `KICAD9_FOOTPRINTS` for the stock library
  path.
- **Jason has switched to KiCad 10**
  (`~/.local/bin/kicad-10.0.6-x86_64.AppImage`). He opens the boards to
  look, **never saves**, and will say if he does (2026-10-07).
  - Opening still makes KiCad 10 write its own files: it rewrote
    `GPSDO-PYNQ-Z2.kicad_pro` to its format (version 5, committed as
    `e1ff1fd`), and `GPSDO-PYNQ-Z2.kicad_prl` with its UI state (`0d6aac5`).
  - Those are KiCad's writes, not edits. Commit them on their own, labelled
    as such, never mixed with work.
  - A change to a `.kicad_pcb` or `.kicad_sch` that nobody announced is
    something to ask about, not to commit.
- **Decision**: port the build to KiCad 10 before rev B is built.
  - `build.py`'s `KICAD_CLI` default.
  - `pcb/build_pcb.py`'s stock footprint path (`KICAD9_FOOTPRINTS`).
  - `gen/project.py` writing version 5.
  - The board and sheets saved in KiCad 10's own format
    (`kicad-cli pcb upgrade`, `sch upgrade`), as CLAUDE_PCB.md asks for new
    boards.
  - Then opening rev B in the GUI changes nothing on disk.
  - Check that the KiCad 10 build reproduces rev A's fab outputs byte for
    byte (the round 30 test in `build.py`'s docstring) before changing
    anything else.

---

## Firmware and gateware (not the PCB, but ship with rev B's bring-up)

### 15. Deglitch the beats in `dmtd_capture.v`: PLANNED, priority 2

Real beats chatter. Round 45 measured it directly, as rising edges per
transition, over two nights and every condition tried:

| unit (source) | edges per transition | transitions with extra edges |
|---|---|---|
| 1, 2 (SDG sine) | 1.63, 1.72 | 28%, 32% |
| 4 (33220A sine) | 1.47 | 26% |
| 11 (HP sine) | 1.57 | 28% |
| 12 (HO, a square) | 1.00 | 0% |

- It is set mostly by the input's slew at the threshold. Neighbours and HO's
  drive didn't move it. Temperature moves it a little: −0.06 edges per
  transition (−0.11 on unit 11) for +11-14 K (RA2).
- The core keeps the *last* rising edge, so a timestamp can come from the
  falling transition's bounce, half a beat period away.
- Add design log §10's K-of-K deglitcher and first/last edge sums.
- `beats.py`'s analysis copes in software, but a quarter of every
  channel's transitions are not clean single edges.

### 16. Monitor and log the Si5351 during long runs: PLANNED, priority 2

Your requirement, round 41:

- Log the **sticky LOL/LOS bits**. `Si5351.sticky()` and `clear_sticky()` are
  in the driver; `bringup.py` clears them after programming and reports them.
- Log **pair-register slips** (`helper_slips()`, `si_watch.py`) for the
  whole multi-day run.

Round 45's `overnight.py` already logs, every 2 minutes, a 10 s
`si_watch.py` slip count (PLLA and HO's beat) and the latched LOL/LOS
flags. Over 15 h at CLK0 2 mA there were none.

A continuous **hardware slip counter** in the gateware would beat software
sampling: count 1024-helper-cycle intervals whose PS-clock length is off by a
reference period.  Today `si_watch.py watch` covers ~78 % of the time (round
42: 60 s of polling in every ~77 s).  With the Si5351C (item 9), its INTR pin
can also latch LOL/LOS in hardware.  Round 40 showed those flags miss the
slips, so INTR is a supplement, not a substitute.

### 17. The ps-per-cycle scale from the measured beat: PLANNED, priority 2

`T_RES_PS` assumes the design beat. A TCXO 2.5 ppm off moves it by 2 %.

Round 43 measured it:

- With the Siglent as the source, the beat period was 8031-8040 helper
  cycles, not 8102. That is **12.44 ps per cycle, 0.8 % off the design's
  12.3425**, enough to misreport a 16.7 ns phase step by 130 ps.
- Counting beat cycles instead, as `xcheck.py` does, needs no constant. It
  read the generator's phase steps with a slope of 1.00013 and a 0.05 Hz
  ramp to 2 ppm.

### 18. The squarer's amplitude-to-phase conversion: PLANNED, priority 1

**Why.** Round 43 stepped one generator output's amplitude while the scope and
the DDMTD both watched. Subtracting the generator's own delay, which the scope
sees, leaves the board's:

| unit | its input | its delay | fit: delay = K / A_peak |
|---|---|---|---|
| 1, 50R fitted | 1.70 → 0.82 Vpp | +1.36 ns | K = 1085 ps·V |
| 2, unterminated | 2.83 → 1.06 Vpp | +1.35 ns | K = 1125 ps·V |

- Both squarers cross about **70 mV off the sine's midpoint**, which makes
  the delay go as 1/amplitude.
- That is **~250 ps per dB at 1 Vpp**, and ~125 ps per dB at 2 Vpp. A source
  whose amplitude drifts 0.1 dB moves its measured phase by 13-25 ps, which
  is far more than the instrument's own noise.
- The likely cause is the 1 MΩ from each gate's output back to its input.
  It biases the input where the output's *average* equals the input's DC
  level, and that equals the switching threshold only if the threshold is
  exactly VCC/2 and the output is symmetric. Rev A's S nodes sit near 1.4 V.

**What.**

- **Bias each squarer from a replica.** Use a dual unbuffered inverter
  (74LVC2GU04). One half squares. The other half has its input tied to its
  output, so it sits exactly at its own threshold, and it feeds the squarer's
  input through the 1 MΩ.
  - The two halves share a die and a supply pin, so they should match to a
    few mV, roughly ten times less AM-to-PM.
  - A replica per channel, not one shared, because each unit's supply
    differs by tens of mV (item 5).
- Or use a comparator whose reference is the signal's own mean.
- Verify with `xcheck.py amp --scope`, before and after, on one channel.

**Bench note**: the SDG1032X's own output delay changes by about 1.5 ns at its
amplitude-range boundary, between 2.0 V and 1.6 V. Keep the generator's
amplitude on one side of that during any phase measurement.

**Re-measured, round 45 (T3).** Unit 1 (50R fitted) −231 ps/dB, K ≈
1.0 ns·V; unit 2 (unterminated) −147 ps/dB, K ≈ 1.16 ns·V. That is within
~10% of round 43.

**Temperature, round 45's night.** Unit 2 − unit 1 drifted +4.3 to
+5.0 ps/K over a 2.5 K room cycle.

- 2.1 ps rms about the fit, with no hysteresis: 619.0 ps cooling against
  618.4 ps warming, at 23.5 °C.
- That includes the SDG's two outputs.
- Feeding both units from one output through a tee, and stepping the
  temperature with the board's heater, would give the board's own share
  (README 45.12, T4). A replica bias should shrink it if the self-bias
  offset is what drifts.
- **RA2, running now, does the heater part.** The heater warms only the
  board, not the SDG, so no tee is needed: the pair's drift during a heater
  step is the board's.
- **Why priority 1.**
  - 147-231 ps per dB means a GPSDO whose output amplitude drifts by 0.1 dB
    with its own temperature shows 15-23 ps of false phase. That is ten
    times the instrument's 2-minute floor.
  - Nothing else on the board converts a source's behaviour into a false
    reading so efficiently.

---

## Probing without holding a probe

### 19. U.FL or MMCX monitor taps on every analog node worth a look: PLANNED, priority 2

**Why.** Jason, round 45:

> Lots of MMCX or U.FL test points on any analog signal you might want to
> investigate. This way I can plug in one of my many USB controlled scopes
> and just walk away rather than hold a probe as students walk in and ask
> for my time.

Rev A's open questions each needed a probe held in place for minutes:

- a squarer's input (round 41's 300-520 mV, with the probe's ~20 pF part of
  the reading);
- unit 4's supply after FB401, for the 557 kHz (42.4, F4);
- the TCXO (F2);
- the rails (F1, and today the CircuitGear leads on J5001).

ECP5-2ADC-2DAC already does this (its review item R17): four Hirose
U.FL-R-SMT-1 (LCSC C88374), each fed through 49.9 Ω.

**What.** A tap is a series part whose pad touches the node, then the jack a
few millimetres away, its ground pads stitched to the plane. Unplugged, it
adds well under 1 pF.

**The series resistor is the "divider built into the connector."** It sets
both the ratio and what the node feels:

| series part | into a 50 Ω scope | into 1 MΩ (CircuitGear, ADALM2000) | load on the node |
|---|---|---|---|
| 450 Ω | ÷10: the "10× probe" | ×1, but a ~45 pF pigtail rolls it off above ~8 MHz | 500 Ω |
| 1 kΩ | ÷21 | ×1 up to ~3.5 MHz | 1.05 kΩ |
| either, plus a series cap | the same, AC only | the same, AC only | nothing at DC |

**Where, and with what:**

| node | how many | series part | why |
|---|---|---|---|
| each unit's input after the 10 nF, **before the 330 Ω** | 13 | 1 kΩ | the amplitude and shape each squarer gets: items 12 and 18 per unit |
| each squarer's supply, after its filter | 13 if they fit, or units 1, 4 and 13 | 1 kΩ + 100 nF | the 557 kHz oscillation (item 12) and supply pushing |
| a squarer's output (item 4) | units 1 and 4 | 1 kΩ | the squared 10 MHz, its duty cycle |
| the helper, at the Si5351 and at the far end of its tree | 2 | 450 Ω | CLK0's amplitude and ringing at 2 vs 4 mA (rounds 40-44) |
| the TCXO's output | 1 | 450 Ω | the reference itself (F2) |
| +3V3_A at the LDO and at the far end, +3V3_D, +5V | 4 | 1 kΩ | DC to a 1 MΩ scope; ripple to either |

That is 25-35 taps.

**Three traps:**

- **Never tap the squarer side of the 330 Ω** (`S`, TP_SQ).
  - That node's 10 MHz source impedance is the 330 Ω. A 500 Ω tap into a
    50 Ω scope would cut its amplitude by about 40%.
  - Through item 18's AM-to-PM (~250 ps per dB at 1 Vpp), plugging the
    scope in would move that unit's phase by about a nanosecond.
  - On the source side of the 330 Ω, a 1 kΩ tap costs 2-5% of the amplitude:
    50-100 ps while plugged in. Measure that once, plugged and unplugged.
- **A rail tap into a 50 Ω scope draws current:** 3 mA through 1 kΩ, which
  is acceptable. Through 49.9 Ω it would be 33 mA, which is not.
- **U.FL is rated for 30 matings; MMCX for about 500.**
  - Use U.FL where space is tight (the tile taps).
  - Use MMCX for the half-dozen board-level taps that will be plugged most:
    rails, helper and TCXO.
  - Check stock with `jlc_api.py` when applying this; only C88374 has been
    used before.

**Silkscreen:** each tap named, with its ratio and the expected reading, as
the test points are: `S4 ÷21 into 50R`, `+3V3_A far ÷21`.

**Probe boards** (Jason: "a lot of 10x probe PCBs, with BNC to U.FL, though
this is maybe overkill"): with the ratio built into the board's own resistor,
a stock U.FL-to-BNC pigtail does the job. A separate probe board would only
earn its keep on a high-impedance node at high frequency, and none of the
taps above is one.

---

## The heater, and the pps inputs

### 20. Heater placement and the thermal layout: TEST RUNNING (RA2), priority 2

**Why.** Rev A's heater is three banks of resistors and FETs spread over the
board, ~9.6 W from its own 15 V jack. It was first switched on in round 45:

- It works, and fast. The sensors nearest units 1 and 2 (T48, T49) rose
  ~2 K within 90 s, while the helper's (T4E, centre) barely moved.
- It adds **no electrical noise**: the jitter, chatter and both rails were
  unchanged with it on, even from a cheap 15 V 6 A supply.
- **It moves a pair by heat, fast.** Unit 2 − unit 1 sat 3.0 ± 0.65 ps
  lower with it on.
  - A 70 s recording showed that shift arriving over 2-4 s and not
    reversing at switch-off: heat, not current.
  - So a heater near a squarer warms it within seconds, long before the
    nearest thermometer moves.

**RA2's result** (README 45.16):

- Full power warms the left edge 13.5-15 K, the right 8.7-11 K, and the
  helper's sensor 6.7-8.5 K: a 5 K gradient.
- The unit 1-2 pair moved +27.5 and +31.1 ps, settling in ~5 minutes.
- No slips at +14 K, and the rails stayed flat.
- Whether the channels respond to the mean temperature or to the gradient
  is RA7's question.

**What RA2 and RA7 decide together.**

- The board's own temperature coefficient, per pair, with the board heated
  ~10 K above the room while the SDG stays put (item 18).
- **Whether the channels warm evenly.** If they don't, rev B wants:
  - heaters equidistant from every squarer, or none near any;
  - a thermometer beside each squarer rather than in the margins;
  - the thermostat loop (the driver's slow PWM) holding the squarers'
    temperature, not the margin sensors'.
- Whether a heated board (a thermostat at, say, 35 °C) improves the night's
  ±10 ps pair stability enough to keep the heater at all.

**Keep regardless.**

- The heater's own jack, polyfuse, Schottky and TVS.
- The heater return on its own trace.
- The DAC that powers up off (EEPROM 0, round 45 confirmed it on the bench).

### 21. pps inputs: NO CHANGE

**Round 45** gave a pps input its first real pulses: CG-1 drove `P2` (unit 2)
with a 0-3 V square.

- Every edge was counted and timestamped at 10 ns.
- The thresholds, measured through the jack, are **1.88-1.98 V rising and
  1.27-1.37 V falling**. That is ≈1.75 V and ≈1.20 V at the 74LVC1G17,
  inside its datasheet ranges.
- The 51 Ω terminators stay DNP. Round 44 wrongly read them as fitted;
  `excluded_from_assembly.csv` says otherwise.
- The 1k/10k divider passes 3.3 V and 5 V pps with margin.
- **For rev B**: nothing to change in the circuit. Add the thresholds to the
  silkscreen limits at each pps jack: `pps: ≥ 2.3 V`. That is the
  datasheet's worst-case VT+ (2.08 V at 3.3 V) through the divider, against
  1.98 V measured. Move the Schmitts onto +3V3_D, as item 13 already says.
