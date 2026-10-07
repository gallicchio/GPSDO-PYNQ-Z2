#!/usr/bin/env python3
"""Look at beats by their TIMESTAMPS -- handbook steps 5 and 6.

    ./pynq-run beats.py record 20 13            # on the PYNQ: unit 13 for 20 s
    ./pynq-run beats.py record 20 1 2 11        # units 1, 2 and 11
    python3 beats.py analyse beats_1_2_11_<time>.npz   # on the laptop (numpy)

Units are numbered as on the silkscreen, 1..13; unit n is beat slot n-1.

WHY NOT THE EDGE COUNT.  The core keeps each slot's LAST rising-edge timestamp
and counts every rising edge, and it does not deglitch yet.  Round 39, the
first board: a function generator's beat read 4-6 rising edges per beat
period -- the edge chatters while the input's phase slides through the
helper's sampling instant -- and an unplugged squarer can chatter at a similar
rate, so the count cannot tell a beat from nothing.  The timestamps can: a
beat's edges fall in two narrow clusters per period (its rising and falling
transitions), chatter's anywhere.

`record` polls the slots as fast as the ARM can (~100 us a loop) and keeps
every change of the count with its timestamp.  `analyse` folds each unit's
timestamps at its own beat period, reports whether it is a beat, its
frequency, how many rising edges each transition makes, and the per-edge
scatter; and for every pair of units on the same source, their difference
edge by edge -- step 6 wants that constant, not drifting.
"""
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

T_SIG = 100e-9                 # one 10 MHz input cycle, s
F_HELPER_NOM = 10001234.4
BURST_GAP = 1000               # helper cycles: a new transition, not more chatter


# ---------------------------------------------------------------------------
# record -- on the PYNQ
# ---------------------------------------------------------------------------
def record(seconds, units):
    import driver                                          # noqa: F401
    from driver import attach
    from driver.dmtd_constants import REG_CHAN0, CHAN_STRIDE, OFF_COUNT, OFF_TS_LO, OFF_TS_HI
    from pynq import Overlay
    ol = Overlay(os.path.join(HERE, 'dmtd_top.bit'), download=False)
    core = attach(ol)
    rd = core.mmio.read
    base = [REG_CHAN0 + (u - 1) * CHAN_STRIDE for u in units]
    rows = [[] for _ in units]
    prev = [None] * len(units)
    # round 43: a wall-clock anchor for the monotonic host times, so events
    # logged on another machine (a generator stepped from the laptop) can be
    # placed in the record.  Both clocks are NTP-disciplined.
    wall0, mono0 = time.time(), time.monotonic_ns()
    print('recording from %.3f' % wall0, flush=True)    # xcheck.py waits for this
    t_end = time.monotonic_ns() + int(seconds * 1e9)
    loops = 0
    while True:
        now = time.monotonic_ns()
        if now > t_end:
            break
        loops += 1
        for i, b in enumerate(base):
            c0 = rd(b + OFF_COUNT)
            if c0 == prev[i]:
                continue
            lo = rd(b + OFF_TS_LO)
            hi = rd(b + OFF_TS_HI)
            if rd(b + OFF_COUNT) != c0:
                continue                   # changed under the read: next loop
            prev[i] = c0
            rows[i].append((now, c0, (hi << 32) | lo))
    out = {'unit%d' % u: np.array(r, dtype=np.int64) for u, r in zip(units, rows)}
    out['wall0'] = np.array([wall0])
    out['mono0'] = np.array([mono0], dtype=np.int64)
    out['helper_hz'] = np.array([core.settle_helper()])
    # round 42: stamped, so an "after rework" recording of the same units does
    # not overwrite the "before" one it has to be compared with
    fn = os.path.join(os.getcwd(), 'beats_%s_%s.npz' % ('_'.join(map(str, units)),
                                                       time.strftime('%Y%m%dT%H%M%S')))
    np.savez(fn, **out)
    print('%d polls in %.1f s (%.0f us each); updates per unit %s; helper %.3f Hz -> %s'
          % (loops, seconds, seconds * 1e6 / max(1, loops),
             dict(zip(units, [len(r) for r in rows])), out['helper_hz'][0], fn))


# ---------------------------------------------------------------------------
# analyse -- on the laptop
# ---------------------------------------------------------------------------
def bursts(rows):
    """One entry per transition: (last rising-edge ts, rising edges in it,
    host time).  A new burst starts where the timestamp jumps by more than
    BURST_GAP helper cycles."""
    ts, cnt, t = rows[:, 2].astype(np.float64), rows[:, 1], rows[:, 0]
    new = np.concatenate(([True], np.diff(ts) > BURST_GAP))
    idx = np.flatnonzero(new)
    ends = np.concatenate((idx[1:] - 1, [len(ts) - 1]))
    edges = np.diff(np.concatenate(([cnt[0] - 1], cnt[ends])))
    return ts[ends], edges, t[ends]


def fold_metric(x, P):
    """How tightly x (helper cycles) folds at period P: the larger of the
    first and second circular harmonics, since a beat's two transitions sit
    about half a period apart and cancel in the first."""
    a = 2 * np.pi * (x % P) / P
    return max(abs(np.mean(np.exp(1j * a))), abs(np.mean(np.exp(2j * a))))


def find_period(x, lo=6000.0, hi=11000.0):
    """The beat period in helper cycles, coarse on the first ~1000
    transitions and then fine on all of them.

    The window is beats of 909-1667 Hz: a 10 MHz input 30 ppm either side of
    nominal, which a function generator, a GPSDO and a +/-2.5 ppm TCXO all
    sit well inside.  It must exclude half the period: there the rising and
    falling transitions land on top of each other and fold just as tightly,
    and round 39's first version of this reported a 2486 Hz 'beat'."""
    x = x - x[0]
    # ~600 beat periods fold sharply enough that a 0.5-cycle grid cannot step
    # over the peak (it is ~P/2400 wide), and keep each block of trial periods
    # x transitions small enough to hold in memory.
    sub = x[:1000]
    grid = np.arange(lo, hi, 0.5)
    best, bp = -1.0, None
    for chunk in np.array_split(grid, max(1, len(grid) // 500)):
        a = 2 * np.pi * (sub[None, :] % chunk[:, None]) / chunk[:, None]
        m = np.maximum(np.abs(np.exp(1j * a).mean(axis=1)),
                       np.abs(np.exp(2j * a).mean(axis=1)))
        k = int(np.argmax(m))
        if m[k] > best:
            best, bp = m[k], chunk[k]
    for step, span in ((0.01, 0.5), (0.0005, 0.02)):
        fine = np.arange(bp - span, bp + span, step)
        m = [fold_metric(x, P) for P in fine]
        k = int(np.argmax(m))
        best, bp = m[k], fine[k]
    return bp, best


def analyse_unit(name, rows, helper, force=False):
    """force=True carries on past the 60 % test, for callers that judge a
    unit by its pairs (overnight.py, round 45): `top` is measured in 0.1 s
    windows, so a source wandering fast against the helper fails it while
    still being a perfectly good beat."""
    last, edges, t = bursts(rows)
    span_s = (rows[-1, 0] - rows[0, 0]) / 1e9
    rate = (rows[-1, 1] - rows[0, 1]) / span_s if span_s > 0 else 0.0
    P, conc = find_period(last)
    ph = ((last - last[0]) % P) / P
    hist = np.histogram(ph, bins=50, range=(0, 1))[0]
    # Share of transitions in the two clusters (the four densest of 50 bins),
    # 0.1 s at a time: over a longer stretch a source wandering against the
    # helper smears its clusters across several bins, which says nothing about
    # whether it is a beat.  Round 40: the Siglent SDG1032X wanders ~15 % of a
    # beat period in 0.2 s, and one-second windows (round 39) called it "not a
    # beat" on two channels that were fine -- their difference was constant
    # to 30 ps rms.  An input chattering like an unplugged one scores ~30 %.
    tops = []
    t_s = (t - t[0]) / 1e9
    for s in np.arange(0.0, t_s[-1] - 0.1, 0.1):
        sel = (t_s >= s) & (t_s < s + 0.1)
        if sel.sum() >= 50:
            h = np.histogram(ph[sel], bins=50, range=(0, 1))[0]
            tops.append(np.sort(h)[-4:].sum() / float(sel.sum()))
    top2 = float(np.median(tops)) if tops else np.sort(hist)[-4:].sum() / float(len(ph))
    is_beat = top2 > 0.6
    out = dict(name=name, P=P, rate=rate, conc=conc, top=top2, beat=is_beat)
    print('\n%s: %.0f rising edges/s over %.1f s' % (name, rate, span_s))
    if not is_beat:
        print('   NOT A BEAT: the best fold (P = %.1f) puts only %.0f%% of the '
              'transitions in its two densest bins -- edges at every phase, '
              'which is chatter, not a squared 10 MHz' % (P, 100 * top2))
        if not force:
            return out
    f_beat = helper / P
    print('   beat %.4f Hz (period %.3f helper cycles; %.0f%% of transitions in '
          'the two clusters) -> input %.4f Hz = 10 MHz %+.3f ppm, in the same '
          'units as the helper (%.3f Hz)'
          % (f_beat, P, 100 * top2, helper - f_beat, ((helper - f_beat) / 1e7 - 1) * 1e6, helper))
    # the two families: the cluster present in (nearly) every period is the
    # rising transition; the other is the falling one, present when it
    # chatters.  Followed transition by transition, so that a source wandering
    # against the helper is tracked: one fold of the whole run mixes the two
    # families for such a source, and fixed windows flip between them.
    near = np.zeros(len(ph), bool)
    h = np.histogram(ph[:250], bins=50, range=(0, 1))[0]
    ref = (np.argmax(h) + 0.5) / 50
    for i, p in enumerate(ph):
        d = ((p - ref + 0.5) % 1) - 0.5
        if abs(d) < 0.25:
            near[i] = True
            ref = (ref + 0.3 * d) % 1
    fams = []
    for sel in (near, ~near):
        if sel.sum() < 10:
            continue
        L = last[sel]
        n = np.round((L - L[0]) / P)
        resid = []
        for i in range(0, len(L) - 124, 124):             # ~0.1 s segments
            x = n[i:i + 124] - n[i:i + 124].mean()
            y = L[i:i + 124] - n[i:i + 124] * P
            resid.extend(y - np.polyval(np.polyfit(x, y, 2), x))
        resid = np.array(resid) if resid else np.zeros(1)
        fams.append((sel.sum() / span_s, edges[sel].mean(), resid.std(), sel))
    fams.sort(key=lambda f: -f[0])
    ps_per_cycle = T_SIG / P * 1e12
    for label, (per_s, e, rms, _) in zip(('rising transition', 'falling transition'), fams):
        print('   %-18s %6.0f per s; %.2f rising edges each; last edge scatters '
              '%.2f cycles = %.0f ps rms about a 0.1 s quadratic'
              % (label, per_s, e, rms, rms * ps_per_cycle))
    out.update(last=last, sel=fams[0][3], ps_per_cycle=ps_per_cycle)
    return out


def compare(a, b):
    """Edge-by-edge difference of two units on the same source.

    Every transition of `a` is paired with the nearest one of `b` in helper
    time, whichever family each belongs to: a source's wander is common to
    both and cancels, so this works for a generator that drifts (round 40:
    the Siglent) where a per-unit fold does not.  The answer is the dominant
    cluster of differences; a second cluster, where one unit's falling
    transition bounces and the other's does not, is reported separately."""
    if abs(a['P'] - b['P']) / a['P'] > 1e-4:
        fa, fb = HELPER / a['P'], HELPER / b['P']
        print('   %s vs %s: different sources -- beats %.4f and %.4f Hz, so the '
              'inputs differ by %.4f Hz = %.4f ppm' % (a['name'], b['name'], fa, fb,
                                                       fa - fb, (fa - fb) / 10.0))
        return
    la, lb = a['last'], b['last']
    j = np.clip(np.searchsorted(lb, la), 1, len(lb) - 1)
    j = np.where(np.abs(lb[j] - la) < np.abs(lb[j - 1] - la), j, j - 1)
    d = la - lb[j]
    P = a['P']
    d = d[np.abs(d) < P / 4]                        # a partner in the same transition
    if len(d) < 20:
        print('   %s - %s: too few matching transitions' % (a['name'], b['name']))
        return
    h, e = np.histogram(d, bins=np.arange(d.min() - 1, d.max() + 3, 2.0))
    peak = (e[np.argmax(h)] + e[np.argmax(h) + 1]) / 2
    mad = np.median(np.abs(d - peak))
    core = np.abs(d - peak) < max(20.0, 6 * mad)
    dc = d[core]
    q = max(1, len(dc) // 5)
    ps = a['ps_per_cycle']
    print('   %s - %s, same source: %d of %d paired transitions in the main cluster; '
          'mean %.2f cycles = %.1f ps, rms %.2f cycles = %.1f ps; by fifths of the '
          'run %s cycles'
          % (a['name'], b['name'], core.sum(), len(d), dc.mean(), dc.mean() * ps,
             dc.std(), dc.std() * ps,
             ', '.join('%.2f' % np.median(dc[i * q:(i + 1) * q]) for i in range(5))))
    rest = d[~core]
    if len(rest) > 0.1 * len(d):
        h2, e2 = np.histogram(rest, bins=np.arange(rest.min() - 1, rest.max() + 3, 2.0))
        p2 = (e2[np.argmax(h2)] + e2[np.argmax(h2) + 1]) / 2
        print('   ... and a second cluster near %.0f cycles holding %d%% of them'
              % (p2, 100 * np.sum(np.abs(rest - p2) < 20) / len(d)))


HELPER = F_HELPER_NOM


def analyse(fn):
    global HELPER
    z = np.load(fn)
    HELPER = float(z['helper_hz'][0]) if 'helper_hz' in z.files else F_HELPER_NOM
    print('%s: helper %.3f Hz as the core measured it against the PS clock'
          % (os.path.basename(fn), HELPER))
    res = []
    for key in sorted((k for k in z.files if k.startswith('unit')), key=lambda s: int(s[4:])):
        rows = z[key]
        if len(rows) < 200:
            print('\n%s: %d updates in the run -- quiet, nothing to fold' % (key, len(rows)))
            continue
        res.append(analyse_unit(key, rows, HELPER))
    beats = [r for r in res if r['beat']]
    if len(beats) > 1:
        print('\npairs:')
        for i in range(len(beats)):
            for j in range(i + 1, len(beats)):
                compare(beats[i], beats[j])


if __name__ == '__main__':
    if len(sys.argv) >= 4 and sys.argv[1] == 'record':
        record(float(sys.argv[2]), [int(u) for u in sys.argv[3:]])
    elif len(sys.argv) == 3 and sys.argv[1] == 'analyse':
        analyse(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
