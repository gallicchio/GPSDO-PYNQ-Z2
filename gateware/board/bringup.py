#!/usr/bin/env python3
"""First power-up of a front-end board, in the only safe order.

    ./pynq-run bringup.py              # everything below
    ./pynq-run bringup.py --scan       # just list who answers on the bus
    ./pynq-run bringup.py --no-si5351  # skip programming the synthesiser
    ./pynq-run bringup.py --no-heater --inputs 13   # HO cabled into unit 13
    ./pynq-run bringup.py --rev B      # name the board instead of detecting it

Order, and why it is the order:

  1. load the overlay and scan the I2C bus -- who is actually there
  2. HEATER DAC FIRST: write its EEPROM to 0 with the 1 k power-down.  The
     part ships at mid-scale (datasheet Table 5-3), which is 1.65 V on three
     FET gates.  Until this has run once on a board, the 15 V jack stays out.
  3. program the Si5351: helper on CLK0 (PLLA, fractional), null / HO from
     PLLB (integer) -- on CLK1 on rev A, CLK2 on rev B; read the image back;
     wait for both PLLs to lock
  4. read the eight thermometers
  5. enumerate the DS18B20 probes through the DS2482
  6. run the measurement core's selftest, which now has a helper to count

With NO board on the header (which is how round 28 tested this), every
device is absent: the scan is empty, steps 2-5 report 'absent' and step 6
reports a dead helper.  That is a pass for the software path, not for the
board.

--rev is the board: rev A drives its Si5351A's XA, rev B its Si5351C's
CLKIN, and an image for the wrong one never locks.  'auto' (the default)
asks the chip which input has a reference (Si5351.rev_of) and stops if
neither does -- the TCXO, test point X.

--inputs names the units (1..13, as printed beside the SMAs) that have a
10 MHz source plugged in; those must show a beat.  The default is none,
which is the board at handbook step 3: every unplugged channel is then
measured and described -- quiet, or its squarer oscillating by itself at
~0.57 MHz (round 39) -- but not counted as a failure.
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
    read_all_thermometers, MCP4725, Heater, DS2482, DS18B20, IDRV_HELPER, IDRV_NULL,
    IDRV_HO_REVB,
)


def hdr(s):
    print('\n=== %s ===' % s)


def parse_units(text):
    """'none' | 'all' | '1,2,13' (unit numbers as on the silkscreen) ->
    the set of beat CHANNELS (unit - 1) that should carry a beat."""
    text = text.strip().lower()
    if text == 'none':
        return set()
    if text == 'all':
        return set(range(len(UNIT_NAMES)))
    units = set(int(u) for u in text.split(',') if u.strip())
    bad = sorted(u for u in units if not 1 <= u <= len(UNIT_NAMES))
    if bad:
        raise argparse.ArgumentTypeError('no unit %s: units are 1..%d'
                                         % (bad, len(UNIT_NAMES)))
    return set(u - 1 for u in units)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scan', action='store_true', help='scan the bus and stop')
    ap.add_argument('--no-si5351', action='store_true')
    ap.add_argument('--clk2', default='off', choices=('off', 'helper', 'null'),
                    help="rev A and a bare Si5351 only: what to put on the "
                         "third output.  'off' is what the rev A board wants -- "
                         "CLK2 has no track on it.  'helper' puts a second copy "
                         "of CLK0 there, so a scope or an ADALM2000 on CLK1 and "
                         "CLK2 sees the 1234.4 Hz beat this instrument is built "
                         "on.  Rev B drives HO from CLK2 and refuses anything "
                         "but 'off'")
    ap.add_argument('--rev', default='auto', choices=('auto', 'A', 'B'),
                    help="which board: 'auto' (the default) reads it off the "
                         "Si5351's LOS flags -- rev A's reference is on XA, "
                         "rev B's on CLKIN")
    ap.add_argument('--no-heater', action='store_true',
                    help='do not touch the DAC (only if it has been made safe before)')
    ap.add_argument('--inputs', type=parse_units, default=set(),
                    help="units with a 10 MHz source plugged in, as printed "
                         "beside the SMAs: 'none' (the default), 'all', or a "
                         "list such as 13 or 1,2,13.  Those must show a beat")
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

    hdr('Si5351')
    chip = None
    if a.no_si5351:
        print('    skipped by --no-si5351')
    elif Si5351.ADDR not in found:
        print('    absent')
    else:
        chip = Si5351(bus, rev=None if a.rev == 'auto' else a.rev)
        chip.wait_ready()
        st0 = chip.status
        print('    status before:', st0)
        seen = Si5351.rev_of(st0)
        print('    reference seen on: %s'
              % {'A': 'XA (rev A: an Si5351A)', 'B': 'CLKIN (rev B: an Si5351C, the TCXO)',
                 None: 'NEITHER input -- no TCXO?  Check test point X'}[seen])
        try:
            rev = chip.board_rev()
        except RuntimeError as e:
            print('    %s' % e)
            print('    not programmed.')
            return 1
        if seen and seen != rev:
            print('    WARNING: --rev %s, but the chip sees its reference where '
                  'rev %s has it' % (rev, seen))
        if rev == 'B' and a.clk2 != 'off':
            print('    --clk2 %s is for a bare Si5351 (handbook section 2): rev B '
                  'drives HO from CLK2.  Not programmed.' % a.clk2)
            return 2
        cfg = Si5351Config(f_helper=F_HELPER, clk2=a.clk2, rev=rev)
        ho = 'CLK2' if rev == 'B' else 'CLK1'
        print('    rev %s: helper on CLK0, null (HO) on %s%s'
              % (rev, ho, '' if rev == 'B' else ', CLK2 %s' % a.clk2))
        f0, f1 = cfg.expected()
        print('    PLLA %d + %d/%d -> VCO %.3f MHz -> CLK0 %.4f Hz'
              % (cfg.a, cfg.b, cfg.c, cfg.f_vco_a / 1e6, f0))
        print('    PLLB %d          -> VCO %.3f MHz -> %s %.4f Hz'
              % (cfg.mult_b, cfg.f_vco_b / 1e6, ho, f1))
        f2 = cfg.expected_clk2()
        if rev == 'A':
            print('    CLK2 %s' % ('off (not routed on the rev A board)'
                                   if f2 is None else
                                   '%.4f Hz  -- %s, a bench witness; CLK1 and CLK2 '
                                   'are then %.1f Hz apart'
                                   % (f2, a.clk2, abs(f2 - f1))))
        print('    drive: CLK0 (helper) %d mA, %s (HO) %d mA%s'
              % (2 * (IDRV_HELPER + 1), ho,
                 2 * ((IDRV_HO_REVB if rev == 'B' else IDRV_NULL) + 1),
                 ', CLK1 off' if rev == 'B' else ''))
        chip.program(cfg)
        bad = chip.verify(cfg)
        print('    readback: %s' % ('all %d registers agree' % len(cfg.registers())
                                    if not bad else 'MISMATCH %s' % bad))
        t0 = time.time()
        while time.time() - t0 < 1.0 and not chip.lock_status():
            time.sleep(0.02)
        print('    status after :', chip.status,
              'LOCKED' if chip.lock_status() else 'NOT LOCKED')
        # ROUND 39.  "Locked" is not enough: with CLK0 at 8 mA the first board's
        # PLLA cycle-slipped ~650 times a second while LOL stayed clear, and
        # whether a start comes up slipping is a matter of state.  Count the
        # 40 ns steps on the core's pair register, and start again if needed.
        for attempt in range(4):
            time.sleep(0.3)
            sl = core.helper_slips(1.0)
            if sl is None:
                print('    helper slips: not measurable (no helper at the core, '
                      'or gateware before 1.1)')
                break
            rate, n, other, span = sl
            print('    helper slips: %d reference-cycle steps, %d other, in %.1f s  -> %s'
                  % (n, other, span, 'clean' if rate < 2.0 else 'SLIPPING'))
            if rate < 2.0 or attempt == 3:
                break
            print('    re-programming the Si5351 (attempt %d)' % (attempt + 2))
            chip.program(cfg)
        # Round 41: start the latched status flags from zero now that the chip
        # is programmed and clean, and report them at the end of the run.
        chip.clear_sticky()

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
        # One 1-Wire reset, and the bridge's own verdict on the bus.  With no
        # probe on any terminal the right answer is: no presence pulse, NO
        # SHORT, and the line idling HIGH -- which checks the pull-up and the
        # five terminals' wiring before a probe is ever fitted.
        pp = br.ow_reset()
        st = br.status()
        print('    bus: presence %s, short %s, line %s'
              % ('yes' if pp else 'no',
                 'YES -- a short on the 1-Wire bus' if st & DS2482.ST_SD else 'no',
                 'high' if st & DS2482.ST_LL else 'LOW -- held down'))
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
    # Is there a front-end board on the header at all?  The squarers and the
    # flip-flops that make a beat are on it, so with it absent the thirteen
    # beat checks cannot pass and reporting them as failures buries whatever
    # else went wrong.  The board's own I2C parts are the evidence: a bare
    # PYNQ with a Si5351 wired to five pins has none of them.
    front_end = bool(set(found) - {Si5351.ADDR})
    if not front_end:
        print('    no front-end board on the bus (%s), so the beat and pps '
              'checks are reported as not testable rather than failed'
              % ('nothing but the Si5351 answered' if found else 'nothing answered'))
    if front_end:
        print('    sources expected on: %s'
              % (', '.join('unit %d' % (n + 1) for n in sorted(a.inputs))
                 or 'no unit (--inputs none): unplugged channels are '
                    'described, not failed'))
    res = core.selftest(settle=1.0, front_end=front_end, inputs=a.inputs)
    fails = core.failures(res)
    hz = core.helper_hz
    if hz:
        print('    helper %.1f Hz measured against the PS clock (that clock is '
              '+/-50 ppm, so +/-500 Hz: use a pps to measure it properly)' % hz)
    if chip is not None:
        # the reference flag that matters is the one this board's PLLs use:
        # rev B's LOS_XTAL is always latched, because XA/XB float there
        st = chip.sticky()
        los = 'LOS_CLKIN' if chip.rev == 'B' else 'LOS_XTAL'
        lost = chip.ref_lost(st)
        print('    Si5351 latched flags since programming: LOL_A %d, LOL_B %d, '
              '%s %d%s' % (st['lol_a'], st['lol_b'], los, lost,
                           '' if not (st['lol_a'] or st['lol_b'] or lost)
                           else '  <-- the chip lost lock during this run'))
    print('\n%d checks, %d failures' % (len(res), len(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
