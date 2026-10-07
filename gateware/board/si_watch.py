#!/usr/bin/env python3
"""Watch both Si5351 PLLs for slipped reference cycles -- rounds 39 and 40.

    ./pynq-run si_watch.py watch 600 12        # 10 min, HO cabled into unit 12
    ./pynq-run si_watch.py watch 3600 12 --clk0 4   # 1 h with CLK0 at 4 mA
    ./pynq-run si_watch.py matrix 8 2          # CLK0 x CLK1 drives, 8 s x 2 each

Needs HO (CLK1) cabled into one 10 MHz input -- unit 12 above, with its 50R
jumper -- and a programmed Si5351.  `matrix` re-programs the chip for each
case and puts the driver's standard image back at the end.

WHAT IT WATCHES.
  PLLA   the pair register (helper counter vs PS counter, latched together
         every 1024 helper cycles).  A slipped 25 MHz reference cycle is a
         40 ns (4-tick) step.  Round 39: ~650 a second with CLK0 at 8 mA.
  BOTH   HO's own beat.  HO (PLLB) and the helper (PLLA) come from one TCXO,
         so their beat has an EXACT period -- 12501543/1543 helper cycles for
         the standard plan -- and a 40 ns slip of either PLL moves it by 0.4
         of a period.  A jump with no PLLA slip in the same window is PLLB's.
         (A slip of BOTH at once would cancel here; the pair register still
         sees PLLA's half of it.)
  LOL    the Si5351's own sticky loss-of-lock bits, cleared before and read
         after.  Round 40: they never saw 2000 slips a second.

Round 40's answer, HO into 50 ohm: CLK0 at 2 mA was clean in every CLK1
setting, 10 fresh starts in 10, and 600 s continuous (0 slips); at 4 mA it
slipped 900-1400/s whenever CLK1 ran at 4 mA or more; at 8 mA, always.
Round 42 repeated the matrix on the unreworked board, 2026-09-30T23:44Z, and
got the same (logs/matrix_before_20260930T2344Z.log on the PYNQ).

`watch` runs whatever the chip holds, unless --clk0/--clk1 (2, 4, 6 or 8 mA)
say otherwise; then it programs that first and puts the standard image back
at the end.  Round 42: after the XA rework, a clean hour at CLK0 4 mA is the
margin that 2 mA does not have on rev A as built.
"""
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

P_NULL = 12501543.0 / 1543.0          # helper cycles per HO-vs-helper beat
WIN = 0.04                            # s: ~50 beat periods per phase window


def watch(core, seconds, unit=12, verbose=True):
    """Count PLLA slips and HO-beat jumps for `seconds`; returns a dict."""
    from driver.dmtd_constants import (REG_LIVE_LO, REG_LIVE_HI, REG_LIVE_PS_LO,
                                       REG_LIVE_PS_HI, REG_CHAN0, CHAN_STRIDE,
                                       OFF_COUNT, OFF_TS_LO, OFF_TS_HI)
    rd = core.mmio.read
    b = REG_CHAN0 + (unit - 1) * CHAN_STRIDE
    n_max = int(seconds * 12000) + 1000
    pairs = np.zeros((n_max, 3), np.int64)       # host ns, helper, ps
    beats = np.zeros((n_max, 2), np.int64)       # host ns, ts
    npair = nbeat = 0
    last_lo = prev_c = None
    t_end = time.monotonic_ns() + int(seconds * 1e9)
    while True:
        now = time.monotonic_ns()
        if now > t_end or npair >= n_max or nbeat >= n_max:
            break
        lo0 = rd(REG_LIVE_LO)
        if lo0 != last_lo:
            hi = rd(REG_LIVE_HI)
            plo = rd(REG_LIVE_PS_LO)
            phi = rd(REG_LIVE_PS_HI)
            if rd(REG_LIVE_LO) == lo0:
                last_lo = lo0
                pairs[npair] = (now, (hi << 32) | lo0, (phi << 32) | plo)
                npair += 1
        c = rd(b + OFF_COUNT)
        if c != prev_c:
            lo = rd(b + OFF_TS_LO)
            hi = rd(b + OFF_TS_HI)
            if rd(b + OFF_COUNT) == c:
                prev_c = c
                beats[nbeat] = (now, (hi << 32) | lo)
                nbeat += 1
    pairs = pairs[:npair]
    beats = beats[:nbeat]
    t0 = min(pairs[0, 0] if npair else 0, beats[0, 0] if nbeat else 0)

    # PLLA: 40 ns steps on the pair register (the same test as the driver's
    # count_slips(), vectorised, and keeping the time of each slip)
    H = pairs[:, 1].astype(float)
    Pp = pairs[:, 2].astype(float)
    dh = np.diff(H)
    dp = np.diff(Pp)
    ok = dh > 0
    r0 = np.median(dp[ok] / dh[ok])
    clean = ok & (np.abs(dp - dh * r0) <= 2)
    r = dp[clean].sum() / dh[clean].sum()
    dev = dp - dh * r
    k = np.round(dev / 4.0)
    slip = (k != 0) & (np.abs(dev - 4 * k) <= 1.0) & (np.abs(dev) >= 1.5)
    other = (np.abs(dev) >= 1.5) & ~slip
    slip_t = (pairs[1:, 0][slip] - t0) / 1e9
    n_a = int(np.abs(k[slip]).sum())

    # HO's beat: the folded phase per window, and its jumps
    jumps, fracs = [], []
    if nbeat > 100:
        ph = (beats[:, 1].astype(float) % P_NULL) / P_NULL
        tb = (beats[:, 0] - t0) / 1e9
        prev = None
        for w in range(int(tb[-1] / WIN)):
            sel = (tb >= w * WIN) & (tb < (w + 1) * WIN)
            if sel.sum() < 10:
                continue
            h, _ = np.histogram(ph[sel], bins=50, range=(0, 1))
            top = (np.argmax(h) + 0.5) / 50
            fracs.append(np.sort(h)[-3:].sum() / float(sel.sum()))
            if prev is not None:
                d = (top - prev + 0.5) % 1 - 0.5
                if abs(d) > 0.1:
                    jumps.append(w * WIN)
            prev = top
    j_a = sum(1 for tj in jumps if np.any((slip_t >= tj - WIN) & (slip_t < tj + WIN)))
    span = (Pp[-1] - Pp[0]) / 1e8 if npair > 1 else seconds
    res = dict(seconds=span, plla_slips=n_a, plla_rate=n_a / span,
               other_steps=int(other.sum()), beat_jumps=len(jumps),
               jumps_with_plla=j_a, jumps_pllb=len(jumps) - j_a, beat_updates=nbeat,
               beat_clustered=float(np.median(fracs)) if fracs else 0.0,
               # Round 45: the helper's frequency against the PS clock, from the
               # same clean pairs -- the board's TCXO (through PLLA) against the
               # PYNQ's own crystal, which tells a TCXO hop from a PLLB one.
               helper_hz_ps=core.ps_clk_hz / r if np.isfinite(r) and r > 0 else float('nan'))
    if verbose:
        print('  %.1f s: PLLA %d slips (%.2f/s), %d other steps; HO beat on unit %d: '
              '%d updates, %.0f%% clustered per %.0f ms, %d jumps (%d with a PLLA '
              'slip, %d PLLB)'
              % (span, n_a, n_a / span, res['other_steps'], unit, nbeat,
                 100 * res['beat_clustered'], WIN * 1e3, len(jumps), j_a,
                 len(jumps) - j_a), flush=True)
    return res


DRIVE_ID = {2: 0, 4: 1, 6: 2, 8: 3}


def program(si, clk0_ma, clk1_ma):
    """The standard image with CLK0/CLK1 at the given drives (mA, or
    'off' for CLK1); waits for lock and settles."""
    from driver import F_HELPER
    from driver.i2c_devices import Si5351Config, REG_CLK_CTRL, CLK_PDN
    off1 = clk1_ma == 'off'

    class Cfg(Si5351Config):
        def registers(self):
            r = Si5351Config.registers(self)
            r[REG_CLK_CTRL] = (r[REG_CLK_CTRL] & ~3) | DRIVE_ID[clk0_ma]
            r[REG_CLK_CTRL + 1] = (CLK_PDN if off1 else
                                   (r[REG_CLK_CTRL + 1] & ~3) | DRIVE_ID[int(clk1_ma)])
            return r

        def oeb(self):
            return 0xFE if off1 else Si5351Config.oeb(self)

    si.program(Cfg(f_helper=F_HELPER))
    t0 = time.time()
    while time.time() - t0 < 1.0 and not si.lock_status():
        time.sleep(0.02)
    time.sleep(0.5)


def restore(si):
    from driver import F_HELPER
    from driver.i2c_devices import Si5351Config
    si.program(Si5351Config(f_helper=F_HELPER))
    time.sleep(1.0)
    print('put back the standard image: lock %s' % si.lock_status())


def sticky(si):
    s1 = si.read_reg(1)
    return 'sticky LOL_A %d LOL_B %d LOS_XTAL %d' % (s1 >> 5 & 1, s1 >> 6 & 1, s1 >> 3 & 1)


def main():
    import driver                                          # noqa: F401
    from driver import attach
    from driver.i2c_devices import PynqBus, Si5351
    from pynq import Overlay
    ol = Overlay(os.path.join(HERE, 'dmtd_top.bit'), download=False)
    core = attach(ol)
    si = Si5351(PynqBus(ol.axi_iic_0))
    args = sys.argv[1:]
    opts = {}
    for flag in ('--clk0', '--clk1'):
        if flag in args:
            i = args.index(flag)
            opts[flag] = args[i + 1]
            del args[i:i + 2]
    mode = args[0] if args else ''
    if mode == 'watch' and len(args) >= 2:
        seconds = float(args[1])
        unit = int(args[2]) if len(args) > 2 else 12
        if opts:
            d1 = opts.get('--clk1', '8')
            program(si, int(opts.get('--clk0', '2')), d1 if d1 == 'off' else int(d1))
        print('CLK0 %d mA, CLK1 %s as programmed; watching in 60 s chunks'
              % (2 * ((si.read_reg(16) & 3) + 1),
                 'off' if si.read_reg(17) & 0x80 else
                 '%d mA' % (2 * ((si.read_reg(17) & 3) + 1))), flush=True)
        si.write_reg(1, 0x00)
        tot = [0.0, 0, 0, 0, 0]
        lol_events = 0
        helper_ps = []
        left = seconds
        while left > 0:
            # Round 41: a UTC stamp and the chip's latched flags on EVERY
            # chunk, cleared as they are read, so a multi-day run logs when a
            # loss of lock happened as well as the slips round 40 showed the
            # flags themselves never see.
            print(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), end='')
            r = watch(core, min(60.0, left), unit)
            left -= 60.0
            s1 = si.read_reg(1)
            if s1 & 0x68:                              # LOL_B, LOL_A, LOS_XTAL
                lol_events += 1
                print('      LATCHED: %s' % sticky(si), flush=True)
                si.write_reg(1, 0x00)
            for i, key in enumerate(('seconds', 'plla_slips', 'other_steps',
                                     'beat_jumps', 'jumps_pllb')):
                tot[i] += r[key]
            helper_ps.append(r['helper_hz_ps'])
        print('TOTAL %.0f s: PLLA slips %d, other steps %d, HO-beat jumps %d '
              '(PLLB-only %d); chunks with a latched LOL/LOS flag: %d'
              % (tuple(tot) + (lol_events,)), flush=True)
        # its own line, after TOTAL, so that nothing parsing TOTAL changes
        print('HELPER %.4f Hz against the PS clock (mean of %d chunks)'
              % (float(np.nanmean(helper_ps)), len(helper_ps)), flush=True)
        if opts:
            restore(si)
    elif mode == 'matrix' and len(args) >= 2:
        seconds = float(args[1])
        trials = int(args[2]) if len(args) > 2 else 2
        unit = int(args[3]) if len(args) > 3 else 12
        for c0 in (2, 4, 8):
            for c1 in ('2', '4', '6', '8', 'off'):
                for _ in range(trials):
                    program(si, c0, c1 if c1 == 'off' else int(c1))
                    si.write_reg(1, 0x00)
                    print('CLK0 %d mA, CLK1 %-5s' % (c0, c1 if c1 == 'off' else c1 + ' mA'),
                          end='')
                    watch(core, seconds, unit)
                    print('      ' + sticky(si))
        restore(si)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()
