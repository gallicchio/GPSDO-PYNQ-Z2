# Rev B changes

Everything planned for the next JLCPCB order, collected in one place so it is
applied **all at once**.

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

### Rev A boards: reworks

The tag is the board as JLCPCB built it. Anything done to a physical board
since goes here, so that every later measurement can be read against the
right hardware.

| date | board | change | why | result |
|---|---|---|---|---|
| — | — | none yet | CLK0 at 2 mA (round 40) is firmware, not a rework | |
| pending | | FB401 bridged | item 12 | |
| pending | | R3001 3k3 → 1k, R3002 1k → 330 Ω | item 9 | |

Round 42 has the bench list for before and after each rework.

---

Each item says why (with the round where the evidence is), what, and where it
stands:

- **IN GENERATOR**: already changed in `gen/` or `pcb/`; takes effect when
  rev B is built.
- **PLANNED**: agreed, not yet applied.
- **TEST ON REV A FIRST**: a rework or measurement on the rev A board decides
  it.
- **OPEN**: a choice still to make.

Rev A experiments come **after** everything that can be learned from the board
as it is (round 41).

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

### 3. 1-Wire colour labels at each screw, just under the terminal: PLANNED

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

### 5. A real +3V3_A plane: PLANNED

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

**What.**

- A +3V3_A pour or plane on an inner layer, fed from the LDO at one point
  near the middle of the board.
- Keep In1 as the unbroken GND reference.
- Correct the docstring.

### 6. Rail indicators with "in range": PLANNED

- One LED per rail to show it exists: +5 V, +3V3_A, +3V3_D and the heater
  input.
- A **TPS3700** window comparator per rail (LCSC C2869617), set by a divider to
  about ±4 %. Its open-drain outputs, wire-ORed, light a green "OK" LED only
  inside the window.
- Drive every LED from +5 V, not from the analog rail.

### 7. Rail monitoring: PLANNED (recommended)

An **INA3221** (LCSC C181255) measures three rails' voltage *and current* over
I²C, through 0.1 Ω shunts on +5 V in, +3V3_A and +3V3_D. The PYNQ then logs
rail voltages and load currents with the measurement. Round 41's question
about an overloaded LDO would have taken one read.

### 8. LDO load and squarer current: TEST ON REV A FIRST

- Rev A's +3V3_A carries ~180 mA, within the TPS7A2033's 300 mA. The part
  was never overloaded; the 3.15 V was distribution drop (item 5).
- Most of that load is unplugged squarers biased at their threshold. Parking
  them (item 11) removes it.
- Candidate lower-current squarer: **74AUP1GU04**. It is pin-compatible and
  built for low-power crystal oscillators. Try one channel on rev A and
  compare edge scatter and supply current.

---

## The helper synthesiser

### 9. A Si5351 that works with margin: PLANNED, the Si5351C with the TCXO on CLKIN

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

### 10. Isolate HO: PLANNED

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

---

## The channels

### 11. Park an unused channel: PLANNED

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
- **Option**: an I²C port expander driving the thirteen 100 k resistors, so
  the PYNQ parks empty channels itself.
- **Not recommended**: a permanent offset on every squarer. It brings back the
  amplitude sensitivity the self-bias removes.

### 12. No resonant supply filters on the gates: TEST ON REV A FIRST

**Why.** Every gate is fed through its own 600 Ω@100 MHz bead into
100 n + 10 n. A ~0.7-1 µH bead with 110 nF resonates at ~0.5-0.6 MHz, where the
unplugged squarers oscillate.

**Test.** Bridge **FB401** (unit 4's squarer bead, at (142.8, 78.2)), then run
`./pynq-run unplugged.py 30 1,2,11,12`. The baseline is unit 4 oscillating
30/30 at 557.1 kHz (round 41). If it goes quiet 30/30, the bead is the cause.

**Then.** Feed the gates through 2.2-10 Ω resistors (RC, no resonance),
especially the squarers.

### 13. Crosstalk: PLANNED

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

**Rules for rev B:**

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

---

## Build environment

### 14. Tools on this machine: NOTE

- `build.py` expects KiCad 9 extracted at `~/.local/kicad9/squashfs-root`.
  This machine has the AppImage (`~/.local/bin/kicad-9.0.9.1-x86_64.AppImage`),
  whose kicad-cli runs directly.
- `pcb/build_pcb.py` now takes `KICAD9_FOOTPRINTS` for the stock library
  path.
- Set `KICAD_CLI` and `KICAD9_FOOTPRINTS`, or extract the AppImage where
  `build.py` expects it, before the rev B build.

---

## Firmware and gateware (not the PCB, but ship with rev B's bring-up)

### 15. Deglitch the beats in `dmtd_capture.v`: PLANNED

Real beats chatter, mostly because of HO (item 10). The core keeps the *last*
rising edge, so a timestamp can come from the falling transition's bounce,
half a beat period away. Add design log §10's K-of-K deglitcher and first/last
edge sums.

### 16. Monitor and log the Si5351 during long runs: PLANNED

Your requirement, round 41:

- Log the **sticky LOL/LOS bits**. `Si5351.sticky()` and `clear_sticky()` are
  in the driver; `bringup.py` clears them after programming and reports them.
- Log **pair-register slips** (`helper_slips()`, `si_watch.py`) for the
  whole multi-day run.

A continuous **hardware slip counter** in the gateware would beat software
sampling: count 1024-helper-cycle intervals whose PS-clock length is off by a
reference period.  Today `si_watch.py watch` covers ~78 % of the time (round
42: 60 s of polling in every ~77 s).  With the Si5351C (item 9), its INTR pin
can also latch LOL/LOS in hardware.  Round 40 showed those flags miss the
slips, so INTR is a supplement, not a substitute.

### 17. The ps-per-cycle scale from the measured beat: PLANNED

`T_RES_PS` assumes the design beat. A TCXO 2.5 ppm off moves it by 2 %.

Round 43 measured it:

- With the Siglent as the source, the beat period was 8031-8040 helper
  cycles, not 8102. That is **12.44 ps per cycle, 0.8 % off the design's
  12.3425**, enough to misreport a 16.7 ns phase step by 130 ps.
- Counting beat cycles instead, as `xcheck.py` does, needs no constant. It
  read the generator's phase steps with a slope of 1.00013 and a 0.05 Hz
  ramp to 2 ppm.

### 18. The squarer's amplitude-to-phase conversion: PLANNED

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

---

## Probing without holding a probe

### 19. U.FL or MMCX monitor taps on every analog node worth a look: PLANNED

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
