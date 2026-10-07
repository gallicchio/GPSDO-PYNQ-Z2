# Running on the PYNQ

Copy this directory and the overlay onto the board:

```sh
scp build/overlay/dmtd_top.bit build/overlay/dmtd_top.hwh xilinx@<board>:~/gpsdo-dmtd/
scp -r driver gateware/board/* xilinx@<board>:~/gpsdo-dmtd/
ssh xilinx@<board> 'cd ~/gpsdo-dmtd && ./pynq-run run_selftest.py'
```

Three things about PYNQ 3.0 that will otherwise cost an afternoon:

1. **pynq lives in a virtualenv.** `/usr/local/share/pynq-venv/bin/python3`, not
   the system `python3` -- which has neither `pynq` nor `pydantic`, and fails
   with `ModuleNotFoundError: No module named 'pydantic'` that looks like a
   broken install rather than the wrong interpreter.
2. **`XILINX_XRT` is exported by `/etc/profile.d/xrt_setup.sh`**, which `sudo`
   and any non-login shell do not source. Without it pynq's ctypes loader
   leaves its XRT handle as `None` and every overlay load dies with
   `RuntimeError: No Devices Found` -- which names neither XRT nor the
   environment. `pynq-run` sets `XILINX_XRT=/usr` and `BOARD=Pynq-Z2`.
3. **Loading an overlay needs root**, for `/dev/mem`.

`pynq-run` handles all three.

## The one API difference from the documented idiom

Use `attach(ol)`, not `ol.dmtd_capture_0`:

```python
import driver
from driver import attach
from pynq import Overlay

ol = Overlay('dmtd_top.bit')
d  = attach(ol)
d.selftest()
```

The driver binds correctly -- `ol.ip_dict['dmtd_capture_0']['driver']` is
`DmtdCapture` -- but pynq 3.0.1 also invents an empty *hierarchy* with the same
name as the IP, and `_IPMap.__getattr__` checks hierarchies before IP, so the
attribute returns an empty `DocumentedHierarchy`. `attach()` goes through
`ip_dict` instead. See the docstring in `driver/dmtd.py` for what was ruled
out.

## Bench tools (round 30) -- these run on the LAPTOP, not the board

```sh
python3 m2k_beat.py                 # measure the Si5351's beat with an ADALM2000
python3 console_log.py              # log the PYNQ's serial console across resets
```

`m2k_beat.py` talks to the M2k over libiio directly -- neither Scopy nor
libm2k is needed. Run `./pynq-run bringup.py --no-heater --clk2 helper` on the
board first, so CLK2 carries a copy of the helper; then CLK1 and CLK2 are
10.000000 and 10.0012344 MHz and the tool measures the 1234.4 Hz between them
from their phase ramp. Two things it knows that cost an afternoon to find:
the M2k leaves its analog front end powered down until something wakes it, and
subtracting two separately-fitted 10 MHz frequencies throws away the precision
that sampling both channels on one clock buys you.

`console_log.py` reconnects when the port comes back, and says in the log
whether the port going away means Linux crashed (it does not -- the FT2232 is
USB-powered and stays enumerated) or the board lost power (it does).
Which port: `/dev/ttyUSB1` here is the UART, `/dev/ttyUSB0` the JTAG of the
same FT2232, and `/dev/ttyACM0` is the ADALM2000, not the PYNQ.

## The generator and the scope -- these run on the LAPTOP

The bench instruments are driven through **lab-instrument-control**
(QuantumQuasars/lab-instrument-control, checked out at `~/lab-instrument-control`;
set `LAB_INSTRUMENT_CONTROL` if it is elsewhere).  Round 44 moved this
directory's own instrument code there: `siglent.py` became the library's
Siglent drivers, and `scope_log.py` its `siglent/sds_log.py`.  What stays here
is GPSDO-specific.

```sh
python3 xcheck.py steps --scope # output 2's phase in steps: generator vs scope vs DDMTD
python3 xcheck.py ramp 0.05     # output 2 at 10 MHz + 0.05 Hz: scale, linearity, crosstalk
python3 xcheck.py amp --scope   # output 2's amplitude in steps: the squarer's AM-to-PM
python3 ~/lab-instrument-control/siglent/sds_log.py 3600 3 4   # log CH3/CH4 while probing
```

`xcheck.py` keeps the board's own limits on top of the library's drivers.

- The generator's open-circuit swing stays at or below 3.3 Vpp, the rating of
  an input without its 50R jumper (the driver's `vlimit`, 1.65 V peak).
- Only a running sine's frequency (within 0.1 % of 10 MHz), amplitude and
  phase are changed. Never its LOAD, waveform or on/off state.
- Both outputs go back exactly as found, and the scope is left running or
  stopped as found.

It records units 1 and 2 on the PYNQ while it changes an output at logged
moments.  `beats.py` recordings carry a wall-clock anchor, so those moments can
be found in the data.  The bench wiring is in `BENCH_WIRING.md`.

## Beats by their timestamps (round 39) -- `beats.py`, both ends

```sh
./pynq-run beats.py record 20 1 2 11      # on the PYNQ: units as on the silkscreen
python3 beats.py analyse beats_1_2_11_<time>.npz   # on the laptop, numpy only
```

Round 42: each recording's name carries its units and the time it was made,
so an "after" recording no longer overwrites the "before" one.

The core does not deglitch yet, so a real beat's edges chatter (2-6 rising
edges per transition on the first board) and an unplugged squarer can chatter
at a similar rate: the edge COUNT cannot tell a beat from nothing.
`beats.py` records every change of each slot's count with its timestamp,
folds each unit at its own beat period, and calls it a beat only if its
transitions sit in two narrow clusters one second at a time.  It prints the
beat and input frequencies (in PS-clock units, like the helper), the chatter,
the per-edge scatter, and for units on the same source their difference edge
by edge -- handbook steps 5 and 6.

`bringup.py --inputs 13` (units, as on the silkscreen) says which channels
should carry a source.  An unplugged channel is described, not failed: it may
be quiet, chatter, or oscillate at ~0.57 MHz.

## Both Si5351 PLLs, watched (round 40) -- `si_watch.py`

```sh
./pynq-run si_watch.py watch 600 12   # 10 min; HO cabled into unit 12 (50R jumper in)
./pynq-run si_watch.py watch 3600 12 --clk0 4   # 1 h with the helper at 4 mA
./pynq-run si_watch.py matrix 8 2     # CLK0 x CLK1 drive strengths, fresh start each
```

PLLA's slips come from the pair register (helper vs PS clock, 40 ns steps).
HO's beat against the helper has an exact period, because both come from one
TCXO, so any jump in it is a slip of one PLL or the other; a jump without a
PLLA slip is PLLB's.  The Si5351's own sticky LOL bits are cleared before and
read after -- round 40 never saw them set, even at 2000 slips a second.
Round 41: `watch` stamps each 60 s chunk in UTC and reports (and clears)
any latched LOL/LOS flag as it happens, for runs of hours or days.
`unplugged.py N units` records what the unplugged squarers do across N
Si5351 restarts -- the before/after for a rework such as bridging FB401.
Round 40's answer: helper (CLK0) at 2 mA is clean with HO at any drive;
the driver uses that.  Round 42: `watch --clk0/--clk1` programs those drives
first and puts the standard image back at the end, for a margin test after
a rework.  Each 60 s chunk takes ~77 s, because the analysis runs between
chunks, so the log covers about 78 % of the wall-clock time.

## Before and after a rework (round 42) -- `bench.sh`

```sh
./bench.sh before    # the board as it is, just before a rework
./bench.sh fb401     # after bridging FB401
./bench.sh xa        # after R3001 -> 1k, R3002 -> 330R
```

It runs the same battery each time, so any two runs compare like with like:
`bringup.py`, `unplugged.py 30`, 30 s recordings of units 1, 2, 11 and 12, and
the drive matrix.  About 10 minutes.  Everything goes to `logs/<stage>_<UTC time>/`
with a `summary.txt`.  It refuses to start while another board script is
running (`sudo pkill -f 'si_watch.py watch'` stops an overnight watch).

Rev A had no jack on unit 4, so round 42's step of moving a cable there is
gone.  With the SMA you are fitting, the 33220A drives unit 4 and the laptop
switches it.  Run `bench.sh` with it off (`bench_setup.py unit4 off`), so
that unit 4 counts as unplugged (round 44).

## The bench, wired to stay (round 44) -- `BENCH_WIRING.md`, `bench_setup.py`

`BENCH_WIRING.md` says what connects to what, cable by cable: two solder jobs
(unit 4's SMA, one 1-Wire terminal), the sources, the scope and two
CircuitGears on the rails.  Its
`bench_wiring.csv` is the copy the experiments read.  `bench_setup.py` (on the
laptop) puts the sources into the bench's state, or out of it:

```sh
python3 bench_setup.py status       # read-only
python3 bench_setup.py on           # 10 MHz sines, 3.3 Vpp open circuit, everywhere
python3 bench_setup.py unit4 off    # the 33220A's output off: unit 4 undriven
python3 bench_setup.py off
```

## Overnight (round 45) -- `overnight.py` on the LAPTOP, `temps.py` on the board

```sh
python3 overnight.py 14             # one row per 90 s for 14 hours
python3 overnight.py 2 --period 60  # a shorter, denser run
./pynq-run temps.py                 # on the PYNQ: the 8 thermometers and the probe, once
```

`overnight.py` is BENCH_WIRING.md's G7. Each row, in `overnight_<UTC time>/log.csv`,
holds:

- the board's temperatures;
- 20 s of beats on units 1, 2, 4, 11 and 12: each unit's fold concentration,
  unit 2 − unit 1 and unit 11 − unit 1 as phase (modulo 100 ns, so the rows
  join into one trace), and units 4 and 12 as frequency;
- 10 s of `si_watch.py watch`;
- the three rails on the CircuitGears;
- the scope's amplitudes on CH1-CH4.

It changes no setting. Each step's failure is logged in the row and the run
goes on. Over password SSH, set `PYNQ_SSH` and `PYNQ_SCP` as for `xcheck.py`.
