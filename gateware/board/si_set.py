#!/usr/bin/env python3
"""Program the Si5351's two drives and leave them so -- round 45 (T2).

    ./pynq-run si_set.py 2 4          # CLK0 (helper) 2 mA, HO 4 mA
    ./pynq-run si_set.py 2 off        # HO off
    ./pynq-run si_set.py standard     # the driver's image for this board

HO is CLK1 on rev A and CLK2 on rev B; the board is read off the chip
(Si5351.board_rev).  The standard image is CLK0 2 mA with HO at 8 mA on
rev A, 2 mA on rev B.

si_watch.py's `matrix` programs a case, measures it and moves on; this leaves
the chip in the case so that another program (beats.py) can record it.  It
prints the lock state and one second of helper slips: check them before
trusting a recording.  Put the standard image back afterwards.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import driver                                            # noqa: F401,E402
from driver import attach                                # noqa: E402
from driver.i2c_devices import PynqBus, Si5351           # noqa: E402
from pynq import Overlay                                 # noqa: E402
import si_watch as W                                     # noqa: E402

args = sys.argv[1:]
if not args or (args != ['standard'] and len(args) != 2):
    print(__doc__)
    sys.exit(2)
ol = Overlay(os.path.join(HERE, 'dmtd_top.bit'), download=False)
core = attach(ol)
si = Si5351(PynqBus(ol.axi_iic_0))
if args == ['standard']:
    W.restore(si)
else:
    c0, c1 = int(args[0]), args[1] if args[1] == 'off' else int(args[1])
    W.program(si, c0, c1)
    print('programmed: CLK0 %d mA, HO (CLK%d) %s'
          % (c0, W.ho_reg(si) - 16, c1 if c1 == 'off' else '%d mA' % c1))
sl = core.helper_slips(1.0)
print('lock %s; helper slips (rate, n, other, span) %s' % (si.lock_status(), sl), flush=True)
