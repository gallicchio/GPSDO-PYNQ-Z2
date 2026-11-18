#!/usr/bin/env python3
"""Does a squarer changing state move its neighbours?  Round 45 (rev B items 5,
8, 11, 12).  Runs on the LAPTOP.

    python3 toggle_test.py CYCLES             # unit 4's source on/off (T1)
    python3 toggle_test.py heater CYCLES      # the board heater on/off instead

With `heater`, the same recordings ask whether the heater -- 0.64 A from
whatever supply is in the 15 V jack -- adds noise: each row also carries the
board temperatures and both rails, and the heater is left off at the end.

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


def cg2_v3d():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with O.CircuitGear(serial_number=O.CG2) as cg:
            sc = cg.scope
            sc.auto_zero('A', ranges=('high',))
            sc.set_range('A', 'high')
            sc.set_coupling('A', 'DC')
            caps = [sc.capture(force=True) for _ in range(8)]
            return float(np.concatenate([c.a for c in caps]).mean()) * 1.0178


def main():
    args = sys.argv[1:]
    what = 'heater' if args and args[0] == 'heater' else 'unit4'
    if args and args[0] == 'heater':
        args = args[1:]
    cycles = int(args[0]) if args else 8
    out = os.path.join(HERE, 'toggle_%s%s' % ('heater_' if what == 'heater' else '',
                                              time.strftime('%Y%m%dT%H%MZ', time.gmtime())))
    os.makedirs(out)
    keep_dir = out
    fields = ['utc', what, 'p2_1_ps', 'p2_1_rms_ps', 'p11_1_ps', 'p11_1_rms_ps', 'u4_top',
              'u4_ept', 'u2_ept', 'u1_ept', 'u11_ept', 'u12_ept', 'v3a', 'v3d', 'T48', 'T49',
              'T4E', 'probe', 'errors']
    g = Agilent33220A() if what == 'unit4' else None
    was_on = g.wave()['output'] if g else None

    def switch(state):
        if g:
            g.output(on=(state == 'on'))
        else:
            O.heater(state)
    with open(os.path.join(out, 'toggle.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        try:
            for i in range(cycles):
                for state in ('on', 'off'):
                    switch(state)
                    time.sleep(3.0)
                    row = {'utc': time.strftime('%H:%M:%SZ', time.gmtime()), what: state}
                    errs = []
                    try:
                        O.beats(row, keep_dir, keep=False)
                    except Exception as e:
                        errs.append('beats: %s' % e)
                    try:
                        row['v3a'] = round(cg1_v3a(), 5)
                        if what == 'heater':
                            row['v3d'] = round(cg2_v3d(), 5)
                    except Exception as e:
                        errs.append('cg: %s' % e)
                    if what == 'heater':
                        try:
                            O.temps(row)
                        except Exception as e:
                            errs.append('temps: %s' % e)
                    row['errors'] = ' | '.join(errs)
                    w.writerow({k: row.get(k) for k in fields})
                    f.flush()
                    print('%s %s %-3s  u2-u1 %8s ps (rms %5s)  u11-u1 %10s ps  ept %s/%s  '
                          '+3V3_A %s +3V3_D %s  T48 %s T4E %s  %s'
                          % (row['utc'], what, state, row.get('p2_1_ps'), row.get('p2_1_rms_ps'),
                             row.get('p11_1_ps'), row.get('u1_ept'), row.get('u2_ept'),
                             row.get('v3a'), row.get('v3d'), row.get('T48'), row.get('T4E'),
                             row['errors'] or ''), flush=True)
        finally:
            if g:
                g.output(on=was_on)
                print('33220A output put back %s' % ('on' if was_on else 'off'))
                g.close()
            else:
                O.heater('off')
                print('heater off')
    print(out)


if __name__ == '__main__':
    main()
