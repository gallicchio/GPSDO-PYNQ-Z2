# Design review response -- round 28

*Started 2026-09-14 00:50 PDT.  This file is written first and updated as
work proceeds, so that if the session dies the state is recoverable from the
**Log** at the bottom.  Every way-point is a git commit; the log names them.*

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
fixed in this round.  Item 3 is answered by an operating procedure for Rev A
and a documented circuit for Rev B.  After this round: **order one board**,
assembled, with the placement preview checked for the packages listed in
§4.  Not five.

## 1. Findings, ranked by severity and agreement

"Agree" lists who found it: **C** = this review (Claude), **G** = GPT-5.6,
**Ge** = Gemini 3.8, **Gr** = Grok 4.6.  "Confirmed" says what I checked to
be sure it is real, because a finding three models agree on can still be
wrong (two of them are, below).

| # | Sev | Agree | Finding | Confirmed by | Disposition |
|---|-----|-------|---------|--------------|-------------|
| 1 | **Blocker** | C G Ge Gr | No I2C device software; the Si5351 is never programmed, so no helper, no beats | `gateware/driver/dmtd.py` says so; PYNQ selftest in round 27 showed 0 Hz | **TO FIX this round (see log)**: `gateware/driver/i2c_devices.py` (Si5351, TMP1075, MCP4725, DS2482/DS18B20), host unit tests, and `gateware/board/bringup.py`.  AxiIIC path exercised on the live PYNQ (bus scan; nothing attached, all NAK, as expected) |
| 2 | **Blocker** | C G Ge | A via drilled *inside* J5001 pin 13 (0.000 mm hole-to-hole) and a via 0.238 mm from J4001 pin 4's hole (rule 0.25) | `filled-drc.rpt` hole_to_hole x4; coordinates verified in the .kicad_pcb | **TO FIX this round (see log)** in the router: PTH drills now carry a no-via zone; rebuilt and DRC'd |
| 3 | High | Ge (C confirms) | MCP4725 ships with EEPROM at mid-scale (0x800 → 1.65 V on the FET gates at power-up) | MCP4725 datasheet Table 5-3, in `datasheets/` | Software + procedure: the bring-up script's first act is Write-DAC-and-EEPROM = 0 with PD=01; 15 V is not connected until then.  Schematic note updated (it asked for exactly this confirmation) |
| 4 | High | Ge (C confirms, differs on remedy) | Three pass FETs in linear mode share one gate; Vth is 1.0–3.0 V (datasheet) so the split between the three banks is a lottery, and the loop gain of Vth tempco × Rθ at half current exceeds 1, so a bank snaps to full-on rather than sitting at 0.8 W | DMN6068SE datasheet; arithmetic in §2.4 | **No board change for Rev A.** Operate the heater as on/off at full drive with slow (≥ 30 s) duty cycling: all 24 heaters switch together, the FETs run at 3 mW instead of 0.8 W, and uniformity is preserved.  Gemini's 3.3 Ω source resistors do not work with a 3.3 V DAC (§2.4).  Rev B recipe: one op-amp current sink per FET, from the 15 V rail |
| 5 | High | G Gr (C confirms) | The 1 pps cannot resolve the 100 ns wrap: pps is timestamped in the same 100 ns helper domain as the beats; `sheet_unit.py` promises a 200 MHz / 5 ns domain that does not exist | `dmtd_capture.v` puts beat and pps through one synchroniser; `phases_ps()` ignores pps | **FIXED in gateware v1.1**: every pps also gets a 64-bit PS-clock (10 ns) timestamp, plus a (helper, PS) counter pair so software maps one to the other; driver `pps_offsets_ns()`; testbench extended.  Note corrected.  (If this entry still says "planned" in the log, it was not finished.) |
| 6 | High | Gr (C confirms) | The fitted TCXO is ±2.5 ppm (FT5HNB**P**K), the schematic says ±0.5 ppm; ±2.5 ppm is ±25 Hz of beat, which reaches the 1260 Hz mains harmonic at the hot end | Fox datasheet option table: P = ±2.5 ppm | Note fixed.  Driver: `Si5351.trim_to_beat()` re-centres the beat from the measured helper frequency, which the core already reports.  The board is thermostatted, so in service the TCXO sees ±2 °C, not −30..+85.  Rev B: the T option (±1.0 ppm) of the same part |
| 7 | Medium | Gr (C confirms the fact, not the remedy); Ge supplies the fix | CLK1 at exactly 10.000000 MHz off the *same* PLL as the 10.0012344 MHz helper needs a fractional MultiSynth (80.0099), i.e. the jittery mode.  Grok says the Si5351A has one PLL: it has two | Si5351 datasheet block diagram (PLLA, PLLB) and §4.1; AN619 register map | Driver puts CLK1 on **PLLB in integer mode** (25 × 32 = 800 MHz / 80); notes on the helper sheet, unit 13 sheet and `design.py` say "same TCXO, both integer" instead of "same PLL, noiseless" |
| 8 | Medium | G Gr (C: **they are wrong**) | "Driving XA is an undocumented mode" | Si5351 datasheet **§6.6 "Applying a Reference Clock at XTAL Input"**: 1 Vpp through a 0.1 µF into XA, XB open.  Documented | Note corrected.  We run 0.77 Vpp because XA's abs max is +1.3 V and its bias point is unpublished; §2.8 shows 0.77 is the largest swing that is safe under the worst-case bias assumption.  GPT's "select the Si5351C" is unnecessary |
| 9 | Medium | Gr C | Comments and notes that describe a different board: pin 31 "DNP 0R alternate helper", "In2 = helper and NOTHING else", `VIA_CLK0/VIA_CLK1` swapped in `helper.py`, "200.02 MHz" pps note, "±0.5 ppm", "noiseless CLK1" | Read each one against the netlist / .kicad_pcb | All fixed at the source |
| 10 | Medium | G Gr C | Bench-powering the board with the PYNQ off puts 3.3 V on 26 unpowered Zynq I/O (abs max 0.55 V) with silkscreen as the only lock | PYNQ-Z2 manual table 15; power sheet | **Interlock added**: the LDO enables now come from `+5V_HDR` (the header side of the OR-ing diode) through 10k, so with the host off the board's 3.3 V rails cannot come up at all.  A DNP 0R restores always-on for use with no host attached.  See log for whether the layout took it |
| 11 | Medium | G Ge C | `rev B` on the silkscreen, `Rev A` everywhere else; silkscreen text clipped by the top edge; two 0.1–0.2 mm stubs on PPS_03/PPS_05 | DRC report; `build_pcb.py` line 2368 | Silkscreen now takes the revision from `design.py`; text moved 1 mm in; stubs are cosmetic and left |
| 12 | Medium | Ge (C: overstated) Gr (C: right) | In2.Cu is not "helper and nothing else": 53 nets, 501 segments.  Gemini calls the crosstalk catastrophic | My own scan (§2.10): the sub-1 mm parallel runs against helper branches are with DC nets, with beats (whose edges are *caused by* the helper edge and so land ns after it, never on it) and with one pps (1 event/s).  Not catastrophic; not clean either | Docstring corrected.  No re-route for Rev A.  Rev B: keep-out for helper branches in the router |
| 13 | Medium | Ge Gr (C: real, not fixable on this board) | The squarer's common-mode-threshold argument only holds for equal slew rates; the inventory spans 23 to ~1000 mV/ns, so 1 mV of rail drift is 44 ps on the FE-5680A and 1 ps on a ZED-F9T | Arithmetic; `design.py` SOURCES | Accept and measure.  Power-sheet note rewritten to say what cancels and what does not; expected floor per source tabulated in §2.13.  Rev B: a comparator-grade front end on one channel |
| 14 | Medium | C G Ge Gr | CPL rotations: KiCad-native, no correction | Compared Gemini's table (SOT-23 = +180) with the JLCKicadTools database used by thousands of orders (SOT-23 = **−90**): they disagree, so no table can be applied blind | `mfg/make_bom.py` now emits **both** files: `_cpl.csv` (native) and `_cpl_jlc_corrected.csv` (JLCKicadTools table, provenance recorded).  FABRICATION_NOTES says which to upload and which five packages to check in the placement preview |
| 15 | Low | Ge | R3004 "33 Ω" on the FPGA helper should be 0 Ω | R3004 is the DNP external-helper selector, not a 33 Ω; the 33 Ω are R3008–R3021, the branch series terminations chosen in round 21 from the Si5351 datasheet | No change.  Gemini misread the reference |
| 16 | Low | Ge | TM-4 unterminated pumps the gate to +7.3 V | Already in `design.py` unit 1 note, round 4 | No change: the TERM jumper ships fitted on unit 1 |
| 17 | Low | Gr | Order one board, not five | — | Agreed; `build.py --boards 1` is now the default release quantity |

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

- [ ] Route fix for the two drill clashes; rebuild; DRC 0 filled, 0 unconnected
- [ ] Notes and comments corrected at the source (`design.py`, `sheet_unit.py`,
      `sheets_rest.py`, `helper.py`, `build_pcb.py`)
- [ ] I2C drivers + host tests + bring-up script; AxiIIC path tried on the PYNQ
- [ ] Release regenerated for **1** board, with both CPL files
- [ ] Gateware v1.1 pps timestamps (see log)
- [ ] LDO-enable interlock from `+5V_HDR` (see log)
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
