# Gateware for the GPSDO DDMTD front-end

The front-end board turns thirteen 10 MHz GPSDO outputs into thirteen ~1234 Hz
beats by sampling each one with a common 10.0012344 MHz helper. All the
FPGA has to do is record **when** each beat edge happened, counted in helper
cycles. That is the whole measurement: one helper cycle of displacement
between two channels' beat edges is 12.3425 ps of phase between their 10 MHz
inputs.

Everything here is scripted. There is no saved block design, no GUI state and
no checked-in project — `build.tcl` builds all of it from the RTL, the board
files and `gen/design.py`, so the result is a diff rather than a screenshot.

## Layout

| path | what it is |
|---|---|
| `rtl/dmtd_capture.v` | the measurement core: AXI4-Lite, 13 beats + 12 pps |
| `sim/tb_dmtd_capture.v` | self-checking testbench, 47 checks |
| `build.tcl` | project, block design, synth, impl, bitstream, handoff |
| `sim.tcl` | runs the testbench, non-zero exit unless it passes |
| `bringup.tcl` | talks to the core over JTAG with no PS and no network |
| `bd_diagram.tcl` | draws the block diagram headlessly, from the BD itself |
| `gen_xdc.py` | generates `xdc/pins.xdc` from `gen/design.py` |
| `gen_constants.py` | generates `driver/dmtd_constants.py` from `gen/design.py` |
| `driver/` | the PYNQ driver, plus host-side tests that need no board |
| `board_files/pynq-z2/` | vendored board files, so no network and no install |

Two things are generated from `gen/design.py`, which is the same file the
schematic and the PCB come from: the pin constraints and the driver's
constants. The board, the gateware and the driver therefore cannot disagree
about which GPSDO is on which pin, or what a helper cycle is worth in
picoseconds.

## Build

```sh
vivado -mode batch -source gateware/build.tcl
```

Produces `build/overlay/dmtd_top.bit` and `.hwh` — the pair PYNQ wants — plus
`.xsa`, a Graphviz block diagram, and utilisation and timing reports.

The build **refuses to publish a bitstream that fails timing**. The first
build of this design closed at WNS = −4.275 ns and still wrote a `.bit`, which
is the exact failure this check exists to prevent: such a bitstream loads,
mostly works, and is wrong occasionally and unrepeatably.

Options:

| flag | effect |
|---|---|
| `-synth_only` | stop after synthesis |
| `-jobs N` | parallel jobs (default 8) |
| `-bench` | add a JTAG-to-AXI master, for bring-up. Writes to `build/bench/` |
| `-plclk` | implies `-bench`, and clocks the AXI fabric from H16 via an MMCM with a tied reset, so nothing in the PL depends on the PS. **Plug in an Ethernet cable first** — H16 is the Ethernet PHY's CLK125, not an oscillator |

`-bench` and `-plclk` are debug builds and are never the delivered overlay: an
unauthenticated AXI master reachable over JTAG is a tool, not a feature.

## Simulate

```sh
vivado -mode batch -source gateware/sim.tcl
```

The testbench drives the real AXI4-Lite handshake — offering AW and W in the
same cycle, the way SmartConnect does — and checks the thing that actually
matters: that the **difference** between two channels' timestamps equals the
number of helper cycles between their edges. It also checks channel mapping,
the register map, liveness, the helper-frequency estimator, and that ALIVE
drops when the helper stops.

It exists because it found a real bug. See "The write bug" below.

## Bring-up on hardware

```sh
vivado -mode batch -source gateware/build.tcl -tclargs -plclk
vivado -mode batch -source gateware/bringup.tcl
```

This needs only the USB cable. It programs the PL and drives the measurement
core from a JTAG-AXI master, so it works on a board with no SD card, no
console and no network — which is the state a new board is usually in.

With nothing plugged into the front-end header there is no helper clock, so
`ALIVE` reading 0 is a **pass**: it means the helper watchdog works. What gets
tested is identity, the address map, and the write path.

### If `bringup.tcl` says there is no debug core

The bitstream contains one, so this means its debug hub is not answering,
which means **its clock is not running**. In the `-bench` build the fabric is
clocked by the PS's `FCLK_CLK0`, and `FCLK_CLK0` only runs once something has
configured the PS — an FSBL from the SD card, or `ps7_init` over JTAG. So this
message means the board has not booted: check that an SD card is in the slot
and that the JP4 boot-mode jumper selects SD rather than JTAG.

`-plclk` is the way in while that is true. It clocks everything from H16
instead, which needs nothing from the PS — but **H16 is the Ethernet PHY's
CLK125, not an oscillator**, so put a cable in the Ethernet jack first or the
PHY will stop and restart the clock about once a second.

## On the PYNQ

```sh
scp build/overlay/dmtd_top.bit build/overlay/dmtd_top.hwh xilinx@<board>:~/gpsdo-dmtd/
scp -r driver board/* xilinx@<board>:~/gpsdo-dmtd/
ssh xilinx@<board> 'cd ~/gpsdo-dmtd && ./pynq-run run_selftest.py'
```

```python
import driver
from driver import attach
from pynq import Overlay

ol = Overlay('dmtd_top.bit')          # the .hwh must sit next to it
d  = attach(ol)                       # NOT ol.dmtd_capture_0 -- see below
d.selftest()
d.phases_ps()                         # ps of each GPSDO vs the null channel
```

**Use `attach(ol)`, not `ol.dmtd_capture_0`.** The driver binds correctly by
VLNV — `ol.ip_dict['dmtd_capture_0']['driver']` is `DmtdCapture` — but pynq
3.0.1 also invents an empty *hierarchy* with the same name as the IP, and
`_IPMap.__getattr__` checks hierarchies before IP, so the attribute returns an
empty `DocumentedHierarchy`. Seen with a `module_ref` IP; the packaged
`axi_iic` in the same design is fine. `driver/dmtd.py`'s `attach()` docstring
records what was ruled out. See `board/README.md` for the three PYNQ 3.0
environment traps (`pynq` is in a virtualenv, `XILINX_XRT` is not inherited by
`sudo`, overlay loading needs root); `board/pynq-run` handles all three.

`driver/` is a package: copy it to the board next to the bitstream. Its tests
run anywhere, with no board and no PYNQ installed:

```sh
python3 -m unittest discover -s gateware/driver -t gateware
```

## Register map

AXI4-Lite, 32-bit, 4 kB, at `0x43C0_0000`.

| offset | | |
|---|---|---|
| `0x000` | R | `ID` = `0x444D5444` ("DMTD") |
| `0x004` | R | `VERSION` = `{maj, min, N_BEAT, N_PPS}` |
| `0x008` | RW | `CONTROL`: write bit 0 to zero the counter and all edge counts. Reads back a bit that toggles on each such write |
| `0x00C` | R | `HELPER`: PS clocks per 2²⁰ helper cycles; 0 means no helper |
| `0x010` | R | `LIVE_LO` — free-running helper counter, refreshed every ~102 µs |
| `0x014` | R | `LIVE_HI` |
| `0x018` | R | `ALIVE`: bit 0 = the helper clock is running |
| `0x200 + 16n + 0` | R | channel *n* timestamp, low word |
| `0x200 + 16n + 4` | R | channel *n* timestamp, high word |
| `0x200 + 16n + 8` | R | channel *n* edge count, free-running, wraps at 2³² |

`n = 0..12` are the beats, `n = 16..27` are the pps returns. Channel 12 is
the null channel: the helper against itself through an identical signal path,
which is the instrument's own noise floor and the thing to subtract.

Read the timestamp **and** the count together. The count says how many edges
have happened since you last looked, so polling from Python at 10 Hz loses
time resolution but never returns a stale or ambiguous phase. Every multi-word
read in the driver is retried until it is self-consistent, because the helper
domain can update a timestamp between two AXI transactions.

## The scale factor

One helper cycle of beat displacement is `T_helper / N_GAIN` = **12.3425 ps**
of input phase — the *helper* period divided by the gain, not the signal
period. The identity that settles it: shifting an input by exactly one 10 MHz
cycle is unobservable, so one whole beat period of displacement must be
exactly 100 ns of input phase. A beat period is `F_HELPER/F_BEAT` = 8102.1
helper cycles, **not** `N_GAIN` = 8101.1, which is the time-stretch gain and a
different quantity that sits right next to it. `gen/design.py` had this wrong
by 123 ppm — not noise, a scale error, so it grows with the phase being
measured (6 ps at a 50 ns reading). Corrected 2026-09-13.

## The write bug

The AXI write decode compared the incoming write data against `awaddr_q`, the
registered write address — in the same cycle that `awaddr_q` was being written
by a non-blocking assignment. SmartConnect offers AW and W together, so the
decode always saw the *previous* transaction's address: every write went to
the address of the write before it, and the **first** write of a session
compared against the reset value and was silently dropped. `BRESP` was `OKAY`
throughout, so nothing anywhere reported a problem.

The fix accepts the two channels independently into their own holding
registers and decodes only once both have arrived. The testbench makes the
first CONTROL write of the simulation a real test, and `bringup.tcl` checks
the same thing on silicon through the CONTROL toggle-bit readback.

## Status

Verified on a real PYNQ-Z2 (PYNQ 3.0.1, kernel 5.15.19-xilinx-v2022.1):

* the overlay loads through `pynq.Overlay`, `fclk0` reads 100.000000 MHz, and
  the `.hwh` parses with `dmtd_capture_0` at `0x43C00000` and `axi_iic_0` at
  `0x41600000`;
* `ID` reads `0x444D5444` and `VERSION` reads v1.0 / 13 beats / 12 pps;
* `selftest()` reports the helper stopped and every beat channel dead, which
  is the correct answer with nothing plugged in;
* the AXI write path, the address map and `axi_iic` were checked over JTAG
  before that (`bringup.tcl`, 13/13).

## Not done yet

* **I²C device drivers.** `axi_iic` is in the overlay at `0x4160_0000` and
  answers, and pynq binds its own `pynq.lib.iic.AxiIIC` to it, so the
  controller driver is already written — but nothing drives the Si5351, the
  eight thermometers, the DAC or the 1-Wire bridge. **The Si5351 is the
  blocker**: it generates the helper, and until it is programmed to
  10.0012344 MHz there are no beats at all and every channel reads zero.
  Note the Si5351A in 10-MSOP is permanently at I²C address `0x60` (no A0
  pin), and the heater DAC was moved to `0x61` to avoid it.
* **No measurement has been taken.** Nothing has ever been plugged into the
  front-end header, so nothing here has seen a real beat.
* **Consider packaging the RTL as a proper IP** (`ipx::package_project`)
  rather than a module reference, which is the candidate permanent fix for the
  `attach()` workaround above. Test it against that symptom rather than
  assuming it cures it.
