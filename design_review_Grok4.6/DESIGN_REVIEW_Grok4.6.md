# GPSDO-PYNQ-Z2 design review (Grok 4.6)

Date: 2026-09-13
Reviewer: Grok 4.6, working from `DESIGN_REVIEW_PROMPT.md` and the sources it points at.
Board revision reviewed: Rev A, as generated.

## Verdict

**Do not treat Rev A as a 12 ps, 13-channel instrument and do not order five assembled boards yet.**

The architecture is not misconceived. A common-helper digital DMTD, with the sampling flip-flop on the mezzanine rather than in the FPGA, is the right shape for this inventory and this host. The generated schematic/PCB flow is a strength. The pin map, I²C addresses, and on-board two-flop sampler look internally consistent.

What I will not sign off on is the **claim set**, not the topology:

1. The helper will not exist until someone writes the Si5351 (and DAC) I²C. That is still a brick.
2. The 12.3 ps figure is a counter quantum, not an instrument floor. For the weak sine sources it is a fantasy.
3. 1 pps, as implemented, cannot resolve the 100 ns wrap.
4. The CLK1 “null” is not a noiseless instrument floor.
5. The actual TCXO eats the 60 Hz-comb margin the beat frequency was chosen for.
6. Bench 5 V with the PYNQ off is an absolute-max violation with only silkscreen as a lock.

Fabricate **one** board after the Si5351 bring-up code exists and has been talked to a real Si5351A. Do not populate the heater until the DAC EEPROM policy is executed. Do not tell anyone this compares an FE-5680A to an HP 10811B at 12 ps until channel 12 has been measured.

“Start over” is the wrong conclusion. “Stop inflating what this board is, write the missing software, and buy one” is the right one.

---

## What I actually checked

A review that approves everything is indistinguishable from one that read nothing, so here is the work:

| Area | Sources | Depth |
|---|---|---|
| Frequencies, gain, wrap, header map, per-unit population | [gen/design.py](../gen/design.py) | Read and re-derived the arithmetic |
| One channel, squarer, FF1/FF2, pps notes | [gen/sheet_unit.py](../gen/sheet_unit.py) | Full file |
| Helper, power, heater, I²C, probes | [gen/sheets_rest.py](../gen/sheets_rest.py) | Helper + power + housekeeping + probes |
| Floorplan, mounting, pin-assignment order | [pcb/geom.py](../pcb/geom.py) | Read |
| Helper placement / Si5351 pad routing | [pcb/helper.py](../pcb/helper.py) | Pad numbers vs MSOP-10 pinout |
| Stackup vs what In2 actually carries | [pcb/build_pcb.py](../pcb/build_pcb.py), [pcb/maze.py](../pcb/maze.py) | Comments vs later routing |
| Tile analog geometry | [pcb/tile.py](../pcb/tile.py) | Placement rules |
| Capture RTL, CDC, register map | [gateware/rtl/dmtd_capture.v](../gateware/rtl/dmtd_capture.v) | Helper domain + AXI comments |
| Pin constraints | [gateware/xdc/pins.xdc](../gateware/xdc/pins.xdc), [gateware/gen_xdc.py](../gateware/gen_xdc.py) | Generated from `design.py` |
| Phase math / selftest | [gateware/driver/dmtd.py](../gateware/driver/dmtd.py), [gateware/driver/dmtd_constants.py](../gateware/driver/dmtd_constants.py) | `phases_ps`, unwrap, PPS unused |
| I²C in the overlay | [gateware/build.tcl](../gateware/build.tcl), [gateware/README.md](../gateware/README.md) | `axi_iic` present, no device driver |
| BOM / CPL policy | [mfg/make_bom.py](../mfg/make_bom.py), [mfg/release/annotated_bom.md](../mfg/release/annotated_bom.md) | Rotations, 5-board qty, stock |
| Author’s own attack list | [DESIGN_REVIEW_PROMPT.md](../DESIGN_REVIEW_PROMPT.md) §7–§9 | Used as the agenda, not as answers |

I did **not** open the board in KiCad and walk copper. I did **not** re-run `build.py`. I did **not** read all 9,700 lines of [README.md](../README.md). Where I cite it, I cite a specific passage. I did not treat the previous LLM review as a source of findings; I formed these independently and then noted overlap.

---

## The architecture (prompt §2–§3)

A single helper sampling thirteen 10 MHz sources is the whole trick, and it is a good trick. Helper phase noise, Si5351 PLL noise, and the helper squarer’s threshold all cancel in a channel-to-channel difference for Fourier frequencies below the beat. That is why this can beat a picosecond counter without being a picosecond oscillator.

Two consequences the write-up under-weights:

* **Anything that is *not* common does not cancel.** Per-channel squarer threshold, slew-dependent amplitude-to-phase conversion, local temperature, and CLK1 MultiSynth jitter on the null are in that set.
* **The 12.3 ps number is not a resolution.** It is `T_helper / N_GAIN` = one helper cycle referred to the 10 MHz input. It is the **quantisation of the counter**. The analog front end, the flip-flop aperture, and the FPGA synchroniser are all allowed to be worse, and for several sources they will be.

The scale arithmetic in `design.py` is right. One beat period of displacement is exactly 100 ns of input phase; a beat contains `F_HELPER/F_BEAT` = 8102.1 helper cycles, not `N_GAIN` = 8101.1. `T_RES_PS = 12.3425 ps`. The prompt table that writes `N = f_helper/(f_helper−f_signal) = 8101` is the old mix-up. Trust the code, not the table.

---

## Findings, ordered by how much it costs to be wrong

### 1. Critical — no helper until I²C exists (prompt §7.1)

`axi_iic` sits at `0x4160_0000` and answers. Nothing programs the Si5351, the TMP1075s, the MCP4725, or the DS2482. Without CLK0 at 10.0012344 MHz there are no beats. The overlay self-test will report a dead helper and thirteen empty channels, which is honest, but it is not an instrument.

This is not a schematic bug. It is a release gate. The Si5351 register sequence is not research: PLL `32 + 4142/1048575`, MultiSynth 80 integer, R = 1, CLK1 at 10.000000 MHz. Write that, talk to a stick of Si5351A, then buy a board.

Also write, on first power-up and before the heater supply is present:

* MCP4725: Write-DAC-and-EEPROM to code 0 with `PD=01` (already flagged in §8).
* General Call Reset.
* A software interlock that refuses to raise `HTR_DRIVE` until the eight TMP1075s NAK-or-read sanely.

Pin assignment vs gateware: **yes, it matches.** `gen_xdc.py` derives `pins.xdc` from `design.py`. Header pin 18 is asserted as `HELPER_CLK` (Y7, `IO_L13P_T2_MRCC_13`). Beats and pps are false-path inputs into a helper-domain synchroniser. That is exactly what [dmtd_capture.v](../gateware/rtl/dmtd_capture.v) implements. Ordinary I/O is sufficient for ~1.2 kHz and 1 Hz. I would not hold fabrication for a second clock-capable pin.

The 200 Ω / ~4.4 ns helper edge is a bring-up risk (double-clocking), not a pin-map error. If it happens, the fix is on the PYNQ or an MMCM, not a respin of this board.

**§7.1 in one paragraph:** the pin map supports the gateware; the missing I²C does not support the instrument. Do not fab a panel until CLK0 has been produced by software on real silicon.

### 2. Critical — the squarer is the analog limit (prompt §7.2)

The 74LVC1GU04 is the measurement. Its Vth *is* the zero crossing. The common-mode argument is half right.

What **does** cancel:

* Slow Vcc drift of `+3V3_A`, because every squarer and every helper buffer drinks from it.
* Helper-squarer threshold, because it is in every channel alike.
* A constant per-channel Vth mismatch, after you subtract it.

What **does not**:

* **Slew-dependent conversion of the same millivolt into different picoseconds.** Referred jitter is `v_n / slew`. At 10 MHz, slew of a sine is `2π f (Vpp/2)`:

  | Source | Vpp into 50 Ω | Slew | 1 mV → | 5 mV → |
  |---|---:|---:|---:|---:|
  | TM-4 terminated | 2.00 V | 63 mV/ns | 16 ps | 80 ps |
  | HP 10811B | 1.56 V | 49 mV/ns | 20 ps | 102 ps |
  | FE-5680A | 0.72 V | 23 mV/ns | **44 ps** | **221 ps** |
  | CMOS ~2 ns edge | 3.3 V | ~1 V/ns | ~1 ps | ~5 ps |

  Five millivolts is not an exotic number for an unbuffered inverter: Vth spread, 1 MΩ bias vs leakage, local supply bounce from the neighbouring 10 MHz flip-flops. For the two sources this board was most motivated by, the analog front end is **tens to hundreds of picoseconds**, not 12.

* **Local temperature.** Buffer tempco of 5–10 ps/°C is why the fan-out is clustered. The squarers are *not* clustered; they sit in thirteen tiles. A 0.5 mV/°C Vth mismatch between two gates, with 1 °C of tile gradient, is 22 ps on the FE-5680A path. The heater exists because of this choice.

* **Same-rail digital bounce.** Fourteen analog-biased inverters share `+3V3_A` with twenty-six 10 MHz flip-flops. Per-gate ferrites help. They do not give a linear inverter PSRR. FF switching is **not** simultaneous across channels, so this is a differential error.

A real comparator (LTC6957, ADCMP600, even a PECL receiver) has a defined, supply-independent threshold and is the thing you buy when the source is a 0.7–2 V sine. The GU04 is the right cheap part for CMOS GPSDOs. This inventory is mixed. The common-mode story is good enough for Leo Bodnar / ZED-F9T squares. It is **not** good enough to claim 12 ps on unit 12.

I would not respin the board onto LTC6957 just to feel pure — JLCPCB stock and $20 × 14 was the original reason not to, and it is still a reason. I would **cut the claim**. Quote 12 ps as the digital quantum. Quote an expected analog floor that scales as 1/slew, and believe the null + a splitter test before publishing any sine-source ADEV below ~50 ps.

**§7.2 in one paragraph:** the common-mode argument is good for supply drift and for CMOS edges; it is not good enough for the analog sines, and those are the interesting oscillators. This, not the helper, is likely what limits the instrument.

### 3. Critical — PPS does not unwrap 100 ns (prompt §7.4)

[sheet_unit.py](../gen/sheet_unit.py) still says the pps is “Timed in the FPGA's 200.02 MHz domain to 5 ns”. That MMCM does not exist. [dmtd_capture.v](../gateware/rtl/dmtd_capture.v) stuffs beats *and* pps into the same helper-clocked synchroniser. Both are quantised to ~99.988 ns. `phases_ps()` never looks at pps. `unwrap_ps()` only works on a continuous series whose steps are < 50 ns of *input* phase.

Helper-clocked PPS cannot choose among 100 ns input-phase bins. It is the same stick you are trying to graduate with. Unit 13 has no pps at all.

That does **not** make the board useless. The original question is relative phase and frequency over seconds to weeks. A locked GPSDO at 1×10⁻¹⁰ wraps the 100 ns bin every ~1000 s; 10 Hz polling unwraps that with enormous margin. What you **cannot** do with the present PPS:

* Recover which 10 MHz cycle you were on after a power cycle.
* Distinguish a real 100 ns jump from a dropped beat.
* Assume a GPSDO’s pps is a known 10 MHz-cycle boundary. Often it is not; TIMEPULSE and 10 MHz are related by firmware, not by a documented analog phase.

Until there is a faster independent timestamp and a documented acquisition state machine, call the output **relative phase, continuously unwrapped**. Strike the sentence that says pps resolves the coarse ambiguity.

I would not add a 200 MHz MMCM just because an old note promised one. For oscillator comparison it is unnecessary. For “which cycle?” it is still marginal (GPS sawtooth is often > 5 ns). Either drop the claim or build a real coarse TDC.

### 4. High — the CLK1 null is not noiseless

The write-up repeats that CLK0 and CLK1 “come off the same PLL, so their beat is exact and noiseless.” Same PLL is true (Si5351A has only PLLA). Noiseless is false.

CLK0 is the integer MultiSynth: VCO 800.098752 MHz / 80. CLK1 at exactly 10.000000 MHz from that VCO needs MS = 80.0098752 — **fractional MultiSynth**, the configuration the helper was carefully steered away from. CLK1’s fractional-N jitter and spurs land in channel 13 as *signal*. Subtracting the null therefore removes helper-common noise and **adds** CLK1 synthesiser noise into every “GPSDO minus floor” plot.

A honest floor measurement is a splitter off one real GPSDO into two tiles. Keep the CLK1 jack; stop advertising it as the instrument floor.

Comment footgun, not a wiring bug: [pcb/helper.py](../pcb/helper.py) names `VIA_CLK1` the net from **pad 10 (CLK0)** to `HELPER_SRC`, and `VIA_CLK0` the net from **pad 9 (CLK1)** to the SMA. Pad numbers match the schematic and the MSOP-10 pinout. The names are swapped. The next person who “fixes the comments” will swap the clocks.

### 5. High — 1234.4 Hz vs the TCXO you actually bought (prompt §7.7)

Nominal separation from the 60 Hz comb: 34.4 Hz below 1200, **25.6 Hz above 1260**. That would be enough at ±0.5 ppm.

The fitted part is `FT5HNBPK25.0-T1`, **±2.5 ppm over −30 to +85 °C** ([README.md](../README.md) around the round-2 TCXO choice). The helper schematic still prints “±0.5 ppm” on the TCXO net. Those two sentences cannot both be true.

±2.5 ppm at 10.0012344 MHz is **±25.0 Hz** of beat.

| | Beat low | Beat high | Gap to 1200 | Gap to 1260 |
|---|---:|---:|---:|---:|
| ±0.5 ppm | 1229.4 | 1239.4 | 29.4 Hz | 20.6 Hz |
| ±2.5 ppm | 1209.4 | 1259.4 | 9.4 Hz | **0.6 Hz** |

At the hot end the beat sits on the 21st harmonic of 60 Hz. Aging (±1 ppm/year) finishes the job. Initial offset can be tuned out in the PLL fraction; **temperature cannot**.

1234.4 Hz is also 4.4 Hz off the centre of the (1200, 1260) gap. Parking the beat at **1230 Hz** with this TCXO still only gives 5 Hz of clearance, which I would not call comfortable, but it is not 0.6 Hz. The real fix is the ±0.5 ppm TCXO the first round asked for, or accepting that some fraction of lab days the 60 Hz comb aliases into the record and looks like oscillator drift.

Si5351 fractional-N close-in spurs: with the fraction in the PLL feedback and integer MultiSynth, the obvious fractional spur is around `f_PFD × b/c ≈ 99 kHz`, not inside a 1 Hz measurement bandwidth. I am less worried about that than the prompt is, **provided** the beat is not sitting on 1260 Hz. Right now it might be.

### 6. High — unpowered host, 3.3 V into 26 FPGA balls

Known, silkscreened, still wrong for a student board. PYNQ-Z2 table 15: unpowered I/O abs-max 0.55 V. Bench posts + this board + PYNQ off = 3.3 V into 13 beats + 12 pps + helper. The host’s 200 Ω limits the current; it does not make the voltage legal.

Pins 1 and 17 are NC, so the board cannot even *see* host 3.3 V. Sense pin 1 (high-Z, no load) and hold every FPGA-facing output in Hi-Z / powered-down until it is present. Or delete the bench 5 V posts. Silkscreen is not an interlock.

I would not give this to a lab as-is. I would still fab one board for the people who wrote it.

### 7. Medium — FF1 metastability / FF2 (prompt §7.3)

The two-flop arrangement is right. A synchroniser in front of FF1 would destroy the measurement. FF2 does not quantise away information you wanted: the information **is** which helper edge the data transition fell nearest, i.e. a 12.3 ps referred quantum. 74LVC1G80 τ is small compared with 100 ns, so FF2 samples a resolved level with absurd MTBF.

What the aperture **does** to the 12.3 ps figure: when the 10 MHz edge lands inside the FF1 metastability window, the beat edge dithers by one helper count. That window is tens of picoseconds at the pins, which is the same order as the quantum, not femtoseconds. Average it; do not quote 12.3 ps single-shot as analog truth. The inverting Q of the 1G80 is handled by using two of them. Pinout 1=D, 2=CLK is checked against TI and Nexperia. I have no complaint with the topology.

### 8. Medium — helper reference is an undocumented XA drive

[sheets_rest.py](../gen/sheets_rest.py) says this out loud: Si5351A has no CLKIN (that is the C), XA/XB abs-max is −0.5 to +1.3 V, Silicon Labs publish no recommended external-clock level, XB is open. The 3k3/1k + 10 nF is a reasonable attempt. TP_XA is the right probe point.

This can fail to start, lock to the wrong overtone-ish mode of the on-die oscillator, or add ugly AM on the reference. The DNP crystal is the datasheet mode and throws the beat at the 60 Hz comb (±10 ppm → ±100 Hz). The Si5351C would have ended this conversation; it was rejected on QFN and stock. Fair, if you treat first silicon as an experiment.

I would not respin. I would bring the TCXO–divider–Si5351 up on a dead-bug before trusting a 590-part assembly, and I would keep Y3001 pads.

### 9. Medium — thermal design (prompt §7.5)

9.6 W, 24 resistors, three SOT-223s dissipating 0.8 W each at ~50 °C rise, Python loop, 34 °C setpoint: this is a lot of board being spent on a problem created by the squarer and by not calibrating tempco.

The spreading-length argument (perimeter-only heating leaves the middle at ~34 % of the edge rise) is qualitatively right and is why there are in-tile heaters. It does not make the three pass FETs into a uniform field. They are 0.8 W point sources, hotter than any 560 Ω, and they sit on the same copper the TMP1075s are trying to flatten.

A heated board is the wrong *first* answer. Measure dφ/dT with the eight thermometers and no heater. If the residual after subtracting a linear combination of those eight is still the floor, *then* turn the heater on. Shipping the DAC able to apply 9.6 W at half-code on a virgin EEPROM is how you cook a first article. Known item; still a gate.

Linear drive rather than PWM is the correct call on a picosecond ground plane.

### 10. Medium — In2 is not “helper and nothing else”

[pcb/build_pcb.py](../pcb/build_pcb.py) lines 1–8:

```
L3  In2.Cu    the fourteen helper-clock branches, and NOTHING else
```

Later in the same file, In2 carries beat and pps returns, I²C, heater drains, `+3V3_D` trunks, because the maze router could not finish on F.Cu. The isolation story (stripline between two grounds, 6.08 mm same-layer analog-to-helper) is still mostly true for the *front ends*. It is not true as a layer discipline. Helper at 10 MHz sharing In2 with 1.2 kHz CMOS squares is probably fine — those squares are strong. Helper sharing In2 with analog-adjacent vias is the case I would actually look at in KiCad, and I did not.

“Passes DRC” is not “well routed”. I am not going to pretend I inspected 207 × 180 mm of maze output. I will say the router’s own comments record several “this was tried and failed” episodes, which is the right attitude, and that a human should still scroll the helper spine, the header neck, and every analog tile before tape-out.

### 11. Medium — manufacturing (prompt §7.9)

CPL rotations are KiCad-native, no per-package correction. SOT-23-5 appears **59 times on one board** (1G80 + 1GU04 + 1G17 + 1G34 + LDOs…), plus SOT-223 tabs and SOIC-8s. Those are exactly the JLCPCB packages that come in rotated. Assembly drawings are better than nothing; they are not a correction table.

The annotated BOM is for **5 boards**, ~$207 SMT+assembly plus THT. For an analog front end that has never seen a beat, that is how you buy five copies of a heater-FET tombstone.

Acceptable path: **one** assembled board, first-article inspect every SOT-23-5 and SOT-223, then copy. I would rather you apply a vetted SOT-23-5 rotation correction than rely on drawings.

369 silkscreen-on-pad reference designators: the fab clips them. Live with it.

### 12. Low — leftover comments that are now lies

These are the JP_NULL class. They calibrate how much to trust notes:

* [design.py](../gen/design.py) pin 31: “DNP 0R alternate helper input”. There is no such 0 Ω. After `_reorder_header()` the comment is overwritten anyway.
* Helper sheet: TCXO “±0.5 ppm”. The part is ±2.5 ppm.
* PPS note: “200.02 MHz domain to 5 ns”. Gateware is helper-clocked.
* `helper.py`: CLK0/CLK1 via names swapped.
* Stackup: “In2 = helper only”.

None of these are ERC. All of them are how the next round introduces a real short.

### 13. Low — student-destroyable inputs

ZED-F9T TIMEPULSE into a fitted 50 Ω jumper is 66 mA into a 5 mA abs-max pin. TM-4 unterminated is ~7.4 V on a 6.5 V abs-max gate. Jumpers ship **removed**, which protects the u-blox and exposes the TM-4. BAV99 is DNP because 10 nA × 1 MΩ = 10 mV of bias, doubling every 10 °C. Fit the clamp on unit 1 only, or print a skull on JP101. Do not rely on the PDF notes.

---

## Prompt §7 items I am *not* going to pile on

**Single-ended everything (§7.6).** At 10 MHz on SMA, single-ended is normal. The picosecond-class worry is helper distribution, and they did the right cheap things: clustered buffers (threshold tempco beats copper), buried stripline, series 33 Ω. Differential helper would want an LTC6957 and a different host connector. Not the respin I would spend.

**Two-flop sampler (§7.3 topology).** See finding 7. This is not the thing to change.

**Generator-driven CAD (§6, §7.8).** The trade is right **for this board**. Thirteen identical tiles, one header table feeding schematic + XDC + driver constants, bit-identical rebuild: that is how you stop the pin map from drifting. The cost (cannot nudge a part in the GUI; reviewers must read Python) is real and already paid. A hand-drawn schematic would not have been more correct; it would have been less reviewable. I will not tell you to start drawing in the GUI.

I *will* tell you that comments in the generator have started to lie, and that a maze router with a 0.5 mm grid and an opt-in via check is a place where “DRC 0” can coexist with an ugly neck. Look at the copper once with human eyes.

**Pin map vs Icepi Zero.** Pin 18 as helper is the one pin that is clock-capable on both. That constraint is load-bearing and should stay. Icepi compatibility is electrical only; the overlay is Zynq.

---

## Is 207 × 180 mm, 4 layers, 590 parts a sensible answer?

As a way to **compare thirteen GPSDOs simultaneously** for three-cornered-hat ADEV, yes. As a way to **find out how good the collection is**, no. Two channels and a travelling standard, or a TICC, or an analog DMTD on a sound card, answers the scientific question at a fraction of the parts count. This board is also a teaching piece about generated CAD and White-Rabbit-style DDMTD. Those are fine reasons. They are not the same reason as “we need 12 ps or we cannot see the oscillators.”

You will see the interesting oscillators through their slew, not through N = 8101.

---

## What I would refuse to sign off before spending the money

1. **Si5351 (and DAC EEPROM) software**, tested on a real 5351A, not on `axi_iic` returning 0xC0.
2. **Order quantity 1**, not 5.
3. **Claims list on the silkscreen / README:** strike “12 ps” as an instrument spec; strike “pps resolves wrap”; strike “CLK1 null is noiseless”; fix “±0.5 ppm”.
4. **No heater power** until EEPROM is `PD=01` data 0.
5. **A first-article rotation check** on SOT-23-5 / SOT-223, or a correction table.
6. **Either** a host-power interlock **or** removal of the bench 5 V posts.

I would **not** refuse the GU04, the two-flop, the Si5351A, the generated CAD, or the 4-layer stackup. I would not start over.

---

## If I were changing hardware on a respin

In order, and only after one Rev A has spoken:

1. ±0.5 ppm TCXO, or move the beat to the centre of a 60 Hz gap and still not trust ±2.5 ppm.
2. Host-3V3 sense on pin 1, FPGA-facing outputs held off.
3. BAV99 fitted on the TM-4 channel.
4. CLK0/CLK1 comment names fixed; consider a splitter null as the official floor.
5. If sine-source ADEV is the point of the instrument, one comparator-grade front end on unit 12, not fourteen LTC6957s.

Do not add a 200 MHz pps TDC unless you have a use for absolute cycle count.

---

## Schematic things that look simply wrong

I did not find a repeat of the 0x60 clash, the SCL-to-3V3 power-symbol short, or the floating SOT-223 centre lead. I²C map as drawn is clean: DS2482 `0x18`, TMP1075 `0x48–0x4F`, Si5351 `0x60`, MCP4725 `0x61`. Header pin 18 is nailed. Unit 13 has no pps. Terminator policy matches the sources.

What is “simply wrong” is documentation that describes a different instrument than the RTL and the BOM: 200 MHz pps, ±0.5 ppm TCXO, noiseless CLK1, In2-only-helper, DNP alternate helper on pin 31. Those are how silent schematic errors get reintroduced.

---

## Bottom line

Digital DMTD with a common helper and on-board samplers is the correct architecture for a mixed 10 MHz / 1 pps collection on a PYNQ-Z2. The generator is the correct way to build thirteen copies of one tile. The analog zero-crossing detector, the missing device software, the over-claimed pps/null/12.3 ps story, and the TCXO-vs-mains arithmetic are what keep this from being the instrument the prompt describes.

Build the I²C, buy one, measure the null and a splitter, then decide whether you own a GPSDO comparator or a well-documented 1.2 kHz square-wave generator.
