#!/usr/bin/env python3
"""First power-up of a front-end board, in the only safe order.

    ./pynq-run bringup.py              # everything below
    ./pynq-run bringup.py --scan       # just list who answers on the bus
    ./pynq-run bringup.py --no-si5351  # skip programming the synthesiser

Order, and why it is the order:

  1. load the overlay and scan the I2C bus -- who is actually there
  2. HEATER DAC FIRST: write its EEPROM to 0 with the 1 k power-down.  The
     part ships at mid-scale (datasheet Table 5-3), which is 1.65 V on three
     FET gates.  Until this has run once on a board, the 15 V jack stays out.
  3. program the Si5351: helper on CLK0 (PLLA, fractional), null on CLK1
     (PLLB, integer); read the image back; wait for both PLLs to lock
  4. read the eight thermometers
  5. enumerate the DS18B20 probes through the DS2482
  6. run the measurement core's selftest, which now has a helper to count

With NO board on the header (which is how round 28 tested this), every
device is absent: the scan is empty, steps 2-5 report 'absent' and step 6
reports a dead helper.  That is a pass for the software path, not for the
board.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import driver                                          # noqa: E402,F401
from driver import attach, F_HELPER, F_BEAT, UNIT_NAMES  # noqa: E402
from driver.i2c_devices import (                       # noqa: E402
    PynqBus, scan, EXPECTED_DEVICES, Si5351, Si5351Config, TMP1075,
    read_all_thermometers, MCP4725, Heater, DS2482, DS18B20,
)


def hdr(s):
    print('\n=== %s ===' % s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scan', action='store_true', help='scan the bus and stop')
    ap.add_argument('--no-si5351', action='store_true')
    ap.add_argument('--no-heater', action='store_true',
                    help='do not touch the DAC (only if it has been made safe before)')
    ap.add_argument('--bit', default=os.path.join(HERE, 'dmtd_top.bit'))
    a = ap.parse_args()

    hdr('overlay')
    from pynq import Overlay
    ol = Overlay(a.bit)
    core = attach(ol)
    bus = PynqBus(ol.axi_iic_0)
    print('    bitstream :', ol.bitfile_name)
    print('    core      :', repr(core))

    hdr('I2C bus scan')
    found = scan(bus)
    for addr in sorted(set(found) | set(EXPECTED_DEVICES)):
        tag = EXPECTED_DEVICES.get(addr, '?? not on the schematic')
        print('    0x%02X  %-8s %s' % (addr, 'ACK' if addr in found else 'absent', tag))
    missing = sorted(set(EXPECTED_DEVICES) - set(found))
    if not found:
        print('    nothing answers: no front-end board on the header, or no 3.3 V on it')
    elif missing:
        print('    MISSING: %s' % ', '.join('0x%02X' % m for m in missing))
    if a.scan:
        return 0

    hdr('heater DAC: make safe (EEPROM := 0, PD = 1k)')
    if a.no_heater:
        print('    skipped by --no-heater')
    elif MCP4725.ADDR not in found:
        print('    absent')
    else:
        rb = Heater(MCP4725(bus)).make_safe()
        print('    EEPROM code %d pd %d; DAC code %d pd %d  -> %s'
              % (rb['eeprom_code'], rb['eeprom_pd'], rb['code'], rb['pd'],
                 'SAFE' if rb['eeprom_code'] == 0 and rb['eeprom_pd'] == 1 else 'NOT SAFE'))

    hdr('Si5351: helper on CLK0, null on CLK1')
    if a.no_si5351:
        print('    skipped by --no-si5351')
    elif Si5351.ADDR not in found:
        print('    absent')
    else:
        chip = Si5351(bus)
        print('    status before:', chip.status)
        chip.wait_ready()
        cfg = Si5351Config(f_helper=F_HELPER)
        f0, f1 = cfg.expected()
        print('    PLLA %d + %d/%d -> VCO %.3f MHz -> CLK0 %.4f Hz'
              % (cfg.a, cfg.b, cfg.c, cfg.f_vco_a / 1e6, f0))
        print('    PLLB %d          -> VCO %.3f MHz -> CLK1 %.4f Hz'
              % (cfg.mult_b, cfg.f_vco_b / 1e6, f1))
        chip.program(cfg)
        bad = chip.verify(cfg)
        print('    readback: %s' % ('all %d registers agree' % len(cfg.registers())
                                    if not bad else 'MISMATCH %s' % bad))
        t0 = time.time()
        while time.time() - t0 < 1.0 and not chip.lock_status():
            time.sleep(0.02)
        print('    status after :', chip.status,
              'LOCKED' if chip.lock_status() else 'NOT LOCKED')

    hdr('board thermometers')
    for addr, t in read_all_thermometers(bus):
        print('    0x%02X  %s' % (addr, 'absent' if t is None else '%.4f C' % t))

    hdr('1-Wire probes')
    if DS2482.ADDR not in found:
        print('    bridge absent')
    else:
        br = DS2482(bus)
        br.reset()
        br.write_config(apu=True)
        probes = DS18B20(br)
        roms = probes.search()
        print('    %d probe(s)' % len(roms))
        if roms:
            probes.convert_all()
            for rom in roms:
                try:
                    print('    %016X  %.4f C' % (rom, probes.read_c(rom)))
                except Exception as e:
                    print('    %016X  read failed: %s' % (rom, e))

    hdr('measurement core selftest')
    res = core.selftest(settle=1.0)
    fails = [r for r in res if not r[1]]
    hz = core.helper_hz
    if hz:
        print('    helper %.1f Hz measured against the PS clock (that clock is '
              '+/-50 ppm, so +/-500 Hz: use a pps to measure it properly)' % hz)
    print('\n%d checks, %d failures' % (len(res), len(fails)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
