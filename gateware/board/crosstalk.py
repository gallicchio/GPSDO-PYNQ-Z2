#!/usr/bin/env python3
"""T2: crosstalk read as phase -- round 45 (REVB_CHANGES items 10 and 13).
Runs on the LAPTOP.

    python3 crosstalk.py                  # every condition below, ~15 min
    python3 crosstalk.py baseline hp      # some of them
    python3 crosstalk.py analyse DIR      # again, from the saved recordings

Each condition records units 1, 2, 4, 11 and 12 and reads the phase tone, in
ps (peak), at each aggressor's offset from the SDG's 10 MHz:

    unit 2 - unit 1    both from the SDG, so its own wander cancels: the
                       sensitive victim pair (32 ps rms per transition)
    unit 11 - unit 1   the HP against the SDG: noisier (the HP's lock wanders
                       ~600 ps rms), but unit 11 is the aggressor's own unit
                       when the HP is offset

The aggressors, each one's offset measured from the recording itself (its
unit against unit 1):

    unit 4    the free-running 33220A, about -184 Hz; always on
    unit 12   HO, the board's TCXO through CLK1, about +9 Hz
    unit 11   the HP at 10 MHz + D, locked to the SDG, so D is exact ('hp')
    unit 9    the CircuitGear's generator ('cg'): not a beat, so its offset
              is taken from its fold period

Conditions:

    baseline   the bench as it stands
    hp         the HP at 10 MHz + 0.5 Hz, then + 5 Hz, then back
    ho         CLK1 (HO) at 2, 4 and 6 mA and off, then the standard 8 mA
    cg         CG-2 on unit 9: 10 MHz 2.8 Vpp, 1 kHz 2.8 Vpp, then off

A tone's amplitude comes from a least-squares sinusoid on the pair, fitted
together with a straight line. Its floor is the same fit at ten neighbouring
frequencies, spaced 2/T apart, where T is the recording's length.  Everything
is put back.  Output: crosstalk_<UTC>/ beside this file, with each recording
and results.json.
"""
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import time
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import beats as B                                              # noqa: E402
import overnight as O                                          # noqa: E402
import xcheck as X                                             # noqa: E402

sys.path.insert(0, os.path.join(O.LIC, 'hp'))
UNITS = (1, 2, 4, 9, 11, 12)
SECS = 60


def record(out_dir, tag, secs=SECS):
    out = O.pynq("mkdir -p %s && cd %s && ~/%s/pynq-run ~/%s/beats.py record %d %s 2>&1 "
                 "| grep -o '/[^ ]*[.]npz'" % (O.SHM, O.SHM, O.RDIR, O.RDIR, secs,
                                                ' '.join(map(str, UNITS))), secs + 120)
    path = out.strip().splitlines()[-1] if out.strip() else ''
    if not path.endswith('.npz'):
        raise IOError('beats.py: no file (%r)' % out.strip()[-80:])
    local = os.path.join(out_dir, '%s.npz' % tag)
    subprocess.run(O.SCP + ['%s:%s' % (O.PYNQ, path), local], check=True, timeout=120,
                   capture_output=True)
    O.pynq('rm -f %s' % shlex.quote(path), 30)
    return local


def tone(t, y, f, n_side=10):
    """Amplitude (ps, peak) of a sinusoid at f in y(t), fitted with a line;
    and the floor: the rms of the same fit at n_side frequencies around f."""
    T = t[-1] - t[0]

    def amp(fr):
        A = np.column_stack([np.ones_like(t), t - t.mean(),
                             np.cos(2 * np.pi * fr * t), np.sin(2 * np.pi * fr * t)])
        c, *_ = np.linalg.lstsq(A, y, rcond=None)
        return float(np.hypot(c[2], c[3]))
    side = [f + k * 2.0 / T for k in range(-n_side // 2, n_side // 2 + 1) if k != 0]
    side = [s for s in side if s > 0]
    return amp(f), float(np.sqrt(np.mean([amp(s) ** 2 for s in side])))


def analyse_file(path, cg_on=None):
    z = np.load(path)
    h = float(z['helper_hz'][0])
    U, offs, tops = {}, {}, {}
    for u in UNITS:
        k = 'unit%d' % u
        if k not in z.files:
            continue
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                a = B.analyse_unit(k, z[k], h, force=True)
            tops[u] = round(100 * a['top'], 1)
            if 'sel' in a:
                U[u] = X.unit(z, k, h, force=True)
            # the input's offset from 10 MHz, from its fold period (helper
            # units): f_in = helper - helper / P
            offs[u] = (h - h / a['P']) - 1e7
        except Exception:
            pass
    res = {'file': os.path.basename(path), 'top': tops}
    if 1 not in U:
        res['error'] = 'unit 1 not analysable'
        return res
    f1 = offs[1]
    # each aggressor's offset from unit 1, Hz: units 4, 11 and 12 from their
    # pair slope (exact); unit 9 from its fold period (approximate)
    agg = {}
    for u in (4, 11, 12):
        if u in U:
            tau, host = X.pair_series(U[u], U[1])
            tt = (host - host[0]) / 1e9
            agg[u] = float(np.polyfit(tt, tau, 1)[0]) * 1e-5       # ps/s -> Hz at 10 MHz
    if cg_on is None:                         # re-analysis: judge from the file name
        cg_on = os.path.basename(path).startswith('cg_') and 'off' not in path
    if cg_on and 9 in offs:
        agg[9] = offs[9] - f1                 # undriven, unit 9 oscillates: no aggressor
    res['offsets_hz'] = {str(u): round(v, 4) for u, v in agg.items()}
    pairs = {}
    for v in (2, 11):
        if v not in U:
            continue
        tau, host = X.pair_series(U[v], U[1])
        tt = (host - host[0]) / 1e9
        lin = np.polyfit(tt, tau, 1)
        row = {'mean_ps': round(float(tau.mean()), 2),
               'rms_ps': round(float((tau - np.polyval(lin, tt)).std()), 2)}
        for u, d in agg.items():
            f = abs(d)
            if not (0.05 < f < 500):           # u == v: the ramp's own residual
                continue
            a, fl = tone(tt, tau, f)
            row['tone_u%d_%.3fHz' % (u, f)] = [round(a, 3), round(fl, 3)]
        pairs['%d-1' % v] = row
    res['pairs'] = pairs
    return res


def show(tag, r):
    if 'error' in r:
        print('%-26s %s' % (tag, r['error']), flush=True)
        return
    parts = []
    for p, row in r['pairs'].items():
        tones = ', '.join('%s %.2f (floor %.2f)' % (k[5:].replace('_', ' at '), v[0], v[1])
                          for k, v in row.items() if k.startswith('tone_'))
        parts.append('%s: rms %.1f ps; %s' % (p, row['rms_ps'], tones or '-'))
    print('%-26s offsets %s\n%28s%s' % (tag, r['offsets_hz'], '', ('\n%28s' % '').join(parts)),
          flush=True)


def main():
    args = sys.argv[1:] or ['baseline', 'hp', 'ho', 'cg']
    if args[0] == 'analyse':
        d = args[1]
        res = {}
        for f in sorted(os.listdir(d)):
            if f.endswith('.npz'):
                res[f[:-4]] = analyse_file(os.path.join(d, f))
                show(f[:-4], res[f[:-4]])
        return 0
    out_dir = os.path.join(HERE, 'crosstalk_%s' % time.strftime('%Y%m%dT%H%MZ', time.gmtime()))
    os.makedirs(out_dir)
    results = {}

    def run(tag, secs=SECS):
        path = record(out_dir, tag, secs)
        results[tag] = analyse_file(path)
        show(tag, results[tag])
        json.dump(results, open(os.path.join(out_dir, 'results.json'), 'w'), indent=1)

    if 'baseline' in args:
        run('baseline')
    if 'hp' in args:
        from hp_33120A import HP33120A
        with HP33120A() as g:
            w0 = g.wave()
            assert w0['function'] == 'SIN' and abs(w0['freq'] - 1e7) < 1e-3, w0
            try:
                for d in (0.5, 5.0):
                    g.sine(1e7 + d, w0['vpp'])
                    time.sleep(1.0)
                    run('hp_plus_%gHz' % d)
            finally:
                g.sine(1e7, w0['vpp'])
                print('HP put back:', g.wave(), flush=True)
    if 'ho' in args:
        try:
            for c1 in ('2', '4', '6', 'off'):
                print(O.pynq('./pynq-run si_set.py 2 %s 2>&1 | tail -1' % c1, 60).strip()[-120:],
                      flush=True)
                run('ho_clk1_%s' % c1, 40)
        finally:
            print(O.pynq('./pynq-run si_set.py standard 2>&1 | tail -1', 60).strip()[-120:],
                  flush=True)
        run('ho_clk1_8_standard', 40)
    if 'cg' in args:
        from syscomp_circuit_gear import CircuitGear

        def cg2(f=None, amp=0.0):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with CircuitGear(serial_number=O.CG2) as cg:        # reset: generator off
                    if f:
                        cg.gen.sine(f, amplitude=amp, offset=0.0)
        try:
            cg2(10e6, 1.4)
            run('cg_10MHz_2.8Vpp', 40)
            cg2(1e3, 1.4)
            run('cg_1kHz_2.8Vpp', 40)
        finally:
            cg2()
        run('cg_off', 40)
    print(out_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
