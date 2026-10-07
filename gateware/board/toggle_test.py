#!/usr/bin/env python3
"""Does a squarer changing state move its neighbours?  Round 45 (rev B items 5,
8, 11, 12).  Runs on the LAPTOP.

    python3 toggle_test.py CYCLES

Unit 4's source (the 33220A) is switched on and off, a 20 s recording of units
1, 2, 4, 11 and 12 is taken in each state, and each recording's mean of
unit 2 - unit 1 and unit 11 - unit 1 is written with CG-1's reading of +3V3_A
(J5001 pin 5, zeroed).  Off, unit 4's squarer oscillates (~560 kHz, round 45's
battery); on, it squares the 33220A's 10 MHz.  Unit 2 is unit 4's neighbour on
the right-hand edge; unit 1 is across the board.  Consecutive on/off pairs
cancel the slow drift (4-5 ps/K, round 45.12).  The 33220A is left as found.
Output: toggle_<UTC>/toggle.csv beside this file.
"""
import csv
import os
import sys
import time
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import overnight as O                                          # noqa: E402
sys.path.insert(0, os.path.join(O.LIC, 'hp'))
from agilent_33220A import Agilent33220A                       # noqa: E402


def cg1_v3a():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with O.CircuitGear(serial_number=O.CG1, calibration_file=O.CG1_CAL) as cg:
            sc = cg.scope
            sc.auto_zero('B', ranges=('high',))
            sc.set_range('B', 'high')
            sc.set_coupling('B', 'DC')
            caps = [sc.capture(force=True) for _ in range(8)]
            return float(np.concatenate([c.b for c in caps]).mean()) * 1.0218


def main():
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    out = os.path.join(HERE, 'toggle_%s' % time.strftime('%Y%m%dT%H%MZ', time.gmtime()))
    os.makedirs(out)
    keep_dir = out
    fields = ['utc', 'unit4', 'p2_1_ps', 'p2_1_rms_ps', 'p11_1_ps', 'u4_top', 'u4_ept',
              'u2_ept', 'u1_ept', 'v3a', 'errors']
    with Agilent33220A() as g, open(os.path.join(out, 'toggle.csv'), 'w', newline='') as f:
        was_on = g.wave()['output']
        w = csv.DictWriter(f, fields)
        w.writeheader()
        try:
            for i in range(cycles):
                for state in ('on', 'off'):
                    g.output(on=(state == 'on'))
                    time.sleep(3.0)
                    row = {'utc': time.strftime('%H:%M:%SZ', time.gmtime()), 'unit4': state}
                    errs = []
                    try:
                        O.beats(row, keep_dir, keep=False)
                    except Exception as e:
                        errs.append('beats: %s' % e)
                    try:
                        row['v3a'] = round(cg1_v3a(), 5)
                    except Exception as e:
                        errs.append('cg: %s' % e)
                    row['errors'] = ' | '.join(errs)
                    w.writerow({k: row.get(k) for k in fields})
                    f.flush()
                    print('%s unit 4 %-3s  u2-u1 %8s ps  u11-u1 %10s ps  u4 top %5s ept %6s  +3V3_A %s  %s'
                          % (row['utc'], state, row.get('p2_1_ps'), row.get('p11_1_ps'),
                             row.get('u4_top'), row.get('u4_ept'), row.get('v3a'),
                             row['errors'] or ''), flush=True)
        finally:
            g.output(on=was_on)
            print('33220A output put back %s' % ('on' if was_on else 'off'))
    print(out)


if __name__ == '__main__':
    main()
