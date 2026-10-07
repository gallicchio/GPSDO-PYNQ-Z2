#!/usr/bin/env python3
"""Plot and fit an overnight log -- round 45.  Runs on the LAPTOP.

    python3 overnight_plot.py overnight_<UTC>/              # -> overnight.png beside log.csv
    python3 overnight_plot.py DIR1 DIR2 ...                 # several segments of one night,
                                                            # joined; the figure goes in the last

One figure, time on the x axis (hours, local time at the ticks):

  1. the board's eight thermometers and the 1-Wire probe;
  2. unit 2 - unit 1 (same SDG, units on opposite edges);
  3. unit 11 - unit 1 (the HP, locked to the SDG's rear 10 MHz);
  4. the board's TCXO (unit 12, HO) and the free-running 33220A (unit 4)
     against the SDG, in ppb;
  5. the rails, scaled by round 45's one-point DMM factors;
  6. the scope's amplitudes on CH1-CH4, as a change in percent;
  7. each unit's fold concentration (`top`);
  8. PLLA slips and HO-beat jumps.

It also prints the drift of each phase against the thermometers: a straight
line in temperature, plus the left-right difference for unit 2 - unit 1.
"""
import csv
import os
import sys
import time

import numpy as np

# Round 45: CircuitGears read ~2 % low at DC against Jason's DMM (3.185 V and
# 3.296 V on +3V3_A and +3V3_D at J5001, 2026-10-07 00:00 UTC, board ~25 C).
# One-point factors.  The first segment read CG-1 with its calibration file's
# zero (which drifts); later segments (with `u1_ept`) zero both units every row.
RAIL_SCALE = {'v3a_far': 1.0296, 'v3d': 1.0178, 'v5_hdr': 1.0}
RAIL_SCALE_ZEROED = {'v3a_far': 1.0218, 'v3d': 1.0178, 'v5_hdr': 1.0}
THERM = {'T48': 'U5001 left, y 48 (unit 1)', 'T49': 'U5002 right, y 48 (unit 2)',
         'T4A': 'U5003 left, y 90', 'T4B': 'U5004 right, y 90',
         'T4C': 'U5005 left, y 132 (unit 11)', 'T4D': 'U5006 right, y 132 (unit 12)',
         'T4E': 'U5007 centre top (helper)', 'T4F': 'U5008 left, y 168'}


def load(paths):
    """One or more log.csv files, joined in order; a column missing from a
    segment (an older format) is NaN there.  Rails are scaled per segment."""
    segs = [list(csv.DictReader(open(p))) for p in paths]
    keys = []
    for rows in segs:
        keys += [k for k in rows[0] if k not in keys]
    cols = {k: [] for k in keys}
    for rows in segs:
        scale = RAIL_SCALE_ZEROED if 'u1_ept' in rows[0] else RAIL_SCALE
        for r in rows:
            for k in keys:
                v = r.get(k, '')
                if k in ('utc', 'errors'):
                    cols[k].append(v)
                else:
                    x = float(v) if v not in ('', 'None') else np.nan
                    cols[k].append(x * scale.get(k, 1.0))
    return {k: (v if k in ('utc', 'errors') else np.array(v)) for k, v in cols.items()}


def fit(y, *xs):
    """Least squares y = c0 + sum(ci xi); returns coefficients and rms residual."""
    ok = np.isfinite(y)
    for x in xs:
        ok &= np.isfinite(x)
    A = np.column_stack([np.ones(ok.sum())] + [x[ok] for x in xs])
    c, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
    return c, float(np.std(y[ok] - A @ c))


def main():
    dirs = sys.argv[1:] or ['.']
    d = dirs[-1]
    c = load([os.path.join(x, 'log.csv') for x in dirs])
    t = c['unix']
    h = (t - t[0]) / 3600
    n = len(t)
    print('%d rows, %.2f h, from %s; rows with errors: %d'
          % (n, h[-1], c['utc'][0], sum(1 for e in c['errors'] if e)))
    tb = np.mean([c[k] for k in THERM], axis=0)               # board mean

    print('\nthermometers, start -> end (deg C):')
    for k, where in THERM.items():
        print('  %s %-32s %7.3f -> %7.3f   (%+.3f)' % (k, where, c[k][0], c[k][-1], c[k][-1] - c[k][0]))
    print('  probe (DS18B20 on J6001)            %7.3f -> %7.3f   (%+.3f)'
          % (c['probe'][0], c['probe'][-1], c['probe'][-1] - c['probe'][0]))

    print('\nphases (ps), start -> end, and against temperature:')
    lr = c['T49'] - c['T48']                                  # right minus left, unit-1/2 row
    for key, label in (('p2_1_ps', 'unit 2 - unit 1'), ('p11_1_ps', 'unit 11 - unit 1')):
        y = c[key]
        cf, res = fit(y, tb)
        print('  %-17s %9.1f -> %9.1f (%+7.1f); rms in a row %5.1f ps; '
              '%+7.1f ps/K against the board mean (residual %.1f ps)'
              % (label, y[0], y[-1], y[-1] - y[0], np.nanmedian(c[key.replace('_ps', '_rms_ps')]),
                 cf[1], res))
        if key == 'p2_1_ps':
            cf2, res2 = fit(y, tb, lr)
            print('  %-17s %+7.1f ps/K mean, %+7.1f ps/K right-minus-left (residual %.1f ps)'
                  % ('', cf2[1], cf2[2], res2))
        d1 = np.diff(y)
        big = np.nonzero(np.abs(d1) > 5 * np.nanstd(d1))[0]
        print('  %-17s row-to-row steps: rms %.1f ps, largest %+.1f ps; %d step(s) over 5 sigma'
              % ('', np.nanstd(d1), d1[np.nanargmax(np.abs(d1))], len(big)))

    print('\nfrequencies against the SDG (ppb), start -> end:')
    for key, label, tk in (('f12_1_ppb', 'TCXO (unit 12)', 'T4E'), ('f4_1_ppb', '33220A (unit 4)', None)):
        y = c[key]
        line = '  %-16s %10.2f -> %10.2f (%+.2f)' % (label, y[0], y[-1], y[-1] - y[0])
        if tk:
            cf, res = fit(y, c[tk])
            line += '; %+.2f ppb/K against %s (residual %.2f ppb)' % (cf[1], tk, res)
        print(line)

    print('\nrails (V, scaled), start -> end:')
    for k in ('v5_hdr', 'v3a_far', 'v3d'):
        cf, res = fit(c[k], tb)
        print('  %-8s %.4f -> %.4f (%+.1f mV); %+.1f mV/K against the board mean'
              % (k, c[k][0], c[k][-1], 1e3 * (c[k][-1] - c[k][0]), 1e3 * cf[1]))
    print('\nslips: PLLA %d, other steps %d, HO-beat jumps %d (PLLB %d), latched LOL/LOS chunks %d'
          % tuple(int(np.nansum(c[k])) for k in ('plla_slips', 'other_steps', 'ho_jumps',
                                                 'pllb_jumps', 'lol_chunks')))
    print('fold concentration (median): ' + ', '.join(
        'unit %d %.0f%%' % (u, np.nanmedian(c['u%d_top' % u])) for u in (1, 2, 4, 11, 12)))
    if 'u1_ept' in c:
        print('chatter, rising edges per transition (median): ' + ', '.join(
            'unit %d %.3f' % (u, np.nanmedian(c['u%d_ept' % u])) for u in (1, 2, 4, 11, 12)))
    if 'helper_ps_hz' in c and np.isfinite(c['helper_ps_hz']).any():
        y = c['helper_ps_hz']
        ok = np.isfinite(y)
        y0 = np.nanmedian(y)
        cf, res = fit(1e9 * (y / y0 - 1), c['T4E'])
        print('helper against the PS clock: median %.4f Hz; %+.1f ppb/K against T4E, '
              'residual %.1f ppb rms' % (y0, cf[1], res))

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(8, 1, figsize=(11, 22), sharex=True)
    for k in THERM:
        ax[0].plot(h, c[k], lw=1, label='%s %s' % (k, THERM[k]))
    ax[0].plot(h, c['probe'], 'k--', lw=1.2, label='probe (J6001)')
    ax[0].set_ylabel('deg C')
    ax[0].legend(fontsize=6, ncol=3)
    ax[1].plot(h, c['p2_1_ps'], '.', ms=3)
    ax[1].set_ylabel('unit 2 - unit 1 (ps)')
    ax[2].plot(h, c['p11_1_ps'] / 1e3, '.', ms=3, color='C1')
    ax[2].set_ylabel('unit 11 - unit 1 (ns)')
    ax[3].plot(h, c['f12_1_ppb'], '.', ms=3, color='C2', label='TCXO (unit 12)')
    ax3 = ax[3].twinx()
    ax3.plot(h, c['f4_1_ppb'], '.', ms=3, color='C3', label='33220A (unit 4)')
    ax[3].set_ylabel('TCXO vs SDG (ppb)', color='C2')
    ax3.set_ylabel('33220A vs SDG (ppb)', color='C3')
    for k, col in (('v5_hdr', 'C0'), ('v3a_far', 'C1'), ('v3d', 'C2')):
        ax[4].plot(h, 1e3 * (c[k] - np.nanmedian(c[k])), lw=1, color=col,
                   label='%s (median %.3f V)' % (k, np.nanmedian(c[k])))
    ax[4].set_ylabel('rail - median (mV)')
    ax[4].legend(fontsize=7)
    for ch in (1, 2, 3, 4):
        y = c['ch%d_pkpk' % ch]
        ax[5].plot(h, 100 * (y / np.nanmedian(y) - 1), lw=1, label='CH%d (median %.3f Vpp)'
                   % (ch, np.nanmedian(y)))
    ax[5].set_ylabel('scope PKPK change (%)')
    ax[5].legend(fontsize=7)
    for u in (1, 2, 4, 11, 12):
        ax[6].plot(h, c['u%d_top' % u], lw=1, label='unit %d' % u)
    ax[6].set_ylabel('fold concentration (%)')
    ax[6].legend(fontsize=7, ncol=5)
    if 'u1_ept' in c:
        a6 = ax[6].twinx()
        for i, u in enumerate((1, 2, 4, 11, 12)):
            a6.plot(h, c['u%d_ept' % u], ':', lw=1, color='C%d' % i)
        a6.set_ylabel('edges per transition (dotted)')
    if 'helper_ps_hz' in c and np.isfinite(c['helper_ps_hz']).any():
        a3 = ax[3].twinx()
        a3.spines['right'].set_position(('outward', 50))
        y = c['helper_ps_hz']
        a3.plot(h, 1e9 * (y / np.nanmedian(y) - 1), '.', ms=3, color='C4')
        a3.set_ylabel('helper vs PS clock (ppb)', color='C4')
    ax[7].plot(h, c['plla_slips'], '.', label='PLLA slips')
    ax[7].plot(h, c['ho_jumps'], '.', label='HO-beat jumps')
    ax[7].set_ylabel('per 10 s')
    ax[7].legend(fontsize=7)
    ticks = np.arange(0, h[-1] + 0.01, 1.0)
    ax[7].set_xticks(ticks)
    ax[7].set_xticklabels([time.strftime('%H:%M', time.localtime(t[0] + 3600 * x)) for x in ticks])
    ax[7].set_xlabel('local time (start %s UTC)' % c['utc'][0])
    for a in ax:
        a.grid(alpha=0.3)
    fig.tight_layout()
    out = os.path.join(d, 'overnight.png')
    fig.savefig(out, dpi=90)
    print('\n' + out)


if __name__ == '__main__':
    main()
