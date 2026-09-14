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
