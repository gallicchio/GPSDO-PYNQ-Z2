#!/usr/bin/env python3
"""The board heater, on or off -- round 45 (T4).

    ./pynq-run heater.py status      # the DAC's register and EEPROM, read only
    ./pynq-run heater.py safe        # EEPROM 0 with 1k power-down, and off now
    ./pynq-run heater.py on          # all three banks fully on (~9.6 W from the 15 V jack)
    ./pynq-run heater.py off

Through the driver's Heater class, which drives the FETs only fully on or
fully off.  `safe` is what bringup.py does first: the MCP4725 ships at
mid-scale, which would be 1.65 V on three FET gates the moment 15 V arrived.
Prints one line, for overnight.py to parse.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import driver                                            # noqa: F401,E402
from driver.i2c_devices import PynqBus, MCP4725, Heater  # noqa: E402
from pynq import Overlay                                 # noqa: E402

cmd = sys.argv[1] if len(sys.argv) > 1 else ''
if cmd not in ('status', 'safe', 'on', 'off'):
    print(__doc__)
    sys.exit(2)
ol = Overlay(os.path.join(HERE, 'dmtd_top.bit'), download=False)
dac = MCP4725(PynqBus(ol.axi_iic_0))
h = Heater(dac)
if cmd == 'safe':
    h.make_safe()
elif cmd == 'on':
    h.on()
elif cmd == 'off':
    h.off()
rb = dac.read()
print('HEATER %s: %s' % (cmd, ' '.join('%s=%s' % kv for kv in sorted(rb.items()))), flush=True)
