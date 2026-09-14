# Design review response -- round 28, with an addendum from rounds 29 and 30

*Started 2026-09-14 00:50 PDT.  This file is written first and updated as
work proceeds, so that if the session dies the state is recoverable from the
**Log** at the bottom.  Every way-point is a git commit; the log names them.*

> **READ THE ADDENDUM FIRST.**  Later the same day, rounds 29 and 30 found
> that the release this document recommends ordering **had no ground planes
> in its gerbers** -- see finding 18 -- along with fourteen other faults and
> the first hardware measurement of the beat.  The round-28 verdict below is
> left exactly as it was written; its error is recorded in the addendum
> rather than edited out of it.

## Verdict, in one paragraph

**Not yet -- but close, and the distance is measured in hours of software and
one rebuild, not in a respin.**  Nothing found by me or by the three reviews
is a "start over".  The architecture (common helper, on-board two-flop
sampler, generated CAD, 4-layer stackup) survives all four reviews.  What
stands between this board and an order is: (1) two vias drilled into
through-hole pads that the fab would query; (2) no software for any I2C
device, so a fabricated board would produce no beats; (3) a heater driver
whose three pass FETs cannot share current, which is real but does not
matter for a first board because the heater should be off for the first
measurements anyway; (4) a handful of claims in the notes that describe a
different instrument from the one built (200 MHz pps timestamps, a ±0.5 ppm
TCXO, a noiseless CLK1 null, a helper-only In2 layer).  Items 1, 2 and 4 are
fixed in this round, and so is a fifth that no review asked to be fixed: the
board's 3.3 V rails can no longer come up with the host off.  Item 3 is
answered by an operating procedure for Rev A and a documented circuit for
Rev B.  After this round: **order one board**,
assembled, with the placement preview checked for the packages listed in
§4.  Not five.

## 1. Findings, ranked by severity and agreement

"Agree" lists who found it: **C** = this review (Claude), **G** = GPT-5.6,
**Ge** = Gemini 3.8, **Gr** = Grok 4.6.  "Confirmed" says what I checked to
be sure it is real, because a finding three models agree on can still be
wrong (two of them are, below).

| # | Sev | Agree | Finding | Confirmed by | Disposition |
|---|-----|-------|---------|--------------|-------------|
| 1 | **Blocker** | C G Ge Gr | No I2C device software; the Si5351 is never programmed, so no helper, no beats | `gateware/driver/dmtd.py` says so; PYNQ selftest in round 27 showed 0 Hz | **FIXED**: `gateware/driver/i2c_devices.py` (Si5351 with the exact PLL ratio 32 + 1543/390625, TMP1075, MCP4725/Heater, DS2482/DS18B20), 20 host unit tests, and `gateware/board/bringup.py`.  Run on the live PYNQ through the real `axi_iic` with nothing attached: every device reported absent, as it should.  Untested against real parts until a board exists |
| 2 | **Blocker** | C G Ge | A via drilled *inside* J5001 pin 13 (0.000 mm hole-to-hole) and a via 0.238 mm from J4001 pin 4's hole (rule 0.25) | `filled-drc.rpt` hole_to_hole x4; coordinates verified in the .kicad_pcb | **FIXED**: a no-via zone round every through-hole drill in the router, applied even to the routing net's own pads (build 1 missed that case; builds 2 and 3 have it).  Build 3's full-severity DRC: **0 hole-to-hole** (was 4).  `hole_to_hole` is now a DRC *error* in the generated project so the build's own check would catch a recurrence |
| 3 | High | Ge (C confirms) | MCP4725 ships with EEPROM at mid-scale (0x800 → 1.65 V on the FET gates at power-up) | MCP4725 datasheet Table 5-3, in `datasheets/` | Software + procedure: the bring-up script's first act is Write-DAC-and-EEPROM = 0 with PD=01; 15 V is not connected until then.  Schematic note updated (it asked for exactly this confirmation) |
| 4 | High | Ge (C confirms, differs on remedy) | Three pass FETs in linear mode share one gate; Vth is 1.0–3.0 V (datasheet) so the split between the three banks is a lottery, and the loop gain of Vth tempco × Rθ at half current exceeds 1, so a bank snaps to full-on rather than sitting at 0.8 W | DMN6068SE datasheet; arithmetic in §2.4 | **No board change for Rev A.** Operate the heater as on/off at full drive with slow (≥ 30 s) duty cycling: all 24 heaters switch together, the FETs run at 3 mW instead of 0.8 W, and uniformity is preserved.  Gemini's 3.3 Ω source resistors do not work with a 3.3 V DAC (§2.4).  Rev B recipe: one op-amp current sink per FET, from the 15 V rail |
| 5 | High | G Gr (C confirms) | The 1 pps cannot resolve the 100 ns wrap: pps is timestamped in the same 100 ns helper domain as the beats; `sheet_unit.py` promises a 200 MHz / 5 ns domain that does not exist | `dmtd_capture.v` puts beat and pps through one synchroniser; `phases_ps()` ignores pps | **FIXED in gateware v1.1**: every pps also gets a 64-bit PS-clock (10 ns) timestamp, plus a (helper, PS) counter pair so software maps one scale onto the other; driver `pps_offsets_ns()` / `absolute_phases_ps()` / `resolve_cycles()`; testbench 47 -> 57 checks, all pass; Vivado WNS +0.971 ns; loaded on the PYNQ, VERSION reads 1.1.  Sheet note corrected |
| 6 | High | Gr (C confirms) | The fitted TCXO is ±2.5 ppm (FT5HNB**P**K), the schematic says ±0.5 ppm; ±2.5 ppm is ±25 Hz of beat, which reaches the 1260 Hz mains harmonic at the hot end | Fox datasheet option table: P = ±2.5 ppm | Note fixed.  Driver: `Si5351.trim_to_beat()` re-centres the beat from the measured helper frequency, which the core already reports.  The board is thermostatted, so in service the TCXO sees ±2 °C, not −30..+85.  Rev B: the T option (±1.0 ppm) of the same part |
| 7 | Medium | Gr (C confirms the fact, not the remedy); Ge supplies the fix | CLK1 at exactly 10.000000 MHz off the *same* PLL as the 10.0012344 MHz helper needs a fractional MultiSynth (80.0099), i.e. the jittery mode.  Grok says the Si5351A has one PLL: it has two | Si5351 datasheet block diagram (PLLA, PLLB) and §4.1; AN619 register map | Driver puts CLK1 on **PLLB in integer mode** (25 × 32 = 800 MHz / 80); notes on the helper sheet, unit 13 sheet and `design.py` say "same TCXO, both integer" instead of "same PLL, noiseless" |
| 8 | Medium | G Gr (C: **they are wrong**) | "Driving XA is an undocumented mode" | Si5351 datasheet **§6.6 "Applying a Reference Clock at XTAL Input"**: 1 Vpp through a 0.1 µF into XA, XB open.  Documented | Note corrected.  We run 0.77 Vpp because XA's abs max is +1.3 V and its bias point is unpublished; §2.8 shows 0.77 is the largest swing that is safe under the worst-case bias assumption.  GPT's "select the Si5351C" is unnecessary |
| 9 | Medium | Gr C | Comments and notes that describe a different board: pin 31 "DNP 0R alternate helper", "In2 = helper and NOTHING else", `VIA_CLK0/VIA_CLK1` swapped in `helper.py`, "200.02 MHz" pps note, "±0.5 ppm", "noiseless CLK1" | Read each one against the netlist / .kicad_pcb | All fixed at the source |
| 10 | Medium | G Gr C | Bench-powering the board with the PYNQ off puts 3.3 V on 26 unpowered Zynq I/O (abs max 0.55 V) with silkscreen as the only lock | PYNQ-Z2 manual table 15; power sheet | **FIXED (build 3)**: the LDO enables come from `+5V_HDR`, the header side of the OR-ing diode, through R2025 (10k), so with the host off the TPS7A20s' own 500k pulldowns hold LDO_EN low and neither 3.3 V rail exists.  R2026 (DNP 0R) restores always-on for a board used with no host.  Laid out in the hand-routed power block on F.Cu + In2; ERC 0, DRC 0, 0 unconnected.  (The first layout crossed the six board-wide In2 links and broke I2C -- build 2, discarded; see log) |
| 11 | Medium | G Ge C | `rev B` on the silkscreen, `Rev A` everywhere else; silkscreen text clipped by the top edge; two 0.1–0.2 mm stubs on PPS_03/PPS_05 | DRC report; `build_pcb.py` line 2368 | **FIXED**: silkscreen reads `rev A` from `design.py` (plus a `DATE`); the edge text moved to 2.2 mm (KiCad still warns at that distance; it is inside JLCPCB's 0.15 mm silk-to-edge rule, and no further in is free of pads); the two stubs are cosmetic and left |
| 12 | Medium | Ge (C: overstated) Gr (C: right) | In2.Cu is not "helper and nothing else": 53 nets, 501 segments.  Gemini calls the crosstalk catastrophic | My own scan (§2.10): the sub-1 mm parallel runs against helper branches are with DC nets, with beats (whose edges are *caused by* the helper edge and so land ns after it, never on it) and with one pps (1 event/s).  Not catastrophic; not clean either | Docstring corrected.  No re-route for Rev A.  Rev B: keep-out for helper branches in the router |
| 13 | Medium | Ge Gr (C: real, not fixable on this board) | The squarer's common-mode-threshold argument only holds for equal slew rates; the inventory spans 23 to ~1000 mV/ns, so 1 mV of rail drift is 44 ps on the FE-5680A and 1 ps on a ZED-F9T | Arithmetic; `design.py` SOURCES | Accept and measure.  Power-sheet note rewritten to say what cancels and what does not; expected floor per source tabulated in §2.13.  Rev B: a comparator-grade front end on one channel |
| 14 | Medium | C G Ge Gr | CPL rotations: KiCad-native, no correction | Compared Gemini's table (SOT-23 = +180) with the JLCKicadTools database used by thousands of orders (SOT-23 = **−90**): they disagree, so no table can be applied blind | **DONE**: `mfg/make_bom.py` emits **both** files: `_cpl.csv` (native) and `_cpl_jlc_corrected.csv` (JLCKicadTools table, 72 placements rotated: 62 SOT-23-x by -90, 3 SOT-223 by +180, 9 SOIC-8 by +270; provenance and sign convention recorded in the source).  FABRICATION_NOTES says which to upload and which five parts to check in the placement preview |
| 15 | Low | Ge | R3004 "33 Ω" on the FPGA helper should be 0 Ω | R3004 is the DNP external-helper selector, not a 33 Ω; the 33 Ω are R3008–R3021, the branch series terminations chosen in round 21 from the Si5351 datasheet | No change.  Gemini misread the reference |
| 16 | Low | Ge | TM-4 unterminated pumps the gate to +7.3 V | Already in `design.py` unit 1 note, round 4 | No change: the TERM jumper ships fitted on unit 1 |
| 17 | Low | Gr | Order one board, not five | — | **DONE**: `build.py --boards 1` is the default; the release is priced for one board: parts $37.00, parts + assembly $99.78 (with R2025) |

Things I looked for and did **not** find (so that this review is
distinguishable from one that read nothing): a repeat of the 0x60 address
clash; a power symbol on a signal wire; a pinout error on the 1G80, 1GU04,
1G17, 1G34, TPS7A20, TMP1075, MCP4725, DS2482 or Si5351 (all re-read against
the datasheets in `datasheets/`); FF1→FF2 hold-time race (FF1's contamination
delay exceeds FF2's hold, same branch, adjacent packages); the FT5HN's pin 1
(NC on the N variant); a reversed diode in either supply path; the SMA
ground returns; the socket's 40 pads against the PYNQ model.

## 2. Detail on the findings that needed arithmetic

### 2.4 The heater FETs (finding 4)

`P_FET = (15 − 70·I)·I` for a bank of eight 560 Ω; peak 0.80 W at 107 mA.
Vth tempco ≈ −4 mV/°C, RθJA ≈ 70 °C/W on this pad, gm ≈ 1 S at 100 mA.
Loop gain at half current ≈ gm × 4 mV/°C × 70 °C/W × dP/dI (≈ 7.5 V) ≈ 2.
Greater than one, so a bank that is asked for 107 mA heats itself into
full-on (214 mA, where dP/dI < 0 and it stops).  With one gate voltage the
three banks turn on in Vth order; the loop in Python sees only temperature
and cannot tell them apart.  Net effect: a linear heater degenerates into
bang-bang per bank, with 3.2 W granularity and up to 0.8 W transiently in
one SOT-223.

Gemini's remedy (3.3 Ω source resistors) fails because the DAC only reaches
3.3 V: a worst-case Vth = 3.0 V part needs Vgs ≈ 3.1 V to carry 107 mA
before any source drop is added, so any degeneration large enough to matter
(≥ 22 Ω for ±30 % sharing) needs a gate drive of 5–6 V.  BJTs with emitter
degeneration would share, but need ~11 mA of base current from a DAC that
can source 15 mA through a 100 Ω.  The correct circuit is an op-amp current
sink per FET (LM324 from the 15 V rail, 10 Ω 2010 sense, 1 k gate); that is
a Rev B change and it is written into `sheets_rest.py` as a note.

For Rev A, none of this matters if the heater is driven **fully on or off**:
at Vgs = 3.3 V every DMN6068SE (Vth ≤ 3.0 V) carries the 214 mA the 70 Ω load
allows, all 24 heaters are on together, and each FET dissipates I²·Rds(on)
≈ 3 mW.  Slow duty cycling (period ≥ 30 s against a ~5 min board time
constant) gives a linear *average* with < 3 % thermal ripple and no
switching edge closer than 30 s to any other.  The driver's heater class
implements exactly that and refuses intermediate DAC values.

### 2.8 The XA drive level (finding 8)

Datasheet §6.6 shows 1 Vpp AC-coupled into XA.  XA abs max is −0.5 to
+1.3 V.  The pin's self-bias is not published; if it were as high as 0.9 V
(the 1.8 V core's midpoint) then 1 Vpp would reach 1.4 V and 0.77 Vpp
reaches 1.285 V.  So 0.77 Vpp (3k3/1k from 3.3 V CMOS) is the largest swing
that is safe without knowing the bias, and it is within 30 % of the
documented figure.  If TP_XA shows the part will not start, 1k → 1k3 gives
0.93 Vpp; nothing else changes.  Not changed for Rev A.

### 2.10 What actually shares In2.Cu with the helper (finding 12)

Scan of the .kicad_pcb: In2.Cu carries 501 segments on 53 nets.  Parallel
runs against a helper branch with an edge gap ≤ 1 mm:

| helper net | neighbour | parallel | min gap | why it does not matter |
|---|---|---:|---:|---|
| HELPER_CLK | HTR_DRIVE | 33 mm | 0.73 mm | DC (a 12-bit DAC through 100 Ω into 1.5 nF) |
| HCLK_00 | J3002 EXT HELPER IN | 25 mm | 0.25 mm | 51 Ω-terminated stub, unused unless R3004 is fitted |
| HCLK_00 | J3001 CLK1 OUT | 22 mm | 0.75 mm | a constant per-cycle artefact on the null channel only; static, cancels in ADEV |
| HELPER_CLK | PPS_04 | 22 mm | 0.75 mm | one edge per second |
| HCLK_07 | BEAT_09 | 14.5 mm | 0.25 mm | a beat edge is FF2's output, clocked *by* the helper, so it moves 3–5 ns after the helper edge and 95 ns before the next one |
| HCLK_00 | PPS_00 | 14 mm | 0.75 mm | one edge per second |
| HELPER_CLK | PPS_09 | 1.1 mm | 0.25 mm | one edge per second |

The stackup claim in `build_pcb.py` was written in round 15 and never
updated when the router was allowed onto In2 in round 18.  It is now true
to the board.

### 2.13 What the squarer's threshold drift costs, per source (finding 13)

Δt = ΔVth / slew.  With ΔVth = 1 mV (a 2 mV rail shift at ∂Vth/∂Vdd ≈ 0.5):

| channel | source | Vpp at gate | slew | 1 mV → |
|---|---|---:|---:|---:|
| 2, 3 | ZED-F9T CMOS | 3.3 | ~1650 mV/ns | 0.6 ps |
| 4–7 | Leo Bodnar CMOS | 1.2–2.3 | ~600–1150 | 1–2 ps |
| 1 | TM-4 terminated | 2.0 | 63 | 16 ps |
| 8, 9, 11 | sine 2.0–2.6 | 2.0–2.6 | 63–82 | 12–16 ps |
| 12 | HP 10811B | 1.56 | 49 | 20 ps |
| 12 | FE-5680A | 0.72 | 23 | **44 ps** |

Common-mode cancellation removes the part of this that is the same on both
channels of a pair; between a CMOS source and the FE-5680A almost none of it
is.  This is the instrument's analog floor for the sine sources and the
reason the heater exists.  It is not a Rev A change; it is a measurement.

## 3. The three reviews, ranked for insight into *this* problem

1. **Grok 4.6** — best.  Read the code it cites and re-derived the
   arithmetic; found the ±2.5 ppm TCXO against the ±0.5 ppm note, the
   swapped via names, the stale pin-31 comment, the 200 MHz pps note and
   the In2 discipline, none of which the other two found.  Its two central
   judgements — that 12.3 ps is a counter quantum and not an instrument
   floor, and that the pps cannot resolve the wrap — are right and are
   stated with the right scope ("relative phase, continuously unwrapped").
   Its verdict (write the software, buy one, measure the null and a
   splitter) is the one I arrive at.  Two errors: the Si5351A has two PLLs,
   not one (so its CLK1 objection has a clean fix it did not see), and the
   XA drive *is* documented.  It also did not open the board, and says so.
2. **GPT-5.6** — second.  The only one that did the manufacturing checks:
   filled the board, ran full-severity DRC, found the two drill clashes and
   the rev A/B mismatch, counted BOM against CPL, checked the DS2482
   pull-up.  Its first-pass verdict ("do not release") was withdrawn in its
   own follow-up for the stated purpose, which is the honest sequence.  Its
   pps analysis is correct and its "call it relative phase" advice matches
   Grok's.  Weaker on the analog: it treats the XA drive as a fabrication
   risk (it is documented) and did not notice the heater sharing problem or
   the TCXO grade.
3. **Gemini 3.8** — third, despite finding the two most concrete circuit
   faults (the FET sharing and the DAC's mid-scale default, both confirmed
   from datasheets) and shipping working-looking code.  Its analysis is
   undermined by overstatement and errors: the CPL table is asserted with
   the wrong value for the package that matters most (SOT-23: +180 vs the
   community's −90); "79 components mounted backwards" is presented as
   certain; the In2 crosstalk is called catastrophic without asking *when*
   the aggressor edges occur; R3004 is misidentified; the 3.3 Ω source
   resistor fix does not work with a 3.3 V DAC; the "21.8 ps per mV" number
   is right but the conclusion that the rails must be split misses that the
   drift it describes is slow and thermal, not the flip-flops' switching
   noise.  Its I2C driver is a reasonable starting point (PLLB for CLK1 is
   the right idea) but it was not checked against AN619's register
   semantics in a few places and the tests only exercise a mock that
   returns zeros.  Useful as a list of things to verify; not as a verdict.

## 4. What to do before ordering (the checklist)

- [x] Route fix for the two drill clashes; rebuild; DRC 0 filled, 0 unconnected, 0 hole-to-hole (build 3)
- [x] Notes and comments corrected at the source (`design.py`, `sheet_unit.py`,
      `sheets_rest.py`, `helper.py`, `build_pcb.py`)
- [x] I2C drivers + host tests + bring-up script; AxiIIC path tried on the PYNQ
- [x] Release regenerated for **1** board, with both CPL files
- [x] Gateware v1.1 pps timestamps: simulated, built, running on the PYNQ
- [x] LDO-enable interlock from `+5V_HDR` (build 3)
- [ ] **Jason:** upload `GPSDO-PYNQ-Z2_cpl_jlc_corrected.csv`; in JLCPCB's
      placement preview confirm pin 1 on one 74LVC1G80 (SOT-23-5), one
      DMN6068SE (SOT-223), one TMP1075 (SOIC-8), the Si5351 (MSOP-10) and the
      band on D2001 (SMA) against `GPSDO-PYNQ-Z2_assembly_top.pdf`.  If the
      corrected file is wrong, upload the native one; one of the two is right
- [ ] **Jason:** decide Rev A vs Rev B for the heater current sinks (§2.4).
      My recommendation: Rev A as-is with on/off drive
- [ ] First power-up order: PYNQ on → board on header → `bringup.py`
      (zeros the DAC EEPROM, programs the Si5351, reads the eight
      thermometers, runs selftest) → only then the 15 V jack

## Log

*(newest last; each entry says what changed and the commit that holds it)*

- **00:50** Read the prompt, the three reviews, every generator source, the
  RTL, the driver, the mfg scripts, the four datasheets the findings turn on
  (Fox FT5HN, DMN6068SE, MCP4725, Si5351), and the DRC reports.  Scanned
  In2.Cu geometry with a script.  Wrote this file.  No source changed yet.
- **01:00** Source edits for findings 2, 6, 7, 8, 9, 11, 12, 14, 17 made
  (router no-via zone round every through-hole drill; silkscreen revision
  from `design.py`; edge text moved; stackup docstring; `helper.py` via names;
  design.py pin-31 comment and unit-13 note; unit-sheet pps and null notes;
  helper-sheet TCXO/XA/CLK1 notes; power-sheet rail and FET notes; DAC EEPROM
  note; both CPL files; one board default).  `build.py --no-pcb`: ERC 0,
  all checks pass, 0 overlaps.  **Full build 1 launched 00:59** (router +
  DRC + release), log in the session scratchpad.  Not yet committed: waits
  for the DRC result.
- **01:05** `gateware/driver/i2c_devices.py`, `test_i2c_devices.py` (20 new
  tests, 44 total pass) and `gateware/board/bringup.py` written.  PLL ratio
  computed exactly (32 + 1543/390625); schematic text updated to match.
- **01:08** `bringup.py` run on the live PYNQ through the real `axi_iic`
  with no front-end board: bus scan empty, every device reported absent,
  core selftest as in round 27.  The software path is exercised end to end;
  the devices are not (no board exists yet).  Way-point 1 committed
  (`dfe5616`).
- **01:14** Gateware v1.1 (finding 5): `dmtd_capture.v` gains a PS-domain
  64-bit counter, a 10 ns timestamp + count for every pps at 0x400+16*slot,
  and the (helper, PS) pair at 0x01C/0x020; VERSION 1.1.  Testbench extended
  to 57 checks (pps spacing 200 helper cycles -> 2000 +/-2 PS clocks; pair
  ratio 9.9988; PS stamp predicts the helper stamp within 3 cycles).
  **xsim: TB PASS 57/57.**  Driver: `ps_channel`, `counter_pair`,
  `pps_offsets_ns`, `absolute_phases_ps`, `resolve_cycles`; 49 host tests
  pass.  **Vivado bitstream build launched 01:15**, log in the scratchpad.
  Board build 1 (router) still running.
- **01:20** Board build 1: router done, **filled DRC 0 violations, 0
  unconnected**; release step running.  (The router's own log says two
  off-block nets, PPS_03 and PPS_05, failed its first pass and were joined
  by the multi-piece pass -- the same two that carried 0.1-0.2 mm stubs in
  round 27.)  Vivado v1.1 overlay: **WNS +0.971 ns, WHS +0.035 ns**, 2523
  LUTs, 9043 FFs, 28 IOBs; `build/overlay/dmtd_top.bit` + `.hwh` written.
- **01:22** Interlock (finding 10) written but NOT yet built: `sheets_rest.py`
  (LDO_EN bus, R2025 10k from +5V_HDR, R2026 DNP 0R), `pcb/power.py`
  (placement, F.Cu, In2 and three vias), `build_pcb.py` (consumes the power
  block's In2 routes/vias), `parts_map.py`, and `gen.py` (hole_to_hole is
  now a DRC *error*).  Goes into **build 2** after build 1's release is
  checked.  If build 2 fails DRC or leaves LDO_EN unconnected, revert these
  five files to way-point 1 and record the interlock as a Rev B item.
- **01:28** Build 1's full-severity DRC: the two hole-to-hole clashes were
  STILL there.  Cause: `build_g2()` (the multi-piece joiner's grid) skips the
  net's own pads with `continue` before the new no-via call, so a net's own
  through-hole pad never got its zone -- and both clashes are exactly that
  case (I2C_SCL's own J5001 pad, +5V_HDR's own J4001 pad).  Fixed by moving
  the call ahead of the skip.  Way-point 2 committed (`9d24e83`) with build
  1's outputs and gateware v1.1.  **Build 2 launched 01:29** with the via
  fix, the interlock and hole_to_hole as a DRC error (launched ~01:23 by the
  wall clock; earlier times in this log are approximate).  Uncommitted at this
  moment: gen/gen.py, gen/sheets_rest.py, pcb/power.py, pcb/build_pcb.py,
  mfg/parts_map.py (all interlock/via-fix), gateware/README.md,
  gateware/driver/dmtd.py (docs).
- **01:58** Build 2's router has been running 31 min against build 1's 20
  (build.py buffers its output, so nothing is visible until it ends).  A
  diagnostic copy of gen/ + pcb/ is running in the session scratchpad with
  `RTPROG=1 RTDEBUG=1` to see which nets it is fighting.  Build 2 left to
  run.  If it does not finish by ~02:20, the plan is: kill it, revert the
  interlock (gen/sheets_rest.py, pcb/power.py, the PW hook in
  pcb/build_pcb.py, mfg/parts_map.py) to way-point 2 and rebuild with only
  the via fix and the DRC severity, then record the interlock as Rev B.
- **02:05** Build 2 finished after 2037 s: 0 DRC violations but **2
  unconnected items, I2C_SCL and I2C_SDA**.  The diagnostic copy (router
  debug flags on) said why within a minute: my LDO_EN run on In2 at board
  x = 128 crossed the six board-wide In2 links at y = 25.0..29.0 that carry
  I2C, the Q2003 drain, HTR_DRIVE, +3V3_D and +15V_HTR straight through the
  power block; spine() tried to hop each link to F.Cu over it and landed on
  U2002's pads, so five links were dropped and the joiner spent half an hour
  failing to re-route two of them.  My In2 scan of the block had only tested
  segment *endpoints* against the window, and the links' endpoints are at the
  board edges.  Build 2's output is discarded (not committed).
- **02:07** `LDO_EN` re-laid: R2025's via at board (143.1, 19.1), In2 up to
  y = 23.5, across to x = 128.5 and up to y = 15.2; each EN pin reaches it by
  a short F.Cu stub to its own via (U2002's at (128.5, 23.5), U2001's at
  (128.5, 15.2)); nothing on In2 at y > 23.5.  R2026 moved to straddle the
  new stub.  The constraint is now written into `build_pcb.py` beside the
  hook.  **Build 3 launched 02:07.**
- **02:28** **Build 3: ERC 0; multi-terminal 0 joins failed; filled DRC 0
  violations, 0 unconnected; full-severity DRC 0 hole-to-hole (was 4)**, 39
  dangling trunk ends (all same-net rail/link ends into pours, as before)
  and the one silk-to-edge warning on the bench-post text.  LDO_EN copper is
  exactly as laid out; R2025 is in the BOM/CPL, R2026 in the excluded list.
  Release regenerated for one board.  1496 s.  Way-point 3 committed
  (`6d1391a`).  README.md gained its Round 28 section; this file is final.

---

# Addendum -- rounds 29 and 30, the same day

*Written 2026-09-14 afternoon, after the round-28 response above was closed.
Rounds 29 and 30 were not a design review; round 29 was a list of silkscreen
corrections and a request for a document, and round 30 was "make
`bringup.py` work".  Both turned up things a review should have found, and
one of them would have wasted the order this file told you to place.*

## Verdict, revised

**Round 28's "order one board" was wrong, and by a wide margin.**  Not
because of anything the four reviews found -- those dispositions all stand --
but because of a fault none of us looked for: **the release in round 28 had
no ground planes in it.**  Not thinned, not badly stitched: absent.

```
                    round 28                    round 29
  In1_Cu     1364 lines, 0 regions        34421 lines, 1 region
  B_Cu       1474 lines, 0 regions        34531 lines, 1 region
  F_Cu       9770 lines, 0 regions        79224 lines, 9 regions
  In2_Cu     2516 lines, 0 regions         2396 lines, 0 regions   (correct: In2 is routed, not poured)
```

A 4-layer board with two empty copper layers and no F.Cu pour is not a board
with a compromised ground; it is a board on which 436 ground pads connect to
nothing.  JLCPCB's own DFM would probably have queried two blank layers
before building it, so the likely cost was a week and an e-mail rather than a
scrapped panel -- but it was the order, either way.

**After round 29 and 30: order one board.**  The same recommendation, now
resting on a release that has been checked rather than one that merely passed
a check aimed somewhere else.

## 5. What rounds 29 and 30 found

Numbering continues from the table in §1.  "Found by" is honest about how:
almost none of these came from re-reviewing the design.  They came from
Jason looking at a render, from a bring-up run on real silicon, and from
making the DRC ask questions it had not been asking.

| # | Sev | Found by | Finding | Confirmed by | Disposition |
|---|-----|----------|---------|--------------|-------------|
| 18 | **Blocker** | round 29, from the DRC-vs-reality gap | **The pours were never poured into the shipped board.** `build.py` filled the zones into a COPY, `build/filled.kicad_pcb`, ran the DRC on that, and committed the unfilled original | `grep -c filled_polygon` on the committed board = 0; the three gerbers above | **FIXED**: the zones are poured into the board itself; the unfilled copy is kept in `build/` for the clearance-only pass, with a copy of the project file beside it so that pass uses our rules and not KiCad's defaults |
| 19 | **Blocker** | round 29, from the 3D render | **The board had no mounting holes.** Six `Cmts.User` captions reading "M3 standoff" and "M3 shared with PYNQ", and no drilled hole anywhere. `put("H1".."H6")` looked six references up in a netlist that has never had a mounting-hole symbol in it, and `put()` returns quietly when it finds nothing | `grep -c MountingHole` on the committed board = 0 | **FIXED**: four M3 holes and one 7 x 3.2 mm M3 slot onto the PYNQ's own top-right hole, placed directly rather than through the netlist (a hole is not a part: no pads, no net, no BOM line). Their courtyard is the standoff keep-out, so the existing courtyard check tests the clearance -- and caught a 2 mm clash with J6001 immediately. Verified in the drill file: four T6 (3.2 mm) hits plus one G85 routed slot |
| 20 | High | round 29 | **The DRC was answering a question nobody asked.** The project set four numeric rules and left the other eleven -- including the entire silkscreen family -- at KiCad's defaults, and every rule at its default severity. `--severity-error` therefore reported "0 violations" on a board carrying 639 warnings; at full severity and under round 29's severities, that same board reports **598 errors** | `kicad-cli pcb drc --severity-all` on the round-28 board | **FIXED**: `gen/jlc.py`, one row per rule, each asserting our figure is at least as strict as JLCPCB's published capability (the file will not import otherwise), plus 25 severities of which 18 are errors. `build.py` now also raises before the release step if the poured board has any DRC error -- which is how round 30's unconnected `I2C_SDA` was caught |
| 21 | High | round 29 | **Twelve silkscreen markers named the wrong part.** `r.startswith("R20")` also matches unit 2's `R201`..`R208`, and `r.startswith("U50")` matches unit 5's `U501`..`U504`, so eight resistors and four logic gates carried a heater `H` or a thermometer `T` | Reference numbering scheme in `build_pcb.unit_of()` | **FIXED**: `re.match(r"^R20\d\d$")` / `^U500[1-8]$`, the same four-digit rule `block_of()` has always used |
| 22 | Medium | round 29 | **Every marker offset was in BOARD coordinates.** A tile is stamped thirteen times at rot 90 on the left and rot 270 on the right, so one offset meant "towards the helper" on one side and "away" on the other; a 9 mm dodge spiral then moved letters onto whatever was clear | Plotted silkscreen, both columns | **FIXED**: offsets are given in the frame of the part they label, so the two sides are mirror images by construction; the dodge radius is 2.2 mm, not 9 |
| 23 | Medium | round 29 | **Reference designators were 0.6 mm tall** -- below JLCPCB's 0.8 mm minimum printable height -- **and the stock footprints' silkscreen outlines are 0.12 mm**, below their 6 mil minimum. No KiCad rule checks a *graphic* line's width, only text's | DRC `text_height` x199 (the per-rule report cap, so the real count was every designator) | **FIXED**: designators are 0.8 mm and are *placed* (588 of 591 find clear board; three test points' names go to F.Fab); `footprint()` raises every silkscreen stroke below 0.16 mm as the footprint is placed, which covers the stock library too |
| 24 | Medium | round 29 | **A false `UNROUTED: PPS_05, PPS_03` caption had been on the board for several rounds** while KiCad's own filled DRC said 0 unconnected. It was printed from the two-point router's leftovers; the multi-terminal pass that runs afterwards had already finished both | KiCad DRC vs the caption | **FIXED**, and then nearly repeated: the replacement check is *stricter* than KiCad's connectivity and put a new false caption on build 4. The check now prints to stderr and writes nothing on the board. **A board must not carry a claim that a better check contradicts** |
| 25 | Medium | round 29 | `HIN` and `HO` were each drawn **twice**, 0.5 mm apart -- `geom.sma_rows()` lists the helper jacks and `build_pcb` had a second loop for them | The .kicad_pcb has two `gr_text "HIN"` | **FIXED** |
| 26 | Medium | round 29 | **Two connectors carried the same five names**: the 1-Wire screw terminals were `P1`..`P5` and the 1 pps jacks are `P1`..`P12` | Round 29's own prompt walked into it ("the screw terminal labeled P3") | **FIXED**: the terminals are `W1`..`W5`, matching the `W` already printed on the 1-Wire test point |
| 27 | Medium | round 29 | **Closest SMT pad to the board edge is 1.19 mm** (`FB5009`; `Q2003` is second at 1.20 mm). An assembly constraint, not a fabrication one, and nothing in KiCad looks at it -- `copper_edge_clearance` is about copper, not about whether a nozzle and an edge clamp can both reach | `mfg/make_fab.py` measures it from the board | **OPEN -- for Jason.** Measured and printed in `FABRICATION_NOTES.txt`. Everything nearer the edge is through-hole and hand-soldered. If 1.19 mm is inside JLCPCB's rail allowance the panel needs a break-away rail, which is a different panel and a price, not a redesign. **Ask them; do not move the part** -- `FB5009` is 4 mm from the pin it decouples and that is the point of it |
| 28 | **Blocker** (bring-up) | round 30, on silicon | **`PynqBus` could not read.** `pynq`'s `AxiIIC.receive()` hands its buffer straight to cffi as `unsigned char *`; cffi converts a `bytes` but refuses a `bytearray`. Every *send* worked, so the bus scan passed and found the Si5351 -- the first *read*, the Si5351's status register, is where `bringup.py` died | The traceback, on the PYNQ | **FIXED**: receives allocate from `AxiIIC._ffi`, the FFI that owns the prototype. Note that `MockBus` and `SmbusBus` cannot reproduce this -- one is a dict and the other goes through `smbus2`. It is exactly the class of bug the 20 host tests for finding 1 could never have found |
| 29 | High | round 30, on silicon | **The selftest reported the helper at 8150729.9 Hz**, -185000 ppm, while the same property read a second later said 10001217.0. The gateware's estimator counts PS clocks across 2^20 helper cycles and *latches the finished window*, so a read taken shortly after the synthesiser starts returns the window that straddles the change -- long by however much of it had no clock in it (8150729.9/10001217 = 0.815, a window 1.227x too long) | Three independent methods agree on 10001217 Hz: the estimator read repeatedly, the free-running counter against the wall clock, and the v1.1 (helper, PS) pair | **FIXED**: `settle_helper()` polls until two consecutive windows agree; `selftest()` uses it. A host test feeds it the 1.227x value first and checks it is not believed |
| 30 | Medium | round 30 | **The selftest counted thirteen untestable things as failures.** The squarers and flip-flops that make a beat are on the front-end board; with no board they read ~0 edges, which is the right answer. "29 checks, 14 failures" buried the one real failure | The run itself | **FIXED**: results are three-state (True / False / None = "not testable here"), `failures()` counts only False, and `bringup.py` infers the flag from the bus -- the board's own I2C parts are the evidence |
| 31 | Low | round 30 | **CLK2 was powered down**, so an ADALM2000 clipped to CLK1 and CLK2 was watching a dead pin. Correct for the front-end board, which routes nothing to CLK2; not correct for a bench | `Si5351Config.registers()` wrote `CLK_PDN` | **FIXED as an option**: `clk2='helper'` puts a second copy of CLK0 there off the same PLLA, so CLK1 and CLK2 are 1234.4 Hz apart. Off by default, so the board's own image is unchanged |
| 32 | Medium | round 30 | **The PYNQ-Z2 power-cycled mid-session.** The serial logger died with "device reports readiness to read but returned no data" -- and that is the evidence, not the bug: the FT2232 is USB-powered, so a PS reset leaves the port open. For `/dev/ttyUSB1` to vanish, the board's power has to go | Device node recreated at the moment of the drop; board reported `up 1 min` on return | **OPEN -- for Jason.** This board's own silkscreen already says it: *power the PYNQ from its barrel jack J9, not USB alone*. A Si5351 module on the header's 3.3 V is exactly the load that turns "enough for most designs" into a brown-out. `gateware/board/console_log.py` now logs across resets and says which of the two happened |

## 6. What is now verified on hardware, and what is still not

Round 28 could say only that the software path ran with nothing attached.
Round 30 ran it against a real Si5351 wired to five header pins, and measured
the number the instrument is built on:

```
    measured beat : 1234.417 Hz     (block-to-block spread 1.24 Hz)
    by design      : 1234.400 Hz
    error          : +0.017 Hz, +0.0017 ppm of 10 MHz
    -> one helper cycle = 12.3426 ps of input phase   (design 12.3425)
```

from an ADALM2000 on CLK1 and CLK2, measured from the **phase ramp** between
the two channels rather than by subtracting two separately-fitted 10 MHz
frequencies: both channels share one ADC clock, so the ramp cancels it.  That
is a DDMTD performed in software on the raw capture, and it is the first
end-to-end confirmation of finding 7's disposition (CLK1 on PLLB in integer
mode) on real silicon.

| | round 28 | now |
|---|---|---|
| I2C write path | exercised, all devices absent | **exercised against a real Si5351** |
| I2C read path | never exercised | **fixed and exercised** (finding 28) |
| Si5351 programming | host tests only | **46 registers written and read back, both PLLs locked** |
| helper frequency | 0 Hz (no synthesiser) | **10001224.7 Hz, -1.0 ppm** (a plain crystal, not a TCXO) |
| the 1234.4 Hz beat | asserted from arithmetic | **measured, +0.0017 ppm of 10 MHz** |
| `bringup.py --no-heater` | crashed | **4 checks, 0 failures, 25 not testable here** |

Still untested, and untestable until boards exist: all thirteen front ends,
the heater and its DAC, the eight thermometers, the DS2482 and the probes,
and the pps path.  The beat and pps counters in the gateware have still only
ever seen a testbench and a bench synthesiser.

## 7. The checklist, restated

Carried forward from §4, with what rounds 29 and 30 added:

- [x] Everything ticked in §4 still holds
- [x] **The pours are in the board and in the gerbers** (finding 18) -- the
      one item that invalidated the round-28 release
- [x] Mounting holes exist and are in the drill file (finding 19)
- [x] The DRC is set from JLCPCB's capability and the build stops on a DRC
      error or an unconnected net (finding 20)
- [x] `bringup.py` runs clean on real silicon (findings 28-30)
- [ ] **Jason:** upload `GPSDO-PYNQ-Z2_cpl_jlc_corrected.csv`; check pin 1 on
      the five named packages in JLCPCB's placement preview (unchanged from §4)
- [ ] **Jason:** decide Rev A vs Rev B for the heater current sinks (§2.4).
      Recommendation unchanged: Rev A as-is with on/off drive
- [ ] **Jason:** ask JLCPCB whether **1.19 mm** from an SMT pad to the board
      edge needs a break-away rail (finding 27).  The number is in
      `FABRICATION_NOTES.txt`
- [ ] **Jason:** re-read the three rules in `gen/jlc.py` marked `as JLC`
      (hole-to-copper, hole-to-hole, silkscreen-to-copper) against their
      current published capability before ordering.  Change the `jlc` column
      if one has tightened and the assertion will say whether we still pass
- [ ] **Jason:** power the PYNQ-Z2 from its barrel jack with J9 at `REG`,
      not from micro-USB (finding 32), before the next long bring-up run
- [ ] First power-up order, unchanged from §4

## Log (continued)

- **11:52-14:50, round 29** Five board builds.  Build 1 was the round-28
  board rebuilt as a baseline.  Build 2 lost the title and the legend heading
  off the board (vias treated as hard obstacles; they are tented, and a
  `gr_text` dropped on one DRCs clean) and left `I2C_SDA` unconnected, and
  built a release from it anyway.  Build 3 caught the same unconnected net
  because `build.py` now raises, and refused to build a release.  The cause
  was mine: I had moved two parts for *silkscreen* room, and a part moved for
  the silkscreen is a part moved -- three packed 1-Wire parts 2 mm lower
  changed which way the DS2482's `I2C_SDA` escaped and cost the helper its
  only corridor.  Both moves reverted, the mounting hole moved instead.
  Build 4 routed clean and printed a false `UNROUTED` caption (finding 24).
  Build 5 ships.  Commits `fe07e29` (sources) and `460c5d6` (the board,
  `HANDBOOK.md`, the release).
- **16:05-16:20, round 30** `bringup.py --no-heater` on the PYNQ: the cffi
  read bug (finding 28), then the stale-window helper reading (finding 29),
  then thirteen untestable beats counted as failures (finding 30).  All three
  fixed; 59 host tests pass.
- **16:20-16:28** The PYNQ dropped off the network mid-run and came back
  reporting `up 1 min`.  My first serial logger captured nothing because it
  died when the port vanished -- which is itself the diagnosis (finding 32).
  `/dev/ttyUSB1` confirmed as the console by writing to `/dev/ttyPS0` on the
  board and watching it arrive.
- **16:29-16:35** CLK2 enabled as a bench witness (finding 31); the M2k's own
  analog front end found powered down (`m2k-fabric` leaves both input
  amplifiers at `powerdown = 1`, which reads as four ADC counts that look
  exactly like a disconnected probe); the beat measured from the phase ramp.
  Commits `76e8b2d` and `6423d21`.
- **16:40** This addendum.  The round-28 verdict above is left as it was
  written, with its error recorded here rather than edited out of it.
