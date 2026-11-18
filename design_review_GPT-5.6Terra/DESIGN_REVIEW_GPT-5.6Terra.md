# GPSDO-PYNQ-Z2 design review

Date: 2026-09-13

## Follow-up review scope

User direction recorded 2026-09-13:

> Actually dive into the schematics and the PCB. We are going to measure the
> things you suggest, but for $100, we're going to measure it on this board
> itself. We need to know if there are catastrophic issues with the schematic
> or PCB that would prevent bring-up and testing of exactly the things you
> suggest. Record this prompt in your .md, look at the schematics and PCB, and
> add to your review with what you find.

This follow-up therefore distinguishes an actual bring-up/test blocker from a
performance uncertainty that a Rev A prototype can characterize.

## Verdict

Do **not** release Rev A to fabrication as the instrument described. The basic
DDMTD topology and the two-flop front end are reasonable, and the generated
board flow is a strength, not a problem. Three properties needed for a usable,
repeatable instrument are not presently established:

1. The proposed PPS mechanism cannot resolve a 100 ns DDMTD wrap after a
   restart or discontinuity.
2. The only normal helper reference drive is an explicitly undocumented use of
   the Si5351A crystal pins.
3. The board can drive an unpowered PYNQ-Z2 through 26 FPGA I/O pins.

The absent device-level I2C software is an acknowledged functional blocker,
rather than a newly discovered schematic error. It is nevertheless a release
gate: without it the board has no intended helper clock and therefore no
measurement.

## Findings

### 1. Critical: PPS does not establish the coarse DDMTD cycle count

A raw DDMTD result is modulo one 10 MHz period (100 ns). To choose the integer
cycle after startup, a coarse observation must be meaningfully finer than one
cycle and must have a known relationship to each source's 10 MHz output.
Neither condition is implemented.

`gateware/rtl/dmtd_capture.v` maps both `beat` and `pps` into `raw` and puts
both through the same synchronizer/counter clocked by `helper_clk`. Therefore
both get the same roughly 99.988 ns sampling granularity. The PPS path has no
capture clock, carry chain, TDC, or counter at 200 MHz. This directly conflicts
with `gen/sheet_unit.py`, whose PPS note says it is timed in a 200.02 MHz FPGA
domain to 5 ns.

The host code confirms the gap. `DmtdRegisters.snapshot()` returns PPS
timestamps, but `phases_ps()` uses only beat timestamps. `unwrap_ps()` can
unwrap a continuous series only if every step is less than half a wrap; it
cannot determine the missing integer at a power cycle, a dropout, or a real
phase step. Unit 13 has no PPS, so it cannot independently seed the null
reference either.

This is not a small resolution shortfall. Two situations separated by an exact
100 ns at the 10 MHz input produce the same DDMTD phase, while the helper-clock
PPS capture is at essentially that same scale. The claimed coarse channel
cannot select between them.

Required correction:

* Add a genuinely independent coarse PPS timestamp, for example a calibrated
  200 MHz or faster capture domain, and expose it in the driver.
* Define and verify the PPS-to-10-MHz phase relationship of every supported
  source. A GPSDO's PPS output is not automatically a known 10 MHz cycle
  boundary just because both are disciplined.
* Make acquisition explicit: use the coarse result to choose an integer wrap,
  reject ambiguous acquisition, and retain an unwrap state with explicit
  gap/cycle-slip handling. Sources without PPS need a defined manual or
  transfer-calibration acquisition procedure.
* Add a simulation that begins with every possible integer 100 ns offset and
  proves that startup, a missed beat, and an interrupted run either select the
  right integer or raise an unambiguous fault.

Until this exists, call the output a continuous *relative phase-change* stream
only. It cannot meet the stated coarse-phase recovery claim.

### 2. Critical: the helper reference relies on an undocumented oscillator input mode

`gen/sheets_rest.py` explicitly states that driving Si5351A XA is not a
documented mode and that Silicon Labs publishes no permitted drive level. The
normal configuration AC-couples a divided TCXO waveform into XA while XB is
open. The suggested fallback is a DNP crystal, not a qualified external-clock
mode.

This is a fabrication risk, not merely a bring-up detail. The TCXO/SI5351
combination creates every sampling clock. Failure to start, injection locking
outside the expected range, excess added jitter, or lot/temperature sensitivity
means the DDMTD is absent or its performance is unknown. Seeing 0.77 Vpp at the
probe point only proves the drive exists; it does not qualify oscillator-loop
operation across parts, voltage, and temperature.

Required correction:

* Select a synthesizer with a specified external reference/CLKIN mode (the
  Si5351C is the obvious family-level candidate) or use a fully documented
  oscillator/reference architecture.
* If Rev A deliberately retains the injection method, make it an engineering
  qualification gate before any production order: test multiple devices over
  supply and the full heated/ambient range for startup margin, frequency,
  close-in phase noise/spurs, and recovery from power cycling. The result must
  be compared against a known-good reference architecture, not only observed
  on a scope.
* Do not represent the DNP crystal as an equivalent fallback. It changes the
  helper-frequency plan enough to lose the designed beat placement and it does
  not validate the intended TCXO architecture.

### 3. High: bench power with the host off violates the PYNQ I/O absolute maximum

The design intentionally generates local 3.3 V rails while every beat, PPS,
and helper line is directly connected to an RPi-header FPGA I/O through only
the PYNQ's 200 ohm series resistor. The review brief and `gen/sheets_rest.py`
both record that an unpowered Zynq I/O absolute maximum is 0.55 V; they do not
add isolation or a power-good interlock.

This is not made safe by the existing 200 ohm resistor. In the simple clamp
model, one 3.3 V output can attempt about $(3.3 - 0.55) / 200 = 13.75$ mA into
an unpowered bank before driver and clamp limits. There are 26 driven outputs.
Actual current will vary, but relying on uncontrolled ESD-diode back-powering
is not an acceptable operating mode and can partially power banks, disturb the
PYNQ rail sequence, or damage either board.

Required correction:

* Add fail-safe isolation/level translation for all board-to-PYNQ outputs, or
  arrange output enables that remain disabled until the relevant PYNQ bank is
  valid. The helper input needs the same protection.
* Give the front end a defined safe state during host reset/off conditions.
* Add a power-sequencing test to the release checklist, including host-off
  current and voltage measurements. A procedural warning is not sufficient
  when the normal bench setup makes the unsafe state easy to create.

### 4. High: configuration software is a release gate, with no executable device test

The overlay contains `axi_iic`, but there is no Si5351, TMP1075, MCP4725, or
DS2482 device driver. `gateware/driver/dmtd.py` documents this explicitly. The
DDMTD simulation drives `helper_clk` directly, so it bypasses the synthesizer,
I2C bus, device addresses, output-enable state, and the unqualified XA clock
injection. The real-board self-test only tests the already-running helper and
edge counts.

The issue is larger than writing I2C bytes. The program must configure both
CLK0 and the null-channel CLK1 deterministically, validate that the helper is
within tolerance before collecting data, confirm every I2C identity/address,
and ensure the heater DAC cannot power up to a nonzero EEPROM value. The last
point is already called out in the design notes and should be resolved before
energizing a heater-equipped board.

Required correction:

* Implement a generated, reviewed Si5351 register image from the declared
  frequency parameters, plus readback and a measured-helper acceptance check.
* Implement and test the full I2C address map, temperature reads, DAC safe
  initialization, and DS2482 discovery.
* Add a hardware smoke-test sequence that first forces the heater safe, then
  validates CLK0/CLK1 and all I2C devices, before enabling normal capture.
* Keep the unit tests, but add a bus-level model or a sacrificial-board test.
  A testbench with an ideal helper input cannot validate the system blocker.

### 5. Medium: the null channel is not a calibration of the other twelve channels

The null-channel arrangement is useful: it measures a repeatable local path
and rejects helper noise that is truly common to CLK0 and CLK1. It does not,
however, make the remaining channels calibrated. `phases_ps()` subtracts one
instantaneous channel-13 timestamp; it has no per-channel offset or
temperature-correction vector.

Each real channel has its own SMA/cable, coupling network, unbuffered-inverter
operating point, two flip-flops, and output path. Their static delays are
expected to be large compared with picoseconds. More importantly, temperature
and amplitude-dependent changes are not guaranteed to track the null channel.
The null signal is a clean CMOS CLK1 output, whereas the measured inventory
includes sine sources spanning at least 0.72 to 4 Vpp at 50 ohm and CMOS
sources. It is a valid noise-floor monitor, not a complete front-end transfer
standard.

This does not prevent excellent frequency stability measurements: a fixed
phase offset drops out of frequency and Allan-deviation calculations. It does
prevent interpreting `phases_ps()` as an absolute, calibrated oscillator phase
comparison.

Required correction:

* Define the measurement product as either uncalibrated relative phase or
  calibrated phase, and make the API name/metadata reflect that choice.
* For calibrated phase, add a traceable transfer-calibration procedure that
  sends one source through every channel, stores an offset per channel, and
  rechecks it over temperature and after cable changes.
* Use the null channel as a monitor and alarm input, not as evidence that all
  front-end error sources are removed.

### 6. Medium: the helper spur and thermal claims remain unqualified performance risks

The stated 25.6 Hz separation from the 60 Hz comb is sensible as a placement
choice, but it is not a phase-noise or spur budget. The Si5351 uses a fractional
PLL, the XA drive is undocumented, and the result needs to support analyses at
about 1 Hz bandwidth. No calculation or test links fractional spurs, supply
pushing, heater current, fan-out-buffer drift, and input-squarer noise to an
allowable phase-noise floor.

Likewise, a 9.6 W distributed heater with three linear SOT-223 hot spots is an
experiment, not an established thermal control system until it is measured on
hardware. Eight sensors can show a gradient but cannot prove all thirteen
squarers and flip-flops track closely enough for the claimed ps-scale accuracy.
The 7 mm bypass placement and uncorrected assembly rotations add avoidable
uncertainty to that first experiment.

Required correction:

* Establish an error budget in input-referred ps/sqrt(Hz), including the
  squarers, flip-flops, fan-out, supply rails, helper noise/spurs, thermal
  gradients, and FPGA edge capture.
* Build and characterize a small helper/front-end coupon before buying a full
  590-placement assembly, or deliberately treat the first full assembly as a
  prototype with a no-performance-claim disposition.
* Obtain a verified manufacturer-specific CPL rotation mapping or a first-article
  placement inspection. Assembly drawings aid review; they do not correct a
  machine's interpretation of a CPL file.

## What I would retain

* The shared-helper DDMTD topology is appropriate for relative frequency and
  phase-noise measurements.
* FF1 deliberately sampling an asynchronous input and FF2 retiming it is the
  correct basic DDMTD pattern. The second flip-flop does not discard an analog
  fine-time value; the measurement is the selected helper cycle. Its remaining
  uncertainty is the intended one-helper-cycle quantization plus real-device
  noise.
* Generator-driven schematic, PCB, constraints, and software constants are a
  strong choice here. The corrected generated wrap constant is internally
  consistent: `F_HELPER / F_BEAT = 8102.101749835533` helper cycles per beat,
  and multiplying it by `T_RES_PS` produces exactly 100000 ps.

## Release gates

I would require all of these before treating the design as fabrication-ready:

1. A documented, tested acquisition/unwrapping protocol that resolves a
   100 ns cycle or rejects ambiguity.
2. A documented helper reference input architecture, or a successful PVT
   qualification of the chosen injection scheme.
3. Hardware-safe PYNQ power-off/reset isolation.
4. A tested I2C bring-up and safe-heater sequence.
5. An error budget and a coupon or explicit prototype plan for the analog,
   clock, thermal, and assembly risks.

## Review scope

This was a static review of the generated design, gateware, driver, schematic
generator, release manifest, and supplied datasheets. I did not claim a visual
copper/gerber approval or substitute for laboratory characterization. The
present DRC/ERC status is useful, but it cannot test the functional and
metrological failure modes above.

## Follow-up: schematic and PCB audit

### Revised prototype verdict

For the stated purpose of spending about $100 to characterize this exact
design, I found **no catastrophic schematic or PCB defect that should prevent
bring-up or those measurements**. I would order it as a prototype, subject to
the known software work and the controlled power-up sequence below. The earlier
"do not release" verdict applies to claiming a finished, calibrated instrument;
it should not be read as a reason to avoid a first board whose explicit purpose
is to resolve the remaining measured uncertainties.

The best escape hatch is already on the board. `EXT HELPER IN` has a 51 ohm
termination and DNP `R3004`; the normal Si5351 path uses fitted `R3005`. If the
Si5351/XA injection scheme does not start or is noisy, remove `R3005`, fit
`R3004`, and inject a known-good 10.0012344 MHz helper. That permits testing
the fan-out, all thirteen front ends, the PYNQ capture path, and the thermal
effects without depending on the unqualified reference-injection mode.

### What was checked

* Rebuilt the complete generated schematic with `python3 build.py --no-pcb`.
  KiCad ERC found zero violations; `check.py`, `check_netlist.py`,
  `check_paths.py`, and `check_overlap.py` all passed. The power-path walker
  traces the two LDOs from `+5V_HDR` through the fuse, Schottky, and ferrite,
  and independently traces Si5351, DAC, and DS2482 supplies from `+3V3_D`.
* Rendered and inspected the power, helper, RPi header, housekeeping, probe,
  and representative channel sheets. The actual netlist agrees with the
  critical pin assignments: LDO input/enable and output pins, Si5351 VDD/VDDO,
  CLK0/CLK1, MCP4725 address strap and output, DS2482, all three heater FETs,
  the 15 V jack, and every RPi-header connection.
* Rendered top and bottom PCB views. The 27 SMA connectors and power/probe
  connectors are edge-accessible, all SMT parts are on top, and the Raspberry
  Pi socket is the sole bottom-side component. The stated PYNQ clearance model
  is consistent with this placement; there is no observed component collision
  or blocked connector.
* Filled a copy of the PCB using KiCad's bundled `pcbnew` and reran KiCad DRC.
  The filled board has **zero error-level violations and zero unconnected
  items**. The generated source board intentionally stores zones unfilled, so
  its unfilled DRC reports 436 ground opens; those disappear after the same
  zone-fill step used by the release flow.
* Compared released assembly data: the BOM and CPL each contain exactly 457
  unique assembled designators, with no duplicate, missing, or extra entries;
  all CPL placements are top-side.
* Checked the DS2482 datasheet against the probe schematic. Its internal
  `RWPU` is a 1.0 to 1.675 kohm weak pull-up, so omitting a separate 4.7 kohm
  1-Wire pull-up is correct. The five star branches have their own 47 ohm data
  resistors and should be tested at `TP_1W` as documented.

### Non-blocking issues found

1. **Clear the remaining DRC warnings before a polished release.** Full-severity
  DRC on the filled board reports 639 warnings: 37 dangling-track endpoints,
  four hole-to-hole warnings, one silkscreen-edge warning, and the remainder
  silkscreen/text-height/overlap warnings. The filled board still has zero
  unconnected pads. Most dangling ends are intentional distribution trunks
  that join same-net poured copper; the only signal-net cases are very short
  redundant stubs on PPS_03 and PPS_05. They do not block operation, but they
  make a future real open harder to notice.

2. **Fix the two distinct drill-spacing cases.** A via sits in the I2C_SCL
  through-hole pad of debug-header J5001, and its duplicate report is a
  same-net redundant drill rather than a short. A separate +5V_HDR via near
  RPi socket J4001 pad 4 has 0.2384 mm drill-to-drill clearance against the
  configured 0.2495 mm minimum. It is also same-net and cannot prevent
  bring-up, but should be moved or the manufacturable rule explicitly agreed
  with the fabricator before calling the design production-ready.

3. **Reconcile the hardware revision identifier.** `gen/design.py` and all
  rendered schematic title blocks say Rev A, while `pcb/build_pcb.py` hard
  codes `GPSDO DDMTD FRONT END rev B` into the PCB silkscreen. This is a
  documentation/release-control defect, not an electrical one. Resolve it
  before ordering so the board, fabrication archive, assembly drawing, and
  bring-up notes identify the same revision.

4. **KiCad schematic-parity DRC is presently unavailable.** KiCad reports that
  it cannot fetch an annotated schematic for parity checking, despite the
  normal generated netlist/ERC checks passing. That does not show a mismatch,
  but it removes a useful independent check. Make the parity invocation work
  or document why this hierarchical generated project cannot use it.

### Safe first-board sequence

1. Mount the front end on a powered PYNQ-Z2 before applying 5 V to the bench
  posts. Do not use the board as a stand-alone powered target: its driven
  header signals violate the host-off I/O absolute maximum.
2. Leave the 15 V heater supply disconnected initially. This makes DAC EEPROM
  state and low-gate-voltage FET behavior harmless while the digital board is
  established.
3. Prove the 5 V and both 3.3 V rails at the marked test points. Enumerate the
  I2C devices, program the Si5351, and verify CLK0 and CLK1. If this fails,
  use the external-helper rework path above; it isolates the analog/capture
  test program from the synthesizer reference question.
4. Verify helper presence at the FPGA, then TP_BEAT on one channel before
  testing all channels. The existing gateware self-test establishes helper
  liveness and edge counts once the device-level I2C configuration exists.
5. Only then connect 15 V and characterize the heaters, FET temperatures,
  rail noise, and temperature distribution. Characterize the null channel,
  supply current, helper noise/spurs, and PPS behavior as experiments, not as
  assumed properties.

The concrete conclusion is therefore narrow: finish the I2C/device bring-up
software and order the first board as an instrument-characterization prototype.
None of the reviewed schematic or PCB issues should stop that plan.
