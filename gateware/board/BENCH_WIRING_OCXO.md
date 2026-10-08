# The OCXO bench: rework, wiring and the tests before rev B

Round 45.19, 2026-10-08.  The bench now has a common 10 MHz: the BG7TBL
8-port OCXO distribution amplifier.  **Its left bank (ports 1, 2, 5, 6) feeds
the board; its right bank (ports 3, 4, 7, 8) feeds the instruments'
references.**  Three 33120As lock to it.  This file replaces `BENCH_WIRING.md`
sections A, C, D and G.  Its sections B (power, network), E1 (the CircuitGears
on the rails), F (hand tests) and H (don'ts) still hold.

Coordinates are the board's own, in mm from the top-left corner, as
`HANDBOOK.md` draws it.  On your bench the board's **top edge** (the `HO`/`HIN`
SMAs and the 1-Wire terminals) faces the 33220A, and its **bottom edge** (the
debug header J5001) faces the PYNQ and the generator stacks.

---

## 0. Today at a glance

| # | Who | What | Takes |
|---|---|---|---|
| 1 | me | shut the PYNQ down | 1 min |
| 2 | you | unplug the PYNQ's barrel jack and the 15 V heater supply, then **solder S1-S4** (§2) | ~60 min |
| 3 | you | **wire it** as §3, then tell me the OCXO port of each cable | ~20 min |
| 4 | you | power up: PYNQ barrel jack, then the heater supply | 1 min |
| 5 | me | **O0-O7** (§4), about 3 h, no hands | afternoon |
| 6 | you | **O8**, swap two cables at the OCXO and back again | 2 min, when I ask |
| 7 | me | **N1**, the night: RA7 with the heater stepped | overnight |

Tomorrow night: **N2** (RA5, HO at 4 mA; no hands).  Then **L1** if O7 asks for
it: the RA4 strap, which is one wire.

## 1. What is new since `BENCH_WIRING.md`

- **The OCXO, measured** (README 45.18): 6.0 Vpp open circuit, **~35 Ω source,
  3.4-3.5 Vpp (+14.7 dBm) into 50 Ω**.  Port 3 is 180° from ports 1 and 2, as
  your note says.  Harmonics ≥ 51 dB down.
- **Three 33120As with Option 001, all locked to it.**  Two are on RS-232
  ("top" and "bottom"), one on GPIB ("right").
  - The top and bottom HPs measured −0.001 ppb against an OCXO port, with
    10-22 ps rms of wander over 20 s.
  - All three, and the 33220A, power on in the default state.
- **The SDG** can lock to it: its rear `10MHz In/Out` is now an input (10MOut
  Disable).  Its outputs aren't needed on the board.
- **The SDS has no 10 MHz jack.**
- **The board's inputs, with the OCXO:**
  - **with the 50R jumper fitted: ~3.5 Vpp** at the SMA.  That is under the
    board's 4.1 Vpp ceiling but over the 3.3 Vpp bench cap;
  - **without the jumper: ~6 Vpp**, which is over the ceiling.  **Never
    connect the OCXO to an input without its jumper.**

## 2. Soldering

**Before you start.**  Tell me, and I shut the PYNQ down (`sudo shutdown`).
Then unplug the PYNQ's barrel jack and the 15 V supply from J2003.  The board
can stay on the PYNQ's header.

### S1. One more SMA: unit 10 (J1001), with its 50R header and a shunt

- **Where.** J1001, the jack marked `10`, at (164.1, 125.0): right-hand
  column, the fifth jack down.  Its 2-pin header JP1001 is at (152.9, 121.6).
- **Why.** RA7 wants four OCXO-fed units at the board's four corners:
  - **1** (top left), **2** (top right), **10** (lower right), **11** (lower
    left);
  - two in each column, and two near each end.
  - Then the heater's left-right gradient and any top-bottom one both show,
    and the room's even swings move all four alike.
  - Rev A's plan used unit 4 for this, but 4 sits 18 mm under 2, so only the
    left column saw top against bottom.
  - It also frees unit 4 for a locked generator (O5-O7).
- **Fit the shunt on JP1001.**

### S2. Park units 3, 6, 7 and 8: one 100 kΩ leaded resistor each

The same rework as unit 5 (round 45): from the squarer's gate node, the test
point `TPx02`, to pin 2 (GND) of that unit's 50R header `JPx01`, about 7.4 mm.

| Unit | From TP (gate node `S`) | To JP pin 2 (GND) | Why |
|---|---|---|---|
| 3 | TP302 (60.3, 59.7) | JP301 pin 2 (56.64, 66.1) | oscillates 29-30 of 30 since unit 5's park; a neighbour of unit 1 |
| 6 | TP602 (146.7, 92.4) | JP601 pin 2 (150.36, 86.0) | oscillated 30 of 30 (round 41); a neighbour of unit 4 |
| 7 | TP702 (60.3, 95.3) | JP701 pin 2 (56.64, 101.7) | sometimes; a neighbour of unit 9 |
| 8 | TP802 (146.7, 110.2) | JP801 pin 2 (150.36, 103.8) | oscillated 30 of 30; a neighbour of unit 10 |

- On the left column a header's pin 2 is to the right of pin 1, and on the
  right column to the left of it.  If the header isn't fitted, the hole will
  do.  The PCB file checks: every `JPx01` pin 2 is GND.
- **Why.** These units oscillate at ~560 kHz whenever undriven.  Each is a
  local aggressor that changes state with its neighbours: parking unit 5 woke
  unit 3.  Parked, they can't confound anything tonight.  Rev B parks every
  unused channel (item 11), so the bench board becomes more like rev B.
- **Leave alone:** unit 13 (never oscillated), unit 5 (parked already), and
  units 4 and 9 (generators drive them).

### S3. RA3: FB401's bridge becomes a 4.7 Ω 0805

- **Where.** Between FB401's pads, (142.76, 79.26) on the +3V3_A side and
  (142.76, 77.14) on the gate side.  Unit 4's squarer, right-hand column.
- **Why.** Rev B feeds every gate through a resistor instead of a bead
  (item 12), and this test picks the value.  O2 checks unit 4 stays quiet,
  and O7 measures what unit 4's state does to its neighbour, unit 2.
- **Skip it** if you don't have a 4.7 Ω 0805 (2.2-10 Ω will do; tell me which).

### S4. RA1: the XA drive, two 0805s by the TCXO

- **R3001, 3k3 → 1 kΩ**, at (101.25, 47.0), vertical; pads at (101.25, 46.09)
  (TCXO side) and (101.25, 47.91).
- **R3002, 1 kΩ → 330 Ω**, at (98.1, 49.4), horizontal; pads at (99.01, 49.4)
  and (97.19, 49.4) (GND).
- **Why.** Item 9: is the slow edge at the Si5351's XA what makes PLLA slip
  when CLK0 is at 4 mA?  O3 repeats the drive matrix, which doesn't depend on
  the input wiring, so round 45's matrix (`mods_20261007T2139Z`) is still the
  comparison.
- **Skip it** if it fights you: it is insurance for item 9, not a decision.

### More SMAs?  Only S1

- **What another SMA would buy:** a generator-driven unit.  There are already
  five locked outputs (three HPs, the SDG's two) for two free jacks (4 and 9).
- **What it costs:** a generator and a cable per unit, and another channel
  whose state changes.  Parking those units (S2) is cheaper, and it is what
  rev B does.
- **The one exception is S1**, because RA7 needs a fourth corner.
- **Unit 13 (J1301)** would give a third aggressor position, next to unit 11.
  Not needed.

### Jumpers after soldering

| Unit | Jumper | Source |
|---|---|---|
| 1 | JP101 **fitted** (as now) | OCXO |
| 2 | JP201 **fit it** (it is off now) | OCXO: **needs it** |
| 4 | JP401 fitted (as now) | top HP |
| 9 | JP901 **off** (as now) | bottom HP, set to ≤ 3.3 Vpp open circuit |
| 10 | JP1001 **fit it** (S1) | OCXO |
| 11 | JP1101 fitted (as now) | OCXO |
| 12 | JP1201 fitted (as now) | HO |

## 3. Wiring

### 3.1 OCXO left bank → the board, through tees on the scope

As before, put a **BNC tee directly on each scope input**: one cable from the
OCXO to the tee, a BNC-to-SMA from the tee to the board.

| # | OCXO port | Tee on | Board jack | Jumper |
|---|---|---|---|---|
| K1 | 1 | scope **CH1** | `1` (unit 1) | JP101 fitted |
| K2 | 2 | scope **CH2** | `2` (unit 2) | **JP201 fitted** |
| K3 | 5 | scope **CH3** | `10` (unit 10, S1) | **JP1001 fitted** |
| K4 | 6 | scope **CH4** | `11` (unit 11) | JP1101 fitted |

- **Four cables of the same type and length**, OCXO to tee.  Then four
  BNC-to-SMA of the same length, routed together.
  - Coax delay drifts with temperature, roughly 0.1-0.5 ps/K per metre.
    Unequal cables would put the room's swings into the pairs, and RA7 is
    after the board's own ~2.6 ps/K.
- **Pads (optional):** a 3 dB SMA attenuator at each board jack brings ~3.5 to
  ~2.5 Vpp.  Use them only if you have **four of the same value**.  Without
  them, 3.5 Vpp is inside the board's 4.1 Vpp ceiling.
- **Every port in one bank.**  Ports 1, 2, 5 and 6 are all the left bank, so
  all four are in phase.  O1 checks 5 and 6.

### 3.2 OCXO right bank → the instruments' references

| # | OCXO port | To | How |
|---|---|---|---|
| R1 | 3 | **SDG1032X** rear `10MHz In/Out` | **through a 50 Ω feed-through** (or a BNC tee with a 50 Ω terminator, or a 6 dB pad). Bare, it sees 6 Vpp. |
| R2 | 4 | **right HP** (GPIB 10) rear `10 MHz In` | direct (+14.9 dBm; its range is −10 to +15 dBm) |
| R3 | 7 | **top HP** (RS-232, `A9WV8RTV`) rear `10 MHz In` | direct |
| R4 | 8 | **bottom HP** (RS-232, `FTER3DQU`) rear `10 MHz In` | direct |

If the top and bottom HPs are already on two right-bank ports, leave them and
just tell me which.  A 3 dB pad on each HP would put it mid-range, but it
isn't needed.

### 3.3 Generators and HO → the board

| # | Source | Board jack | Notes |
|---|---|---|---|
| G1 | **top HP** OUTPUT (front) | `4` (unit 4) | the aggressor and AM-to-PM unit, right column, beside unit 2 |
| G2 | **bottom HP** OUTPUT | `9` (unit 9) | the same on the left column, beside unit 11. JP901 off |
| G3 | the board's `HO` (J3001) | `12` (unit 12) | **direct, no tee now** (CH3 is the OCXO's); the slip check reads its beat |
| G4 | **right HP** OUTPUT | **nothing**: unplug it from unit 11 | a spare locked source |
| G5 | SDG outputs 1 and 2 | **nothing** | outputs off; locked, as a spare |
| G6 | 33220A | **nothing**: it is off unit 4 | free-running; leave it on the LAN, output off |

- **Units 4 and 9 change source:**
  - unit 4 goes from the 33220A to the top HP;
  - unit 9 goes from CG-2's generator to the bottom HP (so **E2b goes**).
- I set every HP's amplitude before anything is driven.  Until then they sit
  at their power-on 1 kHz, 0.1 Vpp, which is harmless anywhere.

### 3.4 The scope

| Channel | What | Settings (I set them) |
|---|---|---|
| CH1 | tee of K1 (port 1, unit 1) | 1 MΩ, DC, 1×, 1 V/div |
| CH2 | tee of K2 (port 2, unit 2) | same |
| CH3 | tee of K3 (port 5, unit 10) | same |
| CH4 | tee of K4 (port 6, unit 11) | same |

The scope logs each OCXO line's amplitude all night.  The squarers convert
amplitude to phase at −150 to −230 ps/dB (item 18), so a port that drifts
0.01 dB moves its unit 2 ps.  RA7 has to see that, to tell it apart from the
board.  **Never set a channel to 50 Ω while it sits on a tee to the board.**

### 3.5 Unchanged

- **B**: power, network, console; the 15 V supply in J2003 for the heater.
- **E1**: CG-1 A on +5V_HDR (J5001 pin 1), CG-1 B on +3V3_A (pin 5), CG-2 A
  on +3V3_D (pin 7).
- **E2a**: CG-1's generator on `P2` (unit 2's pps), teed to CG-2 B.  Off.
- **The probe** in J6001.  Optional: tape it to the OCXO amplifier's case, so
  the night logs the OCXO's temperature as well (RA7's room-swing part).
- **Keep the board out of the sun** for the night: the blinds are behind it.

### 3.6 Map of the board, with today's assignments

```
 board's top edge (HO, HIN, 1-Wire terminals): toward the 33220A
        left column, x = 42.9                 right column, x = 164.1
 y  44.9  [ 1] OCXO port 1 (K1)
 y  53.8                                      [ 2] OCXO port 2 (K2), JP201 fit
 y  62.7  [ 3] parked (S2)
 y  71.6                                      [ 4] top HP (G1); 4.7 ohm (S3)
 y  80.5  [ 5] parked (round 45)
 y  89.4                                      [ 6] parked (S2)
 y  98.3  [ 7] parked (S2)
 y 107.2                                      [ 8] parked (S2)
 y 116.1  [ 9] bottom HP (G2), no jumper
 y 125.0                                      [10] OCXO port 5 (K3): new SMA (S1)
 y 133.9  [11] OCXO port 6 (K4)
 y 142.8                                      [12] HO (G3)
 y 151.7  [13] null channel, undriven (quiet)
 board's bottom edge (J5001): toward the PYNQ and the generator stacks
```

## 4. The tests

O = today, with nobody at the bench unless it says **hands**.  N = a night.
L = later.  Each says what it decides for rev B (`REVB_CHANGES.md` item).

### O0. The wiring check (10 min)

- Every instrument answers.
- **Each HP is locked:** its Questionable Data bit 6 is clear, and its unit
  beats at exactly the OCXO's rate.
- **Every driven unit beats:** 1, 2, 4, 9, 10, 11, 12.
- The scope sees four OCXO lines at ~3.5 Vpp (~2.5 with pads).
- The CircuitGears read their rails, and the probe answers.
- Nothing is changed.

### O1. The OCXO at the board (10 min)

- **What.** The six pairs among units 1, 2, 10 and 11, over 5 minutes.
- **Gives.**
  - Each pair's mean offset (cable plus port plus channel), and whether ports
    5 and 6 are in phase with 1 and 2.  A 180° port would show as 50 ns.
  - **The board's floor with no generator in any pair:** per-transition rms,
    and the pair's deviation at 1-100 s.  Round 45's SDG-fed unit 2 − unit 1
    was 32 ps rms per transition.
- **Decides.** The baseline every other test is read against.

### O2. Quiet when undriven (20 min): parks (S2) and RA3 (S3)

- **What.** `unplugged.py 30 1,2,9,10,11,12`, with the top HP at 0 V DC, so
  unit 4 is undriven.
- **Passes if** units 3, 5, 6, 7 and 8 are quiet 30 of 30 (parked), and unit 4
  is quiet with 4.7 Ω, as it was with the bridge.
- **Decides.** Item 12's resistor value, and item 11's park on every unused
  channel at once.

### O3. RA1, the drive matrix (30 min)

- **What.** CLK0 and CLK1 each at 2, 4, 6 and 8 mA; slips per second at each
  of the 16 settings; then back to the standard (CLK0 2 mA, CLK1 8 mA).
- **Against.** `mods_20261007T2139Z`: CLK0 at 4 mA slipped 865-1711 per
  second whenever CLK1 was at 4 mA or more.
- **Decides.** Item 9's weight.
  - **Clean at CLK0 4 mA**: the slow XA edge was the mechanism; CLKIN removes
    it, and the layout rules are insurance.
  - **Still slips**: supply and ground coupling too, so the separate VDDO
    banks and the guard ring matter as much as CLKIN.

### O4. AM-to-PM on units 4 and 9 (40 min): RA6, item 18

- **What.** Each HP at 10 MHz, stepped ±1 dB in 0.25 dB steps around its
  working level.  Unit 4 is terminated (JP401), unit 9 is not (JP901).  Read
  against the OCXO units, which nothing moves.
- **Against.** T3: unit 1 −231 ps/dB (terminated), unit 2 −147 ps/dB
  (unterminated), both read against the SDG, which wanders.
- **Decides.** Item 18 on two more units, with a reference that doesn't
  wander.
  - Is the spread between units bigger than between terminations?
  - Could a per-channel calibration replace the replica bias, or not?

### O5. Crosstalk with exact offsets (40 min): item 13

- **What.**
  - The top HP at 10 MHz + 0.5 Hz, then + 5 Hz, on unit 4; then the bottom
    HP the same on unit 9.
  - HO's drive at 2, 4, 6 and 8 mA and off.
  - The tone each puts into each OCXO pair, ps peak.
- **Against.** T2: no tone above 0.4 ps, but the floor then was the SDG's.
  This floor should be several times lower.
- **Decides.** Item 13: whether a neighbour at 18 mm couples at all, and how
  much more the near pair (4 → 2, 9 → 11) sees than the far ones.

### O6. HO's drive and the floor (15 min): item 10

- **What.** Per-transition jitter of the OCXO pairs, with HO at 2, 4 and 8 mA
  and off.
- **Against.** T2: 28.3 ps (off) to 32.7 ps (8 mA), on SDG pairs.
- **Decides.** Item 10's drive level, measured without the SDG's own jitter.
  N2 confirms it over a night.

### O7. A neighbour's state (20 min): T1 with RA3

- **What.** The top HP toggled between 10 MHz and 0 V DC every 90 s, 8 times.
  The step that unit 4's state puts on unit 2 (its neighbour) and on the
  others.
- **Against.** T1: +1.90 ps with the bead, +1.39 ± 0.38 ps with the bridge.
  Also changed since then: parks, and OCXO pairs in place of SDG ones.
- **Decides.**
  - **A step under ~0.5 ps**: local RC plus parking isolates neighbours.
  - **Still ~1.4 ps**: it is the shared +3V3_A, item 5's plane is the fix,
    and **L1** (the strap) shows it.

### O8. The port swap (hands: 2 min)

- **What.** At the OCXO, swap the cables of ports 1 and 6 (units 1 and 11)
  for 5 minutes, then swap them back.
- **Gives.** Pair 11 − 1's offset flips by the two ports' difference.  That
  separates what is the port from what is the channel, and checks the ports
  hold still.
- **Decides.** Whether RA7's per-channel numbers can be trusted to the
  picosecond.

### N1. The night: RA7 (items 18 and 20)

- **What.** `overnight.py` with the heater stepped as in RA2: off 1 h, on 3 h,
  off 3 h, on 3 h, then off.  It logs:
  - the six OCXO pairs;
  - units 4 and 9 (HPs at exactly 10 MHz, locked: no beat tone, and no
    undriven unit 9);
  - unit 12 (slips);
  - the eight board thermometers, the probe, the rails and the heater;
  - the four OCXO lines' amplitudes.
- **Against.** RA2: +27.5 and +31.1 ps for ~11 K on SDG pairs.  The heater
  runs the left edge ~5 K hotter.
- **Decides.** Item 20 against item 18.
  - The heater warms the four corners in different proportions, and the room
    warms them alike.
  - **If the pairs follow the gradient (model B)**: thermal symmetry and an
    even heater are the fix (item 20).
  - **If each channel has its own coefficient on the mean (model A)**: the
    replica bias is the fix (item 18).
  - The heater steps are the clean part, because the OCXO and the cables stay
    at room temperature.

### N2. Tomorrow night: RA5 (item 10; no hands)

HO at 4 mA (`./pynq-run si_set.py 2 4`) for the whole night, in the same
wiring.  Against N1.  It decides whether rev A's firmware moves to 4 mA now,
and rev B's HO drive.

### L1. Later, if O7 asks: RA4, the +3V3_A strap (one wire)

An insulated AWG 22-24 wire, ~60 mm, from C2003 pad 1 (122.00, 7.95) to FB201
pad 1 (142.76, 61.46).  Then O7 again.  It decides whether the shared rail is
the coupling path, which item 5's plane removes.

### Which test decides which rev B item

| Rev B item | Decided by |
|---|---|
| 5 +3V3_A plane (priority 1) | O7, L1 |
| 9 Si5351C, CLKIN (priority 1) | O3 |
| 10 HO isolated, 2-4 mA (priority 1) | O5, O6, N2 |
| 11 park unused channels (priority 1) | O2 |
| 12 RC gate filters (priority 1) | O2, O7 |
| 13 crosstalk rules | O5 |
| 18 replica-biased squarers (priority 1) | O4, N1 |
| 20 heater and thermal layout | N1 |

## 5. What I change in the scripts (while you solder)

- `bench_setup.py`: the new sources.
  - The top and bottom HPs over RS-232 by their `/dev/serial/by-id` names, and
    the right HP on GPIB.
  - The SDG's outputs off and its clock on External (after R1).
  - The 33220A off.
  - Amplitudes: the top HP into unit 4's 50 Ω, the bottom HP ≤ 3.3 Vpp open
    circuit into unit 9.
- `overnight.py`, `crosstalk.py`, `toggle_test.py`, `xcheck.py amp`: units 1,
  2, 10 and 11 as the reference set.  The top and bottom HPs replace the SDG,
  the 33220A and the GPIB HP as the sources they step.
- `bench_wiring.csv`: this file's tables.

## 6. Don'ts (additions to `BENCH_WIRING.md` H)

- **No OCXO port into a board input without its 50R jumper.**
- **No OCXO port bare into the SDG**: through 50 Ω.
- The HPs have no output switch.  "Off" is 0 V DC (`off()`), which still
  terminates the line in 50 Ω.
- Don't move the four OCXO cables during N1.
