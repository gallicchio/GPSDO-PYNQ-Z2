#!/usr/bin/env python3
"""G7, the overnight log -- round 45.  Runs on the LAPTOP.

    python3 overnight.py HOURS [--period SECONDS]      # default one row per 90 s
    python3 overnight.py 13 --period 120 --heater 0:off,60:on,240:off,420:on,600:off

One row per period into overnight_<UTC time>/log.csv beside this file:

  * the board's eight thermometers and the 1-Wire probe (temps.py on the PYNQ);
  * 20 s of beats on units 1, 2, 4, 11 and 12 (beats.py on the PYNQ, analysed
    here, the file then deleted there):
      - each unit's fold concentration (`top`, 45.4) and beat frequency;
      - unit 2 - unit 1 and unit 11 - unit 1 as phase: the mean over the 20 s,
        modulo 100 ns, so successive rows join into a night-long trace for
        units that share the SDG's clock;
      - unit 4 and unit 12 against unit 1 as a frequency, in ppb;
  * 10 s of `si_watch.py watch` on unit 12: PLLA slips and HO-beat jumps;
  * the rails on the CircuitGears: +5V_HDR and +3V3_A (CG-1 A and B), +3V3_D
    (CG-2 A, zeroed once at the start);
  * the scope's PKPK and MEAN on CH1-CH4.

Every hour that period's beats file is kept too, as beats_<time>.npz.

--heater MIN:STATE,...  switches the board heater (heater.py on the PYNQ: all
three banks, ~9.6 W from the 15 V jack) at those minutes after the start,
between rows, so its I2C writes never overlap temps.py's reads.  The state is
logged in the `heater` column, and the heater is turned OFF when the run ends,
however it ends.  Safety: if any thermometer (or the probe) reads above
HEATER_MAX_C, the heater is switched off and stays off for the rest of the run
(`heater` = 'cutoff').  A row whose temperatures cannot be read turns it off
too, until a later row can read them.

Round 45's first analysis changed four things (the first 5.4 h were logged
without them):

  * pairs are computed even when a unit fails beats.py's 60 % `top` test.
    That test is made in 0.1 s windows and fails during the source's own
    short-term wander; such rows have perfectly good pairs (unit 2 - unit 1
    at 32.7 ps rms in one);
  * each unit's chatter is logged directly: rising edges per transition;
  * both CircuitGears are zeroed (auto_zero, high range) before every
    reading.  CG-1's zero drifted ~30 mV as the room cooled 2 K;
  * the helper's frequency against the PYNQ's PS clock, from si_watch.

Changes nothing on the board or the generators.  The CircuitGears are opened
with their reset, which leaves both generators off, as they should be
overnight (BENCH_WIRING.md E2).  Each step has its own timeout, and a failure
is written to the row's `errors` column, so a hung PYNQ or an unplugged
instrument costs rows, not the night.  Stop it with Ctrl-C or
`pkill -f overnight.py`.

The PYNQ is reached as xcheck.py reaches it: $PYNQ_SSH, $PYNQ_SCP, $PYNQ_HOST,
$PYNQ_DIR.
"""
import contextlib
import csv
import io
import os
import re
import shlex
import subprocess
import sys
import time
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import beats as B                                              # noqa: E402
import xcheck as X                                             # noqa: E402

LIC = X.LIC
sys.path.insert(0, os.path.join(LIC, 'syscomp_circuit_gear'))
from siglent_SDS2104X import SDS2104X                          # noqa: E402
from syscomp_circuit_gear import CircuitGear                   # noqa: E402

PYNQ = os.environ.get('PYNQ_HOST', 'xilinx@192.168.8.156')
SSH = shlex.split(os.environ.get('PYNQ_SSH', 'ssh ' + PYNQ))
SCP = shlex.split(os.environ.get('PYNQ_SCP', 'scp'))
RDIR = os.environ.get('PYNQ_DIR', 'gpsdo-dmtd')
SHM = '/dev/shm/gpsdo-overnight'      # the beats files' scratch on the PYNQ
UNITS = (1, 2, 4, 11, 12)
HEATER_MAX_C = 50.0             # round 45: the heater warms the board ~2 K a minute
SAME_CLOCK = (2, 11)            # phase against unit 1, modulo 100 ns
OTHER_CLOCK = (4, 12)           # frequency against unit 1
CG1, CG2 = 'C2BRGBL', 'C2BKO1A'
CG1_CAL = os.path.join(LIC, 'syscomp_circuit_gear', 'results', CG1, 'calibration.json')
THERMS = ['0x%02X' % a for a in range(0x48, 0x50)]


def pynq(cmd, timeout):
    r = subprocess.run(SSH + ['cd %s && %s' % (RDIR, cmd)], capture_output=True,
                       text=True, timeout=timeout)
    return r.stdout + r.stderr


def temps(row):
    out = pynq('./pynq-run temps.py', 60)
    m = re.search(r'T (0x48=.*)', out)
    if not m:
        raise IOError('temps.py: ' + out.strip()[-80:])
    for tok in m.group(1).split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            key = 'T' + k[2:] if k.startswith('0x') else 'probe'
            row[key] = None if v == 'NA' else float(v)


def beats(row, out_dir, keep):
    # In RAM, not on the PYNQ's SD card: ~5 MB a row is ~2 GB a night, and
    # round 43's hang was that card.  A directory of our own, because /dev/shm
    # is sticky and the file is root's (sudo) while the rm below is not.
    out = pynq("mkdir -p %s && cd %s && ~/%s/pynq-run ~/%s/beats.py record 20 %s 2>&1 "
               "| grep -o '/[^ ]*[.]npz'" % (SHM, SHM, RDIR, RDIR, ' '.join(map(str, UNITS))), 120)
    path = out.strip().splitlines()[-1] if out.strip() else ''
    if not path.endswith('.npz'):
        raise IOError('beats.py: no file (%r)' % out.strip()[-80:])
    local = os.path.join(out_dir, 'beats_%s.npz' % time.strftime('%H%M%S', time.gmtime()))
    subprocess.run(SCP + ['%s:%s' % (PYNQ, path), local], check=True, timeout=60,
                   capture_output=True)
    pynq('rm -f %s' % shlex.quote(path), 30)
    try:
        z = np.load(local)
        h = float(z['helper_hz'][0])
        row['helper_hz'] = h
        U = {}
        for u in UNITS:
            _, edges, _ = B.bursts(z['unit%d' % u])
            row['u%d_ept' % u] = round(float(edges.mean()), 4)     # chatter
            try:                     # an oscillating, undriven unit has no beat to fold
                with contextlib.redirect_stdout(io.StringIO()):
                    a = B.analyse_unit('unit%d' % u, z['unit%d' % u], h, force=True)
                row['u%d_top' % u] = round(100 * a['top'], 1)
                row['u%d_beat_hz' % u] = round(h / a['P'], 3)
                if 'sel' in a:
                    U[u] = X.unit(z, 'unit%d' % u, h, force=True)
            except Exception:
                pass
        if 1 in U:
            for u in SAME_CLOCK + OTHER_CLOCK:
                if u not in U:
                    continue
                tau, host = X.pair_series(U[u], U[1])
                t = (host - host[0]) / 1e9
                p = np.polyfit(t, tau, 1)
                if u in SAME_CLOCK:
                    row['p%d_1_ps' % u] = round(float(tau.mean()), 1)
                    row['p%d_1_rms_ps' % u] = round(float((tau - np.polyval(p, t)).std()), 1)
                else:
                    row['f%d_1_ppb' % u] = round(float(p[0]) * 1e-3, 3)
    finally:
        if not keep:
            os.remove(local)


def slips(row):
    out = pynq('./pynq-run si_watch.py watch 10 12', 60)
    m = re.search(r'TOTAL (\d+) s: PLLA slips (\d+), other steps (\d+), HO-beat jumps (\d+) '
                  r'\(PLLB-only (\d+)\); chunks with a latched LOL/LOS flag: (\d+)', out)
    if not m:
        raise IOError('si_watch: ' + out.strip()[-80:])
    for k, v in zip(('slip_s', 'plla_slips', 'other_steps', 'ho_jumps', 'pllb_jumps',
                     'lol_chunks'), m.groups()):
        row[k] = int(v)
    m = re.search(r'HELPER ([\d.]+) Hz against the PS clock', out)
    if m:
        row['helper_ps_hz'] = float(m.group(1))


def rails(row, cg2_zero):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for serial, cal, chans in ((CG1, CG1_CAL, (('A', 'v5_hdr'), ('B', 'v3a_far'))),
                                   (CG2, cg2_zero, (('A', 'v3d'),))):
            with CircuitGear(serial_number=serial, calibration_file=cal) as cg:
                sc = cg.scope
                sc.auto_zero(''.join(ch for ch, _ in chans), ranges=('high',))
                for ch, _ in chans:
                    sc.set_range(ch, 'high')
                    sc.set_coupling(ch, 'DC')
                caps = [sc.capture(force=True) for _ in range(4)]
                for ch, key in chans:
                    v = np.concatenate([c.a if ch == 'A' else c.b for c in caps])
                    row[key] = round(float(v.mean()), 4)


def scope(row):
    with SDS2104X() as s:
        for c in (1, 2, 3, 4):
            row['ch%d_pkpk' % c] = s.pava('PKPK', c)
            row['ch%d_mean' % c] = s.pava('MEAN', c)


def heater(state):
    out = pynq('./pynq-run heater.py %s' % state, 60)
    if 'HEATER %s' % state not in out:
        raise IOError('heater.py %s: %s' % (state, out.strip()[-80:]))
    return state


def schedule_state(plan, minutes):
    state = None
    for m, st in plan:
        if minutes >= m:
            state = st
    return state


def zero_cg2(out_dir):
    """CG-2 has only its factory calibration, and its zero reads ~+0.13 V
    (round 45): measure the zero once with AC coupling and keep it."""
    path = os.path.join(out_dir, '%s_autozero.json' % CG2)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with CircuitGear(serial_number=CG2) as cg:
            z = cg.scope.auto_zero('AB', ranges=('high',))
            cg.save_calibration(path)
    print('CG-2 zero before correction: %s' % z, flush=True)
    return path


COLUMNS = (['utc', 'unix'] + ['T' + a[2:] for a in THERMS] + ['probe', 'helper_hz']
           + ['u%d_%s' % (u, k) for u in UNITS for k in ('top', 'beat_hz', 'ept')]
           + ['p%d_1_%s' % (u, k) for u in SAME_CLOCK for k in ('ps', 'rms_ps')]
           + ['f%d_1_ppb' % u for u in OTHER_CLOCK]
           + ['slip_s', 'plla_slips', 'other_steps', 'ho_jumps', 'pllb_jumps', 'lol_chunks',
              'helper_ps_hz',
              'v5_hdr', 'v3a_far', 'v3d']
           + ['ch%d_%s' % (c, k) for c in (1, 2, 3, 4) for k in ('pkpk', 'mean')]
           + ['heater', 'errors'])


def main():
    args = sys.argv[1:]
    period = 90.0
    if '--period' in args:
        i = args.index('--period')
        period = float(args[i + 1])
        del args[i:i + 2]
    plan = []
    if '--heater' in args:
        i = args.index('--heater')
        for item in args[i + 1].split(','):
            m, st = item.split(':')
            if st not in ('on', 'off'):
                raise SystemExit('--heater: state must be on or off, not %r' % st)
            plan.append((float(m), st))
        plan.sort()
        del args[i:i + 2]
    if len(args) != 1:
        print(__doc__)
        return 2
    t_end = time.time() + float(args[0]) * 3600
    out_dir = os.path.join(HERE, 'overnight_%s' % time.strftime('%Y%m%dT%H%MZ', time.gmtime()))
    os.makedirs(out_dir)
    cg2_zero = zero_cg2(out_dir)
    print('logging to %s until %s' % (out_dir, time.strftime('%Y-%m-%d %H:%M %Z',
                                                             time.localtime(t_end))), flush=True)
    last_keep = 0.0
    t_start = time.time()
    h_state = None
    cutoff = False
    with open(os.path.join(out_dir, 'log.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        try:
            while time.time() < t_end:
                t0 = time.time()
                row = {'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t0)),
                       'unix': round(t0, 1)}
                errors = []
                if plan:
                    want = schedule_state(plan, (t0 - t_start) / 60.0)
                    if cutoff:
                        want = 'off'
                    if want and want != h_state:
                        try:
                            h_state = heater(want)
                            print('%s  heater %s' % (row['utc'], want), flush=True)
                        except Exception as e:
                            errors.append('heater: %s' % str(e)[:100])
                    row['heater'] = h_state
                keep = t0 - last_keep >= 3600
                def guarded_temps():
                    nonlocal_cutoff = temps(row)
                    hot = max([row.get(k) or -273.0 for k in ('T' + a[2:] for a in THERMS)]
                              + [row.get('probe') or -273.0])
                    if plan and hot > HEATER_MAX_C and not cutoff_box[0]:
                        cutoff_box[0] = True
                        heater('off')
                        row['heater'] = 'cutoff'
                        print('%s  HEATER CUT OFF: %.2f C > %.1f C' % (row['utc'], hot, HEATER_MAX_C),
                              flush=True)
                    return nonlocal_cutoff
                cutoff_box = [cutoff]
                for name, fn in (('temps', guarded_temps),
                                 ('beats', lambda: beats(row, out_dir, keep)),
                                 ('slips', lambda: slips(row)),
                                 ('rails', lambda: rails(row, cg2_zero)),
                                 ('scope', lambda: scope(row))):
                    try:
                        fn()
                    except Exception as e:
                        errors.append('%s: %s' % (name, str(e).splitlines()[0][:100]
                                                  if str(e) else type(e).__name__))
                if keep and 'u1_top' in row:
                    last_keep = t0
                if cutoff_box[0] and not cutoff:
                    cutoff, h_state = True, 'off'
                if plan and h_state == 'on' and row.get('T48') is None:
                    # no temperatures this row: no heat until they come back
                    try:
                        h_state = heater('off')
                        row['heater'] = 'off (no temperatures)'
                    except Exception as e:
                        errors.append('heater off: %s' % str(e)[:80])
                row['errors'] = ' | '.join(errors)
                w.writerow(row)
                f.flush()
                print('%s  T48 %s probe %s  p2-1 %s ps  p11-1 %s ps  slips %s  3V3_A %s  %s'
                      % (row['utc'], row.get('T48'), row.get('probe'), row.get('p2_1_ps'),
                         row.get('p11_1_ps'), row.get('plla_slips'), row.get('v3a_far'),
                         row['errors'] or 'ok'), flush=True)
                time.sleep(max(0.0, period - (time.time() - t0)))
        except KeyboardInterrupt:
            pass
        finally:
            if plan:
                try:
                    heater('off')
                    print('heater off at the end', flush=True)
                except Exception as e:
                    print('COULD NOT TURN THE HEATER OFF: %s' % e, flush=True)
    print('done:', out_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
