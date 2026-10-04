#!/usr/bin/env python3
"""What the unplugged squarers do, across Si5351 restarts -- round 41.

    ./pynq-run unplugged.py 20 1,2,11,12    # 20 restarts; those units have sources

An unplugged 10 MHz squarer sits still, chatters, or oscillates at ~0.57 MHz,
and which of those it does changes every time the Si5351 is re-programmed
(round 39).  One look therefore proves nothing about a rework.  This restarts
the Si5351 exactly as bringup.py programs it, waits, and counts every beat
slot's rising edges for a second -- N times -- and reports, per unplugged
unit, how often it was quiet, chattering (< 20 kHz) or oscillating, and at
what frequency.  Run it before and after a change (bridging FB401, the bead
of unit 4's squarer, round 41) and compare the two tables.  It saves every
restart's rates to unplugged_<time>.json beside itself.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    n = int(sys.argv[1])
    plugged = set(int(u) for u in sys.argv[2].split(',')) if len(sys.argv) > 2 else set()
    import driver                                          # noqa: F401
    from driver import attach, F_HELPER, N_BEAT
    from driver.dmtd_constants import REG_CHAN0, CHAN_STRIDE, OFF_COUNT
    from driver.i2c_devices import PynqBus, Si5351, Si5351Config
    from pynq import Overlay
    ol = Overlay(os.path.join(HERE, 'dmtd_top.bit'), download=False)
    core = attach(ol)
    si = Si5351(PynqBus(ol.axi_iic_0))
    cfg = Si5351Config(f_helper=F_HELPER)
    units = [u for u in range(1, N_BEAT + 1) if u not in plugged]

    def counts():
        return [core.read(REG_CHAN0 + (u - 1) * CHAN_STRIDE + OFF_COUNT) for u in units]

    runs = []
    for k in range(n):
        si.program(cfg)
        t0 = time.time()
        while time.time() - t0 < 1.0 and not si.lock_status():
            time.sleep(0.02)
        time.sleep(1.0)
        a = counts()
        ta = time.time()
        time.sleep(1.0)
        b = counts()
        tb = time.time()
        rates = [((y - x) & 0xFFFFFFFF) / (tb - ta) for x, y in zip(a, b)]
        runs.append(rates)
        print('restart %2d: %s' % (k + 1, '  '.join(
            'u%d %s' % (u, 'osc %.0fk' % (r / 1e3) if r > 20e3 else
                        ('chat %d' % r if r > 0 else 'quiet'))
            for u, r in zip(units, rates))), flush=True)
    print('\nunit   quiet  chatter  oscillating   (mean oscillation frequency)')
    for i, u in enumerate(units):
        rs = [r[i] for r in runs]
        osc = [r for r in rs if r > 20e3]
        print('%4d   %5d  %7d  %11d   %s'
              % (u, sum(1 for r in rs if r == 0), sum(1 for r in rs if 0 < r <= 20e3),
                 len(osc), ('%.1f kHz' % (sum(osc) / len(osc) / 1e3)) if osc else '-'))
    fn = os.path.join(HERE, 'unplugged_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    json.dump(dict(units=units, plugged=sorted(plugged), runs=runs,
                   time=time.time()), open(fn, 'w'))
    print('saved %s' % fn)
    return 0


if __name__ == '__main__':
    sys.exit(main())
