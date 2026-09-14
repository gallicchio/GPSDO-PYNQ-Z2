#!/usr/bin/env python3
"""Load the DDMTD overlay on the PYNQ and check it, the PYNQ way."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Import the driver BEFORE constructing the Overlay: pynq registers DefaultIP
# subclasses by VLNV at class-creation time, so a driver imported afterwards
# would not be bound and ol.dmtd_capture_0 would be a bare DefaultIP.
import driver                                          # noqa: F401
from driver import UNIT_NAMES, NULL_CHANNEL, F_HELPER
from pynq import Overlay
from pynq.ps import Clocks

print("=== loading the overlay ===")
ol = Overlay(os.path.join(HERE, 'dmtd_top.bit'))
print("    bitstream :", ol.bitfile_name)
print("    fclk0     : %.6f MHz" % Clocks.fclk0_mhz)
print("    IP in the .hwh:")
for name in sorted(ol.ip_dict):
    d = ol.ip_dict[name]
    addr = d.get('phys_addr')
    print("      %-16s %-42s @ %s" % (
        name, d.get('type', '?'),
        ('0x%08X' % addr) if addr is not None else '(no address)'))

from driver import attach
print("\n=== the driver ===")
print("    ol.dmtd_capture_0        ->", type(ol.dmtd_capture_0).__name__,
      "  (shadowed by an empty hierarchy -- see attach())")
d = attach(ol)
print("    attach(ol)               ->", type(d).__name__)
print("    repr =", repr(d))
assert type(d).__name__ == 'DmtdCapture'
print("    axi_iic driver           ->", type(ol.axi_iic_0).__name__)

print("\n=== selftest ===")
res = d.selftest(settle=0.5)
fails = [r for r in res if not r[1]]
print("\n=== %d checks, %d failures ===" % (len(res), len(fails)))
print("(with nothing plugged in, the helper and every beat MUST fail --")
print(" that is the correct answer, not a broken overlay)")
