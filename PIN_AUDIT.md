# GPSDO-PYNQ-Z2: pin audit (2026-11-16)

Done to `~/OpticsPCBs/tools/pin_audit/BRIEF.md` (CLAUDE_PCB.md, "Two checks no board ships without" and section
10, gates 2a-2c), on both revisions:

- **Rev A**: the two bench boards JLCPCB built (ordered 2026-09-15, tag `GPSDO-PYNQ-Z2-revA` = `0f9a4dd`). It is
  the board that was brought up.
- **Rev B**: ordered 2026-10-22 (JLCPCB order SMT026101160736). It is the working tree.

Every claim below was re-derived from the data sheets and the netlists. None of it comes from the README, the
schematic notes or an earlier review.

## Red flags

| severity | board | finding | evidence | on a built board | workaround / rework |
|---|---|---|---|---|---|
| **HIGH** (latent; BLOCKER if fitted) | rev A and rev B | **All 13 BAV99 input clamps (D101 ... D1301, DNP) are wired backwards.** Pin 1, the anode, goes to +3V3_A, and pin 2, the cathode, goes to GND. A fitted clamp is therefore two forward-biased diodes across +3V3_A, not a clamp. | Netlist (both revisions): `D101.1 -> +3V3_A`, `D101.2 -> GND`, `D101.3 -> Net-(C101-Pad2)` (the gate node behind the 10n), and the same on all 13 units. `BAV99LT1-D.txt:12-16` "ANODE 1 / CATHODE 2 / 3 CATHODE/ANODE", and `:244-246` Style 11 "PIN 1. ANODE 2. CATHODE 3. CATHODE−ANODE". The Diodes `BAV99.pdf` p.1 internal schematic (rendered) agrees. The cached `Diode:BAV99` symbol *names* pin 1 "K" and pin 2 "A", but its *drawing* makes pin 1 the anode and pin 2 the cathode. `gen/sheet_unit.py:170-176` and README 21.1.2 ("Correct") followed the names. The project's `check_paths.shunt_diodes()` skips 3-pin diodes. | **Nothing yet**: D?01 is DNP on both revisions, and rev A's rework log fits none. But `mfg/release/excluded_from_assembly.csv` says to fit one "on a channel run UNTERMINATED above ~6 Vpp". Fitting one puts 3.3 V across two series diodes, hundreds of mA. U2001 goes into current limit (360 mA minimum), which collapses +3V3_A for all 13 channels. The SOT-23 overheats, and the gate node is pinned near 1.65 V, so the signal is shunted. The protection the clamp exists for (a hot unterminated source driving the gate over its 6.5 V absolute maximum) does not exist on either revision. | **Never fit a BAV99 at D?01.** If a clamp is needed on a built board, fit two small-signal diodes by hand: one with its anode on pad 3 (the node) and its cathode on pad 1 (+3V3_A), and one with its anode on pad 2 (GND) and its cathode on pad 3. Until then, use the 50R jumper for hot sources. Next revision: in `sheet_unit.py`, wire `d.pin(2)` to RAIL_A and `d.pin(1)` to GND, and make `shunt_diodes()` read series pairs by the data sheet's pin numbers, not by the symbol's pin names. |
| MEDIUM (known) | rev B | **+3V3_A's load can exceed U2001's rating.** There are 13 always-biased replica gates, and idle unparked squarers add to them. Together they draw 290-420 mA, against the TPS7A2033's 300 mA recommended maximum and its 360 mA minimum current limit. F2001 (500 mA hold) then sees up to ~520 mA. Rev A measured 180 mA. | `TI_TPS7A20xx_LDO.txt:233` "IOUT Output current 0 300 mA" and `:338` "ICL Output current limit 360 520 730 mA". The author's own budget is in README round 45.32 (~line 15929) and the power sheet's CURRENT BUDGET note. | With every JP on PARK, or on 50R with its source running, the load is 160-250 mA, which is fine. With unparked channels that have no source, +3V3_A can fold back and F2001 can trip when warm. | Procedure: all 13 shunts on PARK at power-up (handbook). Next revision: more LDO current on +3V3_A (a 500 mA part, or split the rail). |
| LOW (uncertain) | rev B | **FO_VDD and SI_VDD have thin margins behind their 4R7s.** FO_VDD feeds both LMK1C1108s and U3003 through R3055 \|\| R3056 = 2.35 Ω, and comes out at ≈3.15 V worst case against the LMK's 3.135 V minimum, a margin of ~10 mV. SI_VDD (the Si5351C core) comes out at 3.05 V against 3.0 V, a margin of 50 mV. | `TI_LMK1C1108.txt:227` "3.3-V supply 3.135 3.3 3.465" and `SiLabs_Si5351ABC.txt:405-406` "3.0 3.3 3.60 V". The arithmetic is in `boards/GPSDO-PYNQ-Z2_revB.py` RAILS. The currents are estimates (12.9 mA a self-biased gate, from rev A; the LMK currents scaled from the 100 MHz figures). | Probably fine: a typical LDO and typical currents give ~3.2 V. Rev B is not yet measured. | Measure FO_VDD at C3010 and SI_VDD at C3003 with the helper running. If FO_VDD reads under ~3.17 V, replace R3055/R3056 with 1R0 each. 2 x 1 Ω still damps the filter, which was item 12's reason for using 4R7. |
| LOW (uncertain) | rev A and rev B | **The heater FETs may not be fully on.** Q2001-Q2003 (DMN6068SE) get at most ~3.3 V of gate drive (U5009's VOUT ≤ VDD = +3V3_D), but their VGS(th) can be as high as 3.0 V, and RDS(on) is specified only at 4.5 V and 10 V. "Fully on at 3.3 V" (README 28.4) is therefore not guaranteed for a worst-case part. | `DMN6068SEQ.txt:230` "Gate Threshold Voltage VGS(TH) 1.0 3.0 V" and `:9-11` "68mΩ @ VGS = 10V", "100mΩ @ VGS = 4.5V". The netlist has HTR_DRIVE = U5009.1 via R5001 100R to Q2001-3.1. | Rev A's heater works (REVB_CHANGES rework log, 2026-10-07). A high-Vth part would leave its bank partly on: less heat, and up to ~0.8 W in the FET, which README 28.4 shows is safe. | None needed on rev A. Next revision: a FET with RDS(on) specified at 2.5 V, or the op-amp current sink that README 28.4 called "a Rev B change". It is not in rev B. |
| LOW | rev B | **HO OUT asks its buffer for more current than recommended.** U3002 (74LVC1G125) drives HO OUT through 33R into the instrument's 50 Ω, DC coupled. That asks for ~33 mA while high, past the buffer's recommended IOH of -24 mA at 3.0-3.6 V (absolute maximum ±50 mA). | `TI_sn74lvc1g125.txt:207-209` "IOH High-level output current ... –24" and `:157` "IO Continuous output current ±50 mA". The netlist has U3002.4 -> R3002 33R -> J3001. | It works, but outside the recommended conditions: ~1.6 Vpp at the load, with large current edges near the helper. | R3002 33R -> 68-100R (~1.0-1.3 Vpp into 50 Ω), or AC-couple HO. |
| INFO | both | **The PYNQ-Z2 user manual contradicts the PYNQ-Z2 schematic on the Raspberry Pi header.** The manual's Table 22 (p.30) swaps header pins 7/8, 10/29, 18/31 and 22/26, and calls pin 1 GND. The board follows the schematic. All 28 signal pins agree between `gen/design.py` HEADER, both netlists and `gateware/xdc/pins.xdc`. | `TUL_PYNQ_Schematic_R12.txt:344-363` "JA1_P ... R688 ... RPIO_04_R" (pin 7 = Y18), and so on; `:338-339` RP_IO16/17 -> RPIO_08/25. | Correct as built. Rev A's beats, pps and helper all work through it. | Do not "fix" the map from the manual. |

The analog sign of the channel chain was traced through the netlist. The squarer U?01 inverts (1Y = NOT 1A). FF1
and FF2 (74LVC1G80) both output ~Q (`sn74lvc1g80.txt:139` "Q 4 O Inverted output"). So FF1 D to BEAT is
non-inverting, as `sheet_unit.py` claims ("the two stages restore the sense"). Overall, BEAT = NOT(input) sampled
twice. The helper path is the same in every channel: CLK0 -> 10n -> U3003 (inverting) -> LMK1C1108 (non-inverting)
-> FF clocks, so FF1 samples on CLK0's falling edges. Both inversions are common to all 13 channels, including the
null channel 13, so they cancel in channel differences. Rev A is the same, with 74LVC1GU04 and 74LVC1G34 in place of
these parts.

## What was covered

| | rev B (`build/netlist.net`) | rev A (exported from the tag) |
|---|---|---|
| ICs with a data-sheet table | 69 (11 part numbers) | 71 (10 part numbers) |
| supply pins checked by voltage (VCC/VDD/V+/VDDOx/IN/OUT) | 79 | 74 |
| ground pins | 74 | 72 |
| must-be-unconnected pins (NC, Si5351C XA/XB) | 16 | 33 |
| enable and strap pins on a known rail (LDO EN, OEB, OE#, 1G, address straps) | 33 | 29 |
| power rows in total, failures | 202, 0 | 208, 0 |
| differential pairs | **none exist** (no USB, LVDS, TMDS, Ethernet, CAN, RS-485, differential clock or differential analog) | none exist |
| single-ended connector-to-chip traces by pin function | 142, 0 fail | 124, 0 fail |
| rows from MEMORY (not checked against a data sheet) | **0** | **0** |
| quoted data-sheet lines machine-checked against the text | 68 | 46 |

- **The rails were derived from their sources:**
  - TPS7A2033 fixed output, ±1.5 % (+3V3_A, +3V3_D);
  - the PYNQ-Z2's VCC5V0 on header pins 2/4;
  - the diode, PPTC and bead drop to the LDO input;
  - LDO_EN through R2025 (R2026 is DNP);
  - the I·R drop of every 4R7 feed.

  Rev A's measured values (4.87-4.90 V header, 4.41 V LDO input, 3.286/3.298 V LDO outputs) fall inside them. No
  rail's name disagrees with its derived voltage. +3V3_A reads 3.09-3.19 V at the far end of rev A's tracks, a
  distribution drop; every load there accepts down to 1.65 V.
- **The traces cover:**
  - every 10 MHz SMA to its squarer;
  - every TAP SQ to squarer 1Y and FF1 D;
  - FF1 ~Q to FF2 D;
  - every FF clock to an LMK output;
  - every 1pps SMA to its Schmitt input (pin 2, not Y);
  - each `beat[i]` / `pps[i]` header pin in `pins.xdc` to unit i+1's own FF2 / Schmitt (the gateware's channel
    order against the board);
  - the helper chain, the TCXO to CLKIN, the REF and CLK0 taps, HO;
  - the heater drive, the five 1-Wire probes;
  - I2C SDA/SCL from header pins 3/5 to each of 11 devices, each with the opposite line forbidden.
- **Pin numbers chosen by number** (the generator's `x.pin(N)` calls, `design.HEADER`, `FF_D_PIN/FF_CLK_PIN`). Every
  IC pin in both netlists was read against its data sheet's table by function:
  - SN74LVC2GU04 DCK;
  - SN74LVC1G80, 1G17, 1G125 and 1GU04/1G34 DBV;
  - LMK1C1108 PW (all 16 pins);
  - Si5351C QFN-20 (all 21) and Si5351A MSOP-10;
  - TMP1075 SOIC-8, MCP4725 SOT-23-6, DS2482-100 SO-8;
  - TPS7A20 DBV;
  - the Fox FT5HN TCXO, whose pin 1 is a true GND, not an enable.

  All agree, except the BAV99 above. The header map is in the INFO row.
- **Discretes:**
  - SS34 ×3: K on pad 1, pointing to the load; correct OR-ing and reverse-polarity protection.
  - SMAJ18A (unidirectional): K to +15V_HTR. The 5.6 V zener D2003: K to the 5 V node. PESD5V0S1BA: bidirectional.
  - DMN6068SE: 1 G, 2 D (tab), 3 S, from the "Pin Out – Top View" drawing.
  - BAV99: wrong (above).
  - There are no LEDs.
- **Logic levels:**
  - The beats, pps and helper are 3.3 V LVC driving LVCMOS33 Zynq pins through the PYNQ's 200 Ω.
  - The pps inputs get ≤ 4.55 V into an LVC input rated 0-5.5 V.
  - HCLK (LMK on FO_VDD) drives 74LVC1G80 clocks: VIH 2.0 V.
  - TCXO VOH ≥ 80 % VDD ≈ 2.57 V, against Si5351 CLKIN VIH 0.7·VDD ≤ 2.35 V.
  - I2C is pulled up by 2k2 to 3.3 V on the PYNQ (R305/R306), plus the FPGA's PULLUP.
  - Back-powering an unpowered Zynq is prevented: LDO_EN comes from +5V_HDR, and R2026 is DNP.
- **Enables and straps:**
  - None floats: LDO EN, Si5351 OEB, 74LVC1G125 OE#, LMK 1G, TMP1075 A0-A2, MCP4725 A0, DS2482 AD0/AD1 are all on
    known rails.
  - The I2C addresses are unique: Si5351 0x60, MCP4725 0x61 (A0 high), DS2482 0x18, TMP1075 0x48-0x4F.
  - Unused Si5351 XA/XB float, as its data sheet asks (`:1421`).
- **Regulators:** TPS7A2033 ×2.
  - Input 4.10-5.10 V, inside 1.6-6.0 V.
  - Dropout 145 mV at 300 mA, against ≥ 0.75 V of headroom.
  - At 250 mA it dissipates 0.28 W, which is +52 °C at RθJA 187 °C/W. That is acceptable.
  - Its load is the MEDIUM row.

## What was not checked, and why

- **Footprint pad geometry** was not checked against each land pattern. Spot checks only:
  - J4001's underside socket is the same footprint at the same place as rev A, which works;
  - the BAV99 SOT-23 numbering;
  - the Fox pad numbering against its drawing.
- **The PYNQ-Z2 balls for header pins 8, 10, 11, 13, 15, 16, 18, 19, 21, 23, 33, 35, 37 and 40** could not be traced
  through the schematic's text, which is mangled by its layout. They rest on rev A's bring-up, where every beat, pps
  and the helper clock worked.
- **The FO_VDD, SI_VDD and +3V3_A currents** are estimates. Nothing on rev B has been measured.
- **Out of scope:** the gateware's logic, the Si5351's register settings (drive strengths), the 1-Wire probes' wire
  colours, and the JLCPCB CPL rotations.
- **The engine has limits, worked around in the configs:**
  - pin_audit treats DNP parts as fitted, which matters for R2026; LDO_EN is pinned in RAILS.
  - Its `_ohms()` does not read the RKM code "4R7", so the ≤10 Ω inheritance never fires on rev B's 67 4R7 feeds.
    Each sub-rail is listed with its own drop.
  - `walk()` crosses resistors of any value, so the 1M/100k bias ends appear in the reach lists.

## Where the configs and outputs are

- `~/OpticsPCBs/tools/pin_audit/boards/GPSDO-PYNQ-Z2_revB.py` and `GPSDO-PYNQ-Z2_revB.out`. It uses the project's
  `build/netlist.net`. That netlist is current: a fresh `kicad-cli` 10.0.7 export of the working-tree schematics,
  which are identical to the order commit `cdd6947`, matches it in all 661 parts, 376 nets and every pin.
- `~/OpticsPCBs/tools/pin_audit/boards/GPSDO-PYNQ-Z2_revA.py` and `GPSDO-PYNQ-Z2_revA.out`. Its netlist was exported
  with KiCad 9.0.9 from `git archive GPSDO-PYNQ-Z2-revA` into the auditor's scratch area. The config's docstring
  gives the commands to re-export it.
- The data-sheet text that the quotes cite is `pdftotext -layout` of `datasheets/*.pdf`. Two TI data sheets were
  fetched from ti.com: SN74LVC2GU04 (SCES197N) and SN74LVC1G125 (SCES223U).

## Check 3: connectors against their drawings (2026-11-16)

Brief: `~/OpticsPCBs/tools/pin_audit/BRIEF_CONNECTORS.md` (CLAUDE_PCB.md top block item 3, gate 2d). Both revisions
were checked from their placed pads:
- **rev A**: `git show GPSDO-PYNQ-Z2-revA:GPSDO-PYNQ-Z2/GPSDO-PYNQ-Z2.kicad_pcb`;
- **rev B**: the working tree.

The script's pad positions agree with KiCad's IPC-D-356 export to 0.002 mm on every pad (1540 on rev A, 1762 on rev
B), J4001 on the underside included. Every non-SMA connector that both revisions share sits at the same place,
rotation and side on both.

### Red flags

| severity | board | connector | finding | evidence | on a built board | workaround / fix |
|---|---|---|---|---|---|---|
| — | rev A, rev B | — | **No BLOCKER, HIGH, MEDIUM or LOW.** Every connector below agrees with its drawing. | `connectors/GPSDO-PYNQ-Z2.out` (0 FAIL) | — | — |
| INFO | (the PYNQ-Z2's docs) | J4001's partner, the PYNQ's RPI_IDE | TUL's user manual (`datasheets/pynqz2_user_manual_v1_0.pdf` p.30, Table 22) marks PYNQ pin 1 "G". The schematic (`TUL_PYNQ_Schematic_R12.pdf` p.4, RPI_IDE) has VCC3V3 on pins 1 and 17. | J4001 pads 1 and 17 are unconnected (silk "nc"). | None. | Believe the schematic. |
| INFO | rev A, rev B | J2003 | KiCad's generic `BarrelJack_Horizontal` puts the switch pad 3.00 mm from the back terminal. XUNPU's DC-005-A200 drawing puts the switch terminal 2.65 mm from it (13.75 − 11.10). The 0.35 mm sits inside the 3 x 0.8 mm slot, and the pad is unconnected. | Pads 1 (184, 16) and 3 (179.3, 13); XUNPU drawing below. | None: the built boards took the part. | None needed. |
| INFO *(uncertain: a listing photo)* | rev A, rev B | J6001-J6005 | The board's legend "yel = DATA red = VCC blk = GND" matches DROK's listing image of the probes' lead (`datasheets/DROK ... Probes 3.avif`: yellow DATA, red VCC, black GND). The labels do not sit over their screws. "red" is 1.9-2.0 mm off pin 2's column: toward pin 1 on most terminals, toward pin 3 on J6001 (both revisions) and on rev A's J6005. "yel" is 1.5 mm off pin 1. So the labels are read by their order, not their alignment. | The labels sorted left to right against pins 3, 2, 1 (below). | None, if the bought probes follow the listing. | Buzz a probe's red lead to its sensor's VDD leg, or read 3.3 V on it once fitted. |

### What was checked (counts, each revision)

- **J4001, the 2x20 socket on the underside, mated with the PYNQ-Z2's Raspberry Pi header.** Both patterns are taken
  from the top. Shield pad n is set on PYNQ pin n by a proper rotation plus a translation, with no mirror. The fit is
  exact: rotation 0°, translation (+35, +169) mm, worst 0.000 mm. A mirrored footprint would leave 2.54 mm.
  - **Functions** (TUL schematic p.4): the PYNQ's 5 V pins 2 and 4 meet +5V_HDR. Its 3V3 pins 1 and 17 meet open
    pads. Its eight GND pins meet GND. Its 28 RPIO pins meet BEAT_xx, PPS_xx, HELPER_CLK and I2C.
  - **Body:** the shield extends outward, beyond the PYNQ's header edge, and overlaps the PYNQ only in an 11 mm strip.
  - **Standoff:** the PYNQ's top-right hole lands exactly under slot MH5.
  - **Silk:** all 40 of J4001's own labels (B00-B12, P00-P11, HCK, SDA, SCL, 5V, GND, nc) sit beside the pad on the
    net they name.
  - **The PYNQ-Z2's geometry:**
    - the caliper measurements in `mechanical/make_mockup.py` L22-36;
    - pin 1's end and the edge row: the PYNQ's own silk in `datasheets/PYNQ-Z2_DFR0600_Dim_02.jpg` ("1" by the edge
      row and "2" by the inner row at the right end, "39 40" at the left), and the manual's Table 22.

    No dimensioned TUL drawing was found on disk. The chirality result does not depend on the absolute numbers.
  - **Corroboration only:** rev A's bring-up, every beat, pps and helper clock through this socket.
- **J2003, the 15 V barrel jack** (XUNPU DC-005-A200, C720557). XUNPU's drawing "DC-005-AXXX" is not on disk. It was
  fetched into scratch from `datasheet.lcsc.com/datasheet/pdf/0f7696801952c83720863317845467ef.pdf`.
  - **The drawing:** the centre pin's terminal (its pin 4) is at the back, 13.75 mm from the front face. The sleeve
    (pin 2) is 7.60 mm from the front, on the axis. The switch (pin 3) is 11.10 mm from the front, 4.70 mm off the
    axis.
  - **Ours:**
    - pad 1 is at the back, 13.70 mm behind the body's front, and carries the +15 V feed through F2002 (PPTC);
    - pad 2 is 6.00 mm forward, on the axis, and is GND;
    - pad 3 is 4.70 mm aside and unconnected.
  - So the jack is **centre positive**, as the silk says ("HEATER ONLY, CENTRE +").
  - It opens toward the north edge, its front 2.3 mm inside it.
- **J6001-J6005, the 1-Wire terminals:**
  - left to right, the silk reads blk, red, yel over pins 3, 2, 1;
  - pin 3 is GND, pin 2 goes through 47 R to +3V3_D, and pin 1 through 47 R to ONEWIRE;
  - so the legend's GND, VCC and DATA are right on all five.
- **J5001, the debug 2x10:** the ten column labels over the odd row sit on their nets: +5V_HDR, ONEWIRE, +3V3_A,
  +3V3_D, HTR_DRIVE, I2C_SDA, I2C_SCL, then NC three times. The even row is all GND.
- **J2001/J2002, the bench posts:** "+5V" sits by J2001 (into D2001's anode) and "GND" by J2002.
- **Jumpers:**
  - rev A: 13 two-pin 50R TERM shunts, which have no orientation (pin 2 is GND on all);
  - rev B: 13 three-pin 50R/PARK jumpers, with "50R" beside pin 1 (the input), "PARK" beside pin 3 and GND in the
    middle, on all 13.
- **Rev B's 32 U.FL taps:** the centre pad carries the signal and both tabs are on GND, in Hirose's pattern.

### Not checked, and why

- **The 27 SMAs:** out of scope by the request.
- **The PYNQ-Z2's Arduino headers:** these boards do not use them, and they reach only 11 mm onto the PYNQ. By the
  photo, the Arduino rows are about 20 mm from the RPi header edge.
- **The mechanical clearance** of the PYNQ's USB-A, HDMI and audio jacks under that 11 mm strip. This is not a pin
  question, and rev A sits on its PYNQ.
- **The probes' own wiring:** DROK publishes no data sheet. Only its listing image, the INFO row above, shows it.
- **No JTAG, GPS, USB, JST or IDC connector** is on either revision.

### Where

- The script: `~/OpticsPCBs/tools/pin_audit/connectors/GPSDO-PYNQ-Z2.py`, with helpers and the PYNQ-Z2 model in
  `_GPSDO_PYNQ_Z2_lib.py`. Its output is `GPSDO-PYNQ-Z2.out` (exit 0).
- Rev A's board file, the IPC-D-356 exports, the XUNPU drawing (`fetch_dc005/dc005.pdf`) and the renders are in the
  session scratch area, `.../scratchpad/conn_icepi_pynq/pynq/`. The script re-extracts rev A from git and re-exports
  the IPC-D-356 if they are missing.
