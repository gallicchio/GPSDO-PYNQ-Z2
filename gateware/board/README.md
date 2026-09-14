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
