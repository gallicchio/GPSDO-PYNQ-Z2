#!/usr/bin/env python3
"""RA7 (N1): the OCXO at the board's four corners, the heater stepped -- round 45.21.

    python3 ra7_analyse.py overnight_20261008T2322Z

Units 1, 2, 10 and 11 all take the OCXO (BENCH_WIRING_OCXO.md), so every pair
among them is the board alone.  Each unit's delay against unit 1 (the log's
p2_1, p10_1 and p11_1) is fitted, row by row, three ways:

  A  each unit its own coefficient on its LOCAL temperature:
         d_u - d_1 = a_u T_u - a_1 T_1 + c          (a_1 shared by all three)
  B  one coefficient on the GRADIENT between the two corners:
         d_u - d_1 = k (T_u - T_1) + c
  M  each unit its own coefficient on the board's MEAN temperature:
         d_u - d_1 = m_u T_mean + c

and every model also gets e_u * heater, the heater's instant electrical step (the
pairs jump at switch-on before any thermometer moves: 45.20).  T_u is the board
thermometer nearest unit u: 0x48 (unit 1), 0x49 (2), 0x4D (10), 0x4C (11), all on
the board's edges, ~57 mm out from the squarers.  T_mean is the eight's mean.

Prints each model's coefficients and residuals, the steps at each heater switch,
and the room's own swing; writes ra7.png beside the log.
"""
import csv
import os
import sys

import numpy as np

UNITS = (2, 10, 11)
NEAR = {1: 'T48', 2: 'T49', 10: 'T4D', 11: 'T4C'}
THERMS = ['T%X' % a for a in range(0x48, 0x50)]


def load(d):
    rows = list(csv.DictReader(open(os.path.join(d, 'log.csv'))))
    keys = ['unix'] + THERMS + ['probe'] + ['p%d_1_ps' % u for u in UNITS]

    def f(r, k):
        try:
            return float(r[k])
        except (TypeError, ValueError, KeyError):
            return np.nan
    a = {k: np.array([f(r, k) for r in rows]) for k in keys}
    a['heater'] = np.array([1.0 if (r.get('heater') or '').startswith('on') else 0.0 for r in rows])
    ok = np.all([np.isfinite(a[k]) for k in keys], axis=0)
    a = {k: v[ok] for k, v in a.items()}
    a['h'] = (a['unix'] - a['unix'][0]) / 3600.0
    a['Tmean'] = np.mean([a[k] for k in THERMS], axis=0)
    return a


def fit(y, cols):
    A = np.column_stack(cols + [np.ones_like(y)])
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    r = y - A @ c
    return c, r


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else sorted(x for x in os.listdir('.') if x.startswith('overnight_'))[-1]
    a = load(d)
    n = len(a['h'])
    print('%s: %d rows, %.1f h; heater on in %d rows' % (d, n, a['h'][-1], int(a['heater'].sum())))
    print('temperatures, min..max: ' + '  '.join('%s %.1f..%.1f' % (k, a[k].min(), a[k].max()) for k in THERMS + ['probe']))

    # the heater's switching rows: the step across each switch, and the temperatures' change
    sw = np.where(np.diff(a['heater']) != 0)[0]
    print('\nAt each heater switch (the first row after minus the last row before, 2 min apart):')
    for i in sw:
        st = 'on ' if a['heater'][i + 1] else 'off'
        print('  %5.2f h %s: ' % (a['h'][i + 1], st)
              + '  '.join('u%d-u1 %+6.1f ps' % (u, a['p%d_1_ps' % u][i + 1] - a['p%d_1_ps' % u][i]) for u in UNITS)
              + '   T48 %+.2f K, Tmean %+.2f K' % (a['T48'][i + 1] - a['T48'][i], a['Tmean'][i + 1] - a['Tmean'][i]))

    H = a['heater']
    print('\nModel A: each unit its own coefficient on its local temperature (a_1 shared)')
    # joint fit: stack the three pairs; unknowns a_1, a_2, a_10, a_11, e_u (3), c_u (3)
    Y, rowsA = [], []
    for j, u in enumerate(UNITS):
        y = a['p%d_1_ps' % u]
        for i in range(n):
            row = np.zeros(10)
            row[0] = -a[NEAR[1]][i]            # a_1
            row[1 + j] = a[NEAR[u]][i]         # a_u
            row[4 + j] = H[i]                  # e_u
            row[7 + j] = 1.0                   # c_u
            rowsA.append(row)
            Y.append(y[i])
    A = np.array(rowsA); Y = np.array(Y)
    c, *_ = np.linalg.lstsq(A, Y, rcond=None)
    rA = Y - A @ c
    print('  a_1 %+.2f ps/K; ' % c[0] + '  '.join('a_%d %+.2f ps/K' % (u, c[1 + j]) for j, u in enumerate(UNITS))
          + ';  steps ' + ' '.join('%+.1f' % c[4 + j] for j in range(3)) + ' ps;  residual %.2f ps rms' % rA.std())

    print('\nModel B: one coefficient on the gradient between corners')
    rowsB = []
    for j, u in enumerate(UNITS):
        for i in range(n):
            row = np.zeros(7)
            row[0] = a[NEAR[u]][i] - a[NEAR[1]][i]
            row[1 + j] = H[i]
            row[4 + j] = 1.0
            rowsB.append(row)
    B = np.array(rowsB)
    cb, *_ = np.linalg.lstsq(B, Y, rcond=None)
    rB = Y - B @ cb
    print('  k %+.2f ps/K;  steps ' % cb[0] + ' '.join('%+.1f' % cb[1 + j] for j in range(3))
          + ' ps;  residual %.2f ps rms' % rB.std())

    print('\nModel M: each unit its own coefficient on the mean temperature')
    resM = []
    for u in UNITS:
        cm, rm = fit(a['p%d_1_ps' % u], [a['Tmean'], H])
        resM.append(rm)
        print('  u%d-u1: m %+.2f ps/K, step %+.1f ps, residual %.2f ps rms' % (u, cm[0], cm[1], rm.std()))
    print('  all three: residual %.2f ps rms' % np.concatenate(resM).std())

    print('\nPer pair, model A against B (residual rms, ps):')
    for j, u in enumerate(UNITS):
        print('  u%d-u1: A %.2f  B %.2f  M %.2f' % (u, rA[j * n:(j + 1) * n].std(), rB[j * n:(j + 1) * n].std(), resM[j].std()))

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(3, 1, figsize=(11, 10), sharex=True)
        for u in UNITS:
            y = a['p%d_1_ps' % u]
            ax[0].plot(a['h'], y - y[:10].mean(), label='unit %d - unit 1' % u)
        ax[0].set_ylabel('ps (from the first 20 min)')
        ax[0].legend()
        for k in THERMS:
            ax[1].plot(a['h'], a[k], label=k)
        ax[1].plot(a['h'], a['probe'], 'k--', label='probe (OCXO case)')
        ax[1].set_ylabel('deg C')
        ax[1].legend(ncol=5, fontsize=7)
        for j, u in enumerate(UNITS):
            ax[2].plot(a['h'], rA[j * n:(j + 1) * n], label='A, u%d' % u)
            ax[2].plot(a['h'], rB[j * n:(j + 1) * n], ':', label='B, u%d' % u)
        ax[2].set_ylabel('residual, ps')
        ax[2].legend(ncol=3, fontsize=7)
        for axx in ax:
            for i in sw:
                axx.axvline(a['h'][i + 1], color='0.8', lw=0.8)
        ax[2].set_xlabel('hours from the start')
        fig.tight_layout()
        out = os.path.join(d, 'ra7.png')
        fig.savefig(out, dpi=110)
        print('\n' + out)
    except Exception as e:
        print('plot skipped:', e)


if __name__ == '__main__':
    main()
