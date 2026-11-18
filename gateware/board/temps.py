#!/usr/bin/env python3
"""The board's eight thermometers and the 1-Wire probes, read once -- round 45.

    ./pynq-run temps.py

Prints one line, for overnight.py on the laptop to parse:

    T 0x48=24.4375 0x49=... 0x4F=... | PROBE 65000000CA223A28=23.8125

Attaches to the overlay already loaded and changes nothing on the board: the
TMP1075s are only read, and the DS2482 bridge is reset and searched exactly as
bringup.py does.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import driver                                            # noqa: F401,E402
from driver.i2c_devices import (PynqBus, read_all_thermometers, DS2482,  # noqa: E402
                                DS18B20)
from pynq import Overlay                                 # noqa: E402

ol = Overlay(os.path.join(HERE, 'dmtd_top.bit'), download=False)
bus = PynqBus(ol.axi_iic_0)
parts = ['T'] + ['0x%02X=%s' % (a, 'NA' if t is None else '%.4f' % t)
                 for a, t in read_all_thermometers(bus)]
parts.append('| PROBE')
try:
    br = DS2482(bus)
    br.reset()
    br.write_config(apu=True)
    probes = DS18B20(br)
    roms = probes.search()
    if roms:
        probes.convert_all()
    for rom in roms:
        try:
            parts.append('%016X=%.4f' % (rom, probes.read_c(rom)))
        except Exception:
            parts.append('%016X=NA' % rom)
except Exception as e:                       # the bridge or the bus misbehaving
    parts.append('ERROR=%s' % str(e).replace(' ', '_')[:60])
print(' '.join(parts), flush=True)
