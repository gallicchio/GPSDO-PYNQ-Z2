#!/usr/bin/env python3
"""Measure the Si5351's two 10 MHz outputs with an ADALM2000, from the bench.

    python3 m2k_beat.py                     # both channels, default 1 M sample
    python3 m2k_beat.py --uri ip:192.168.2.1 --samples 262144
    python3 m2k_beat.py --plot beat.png     # and draw what it saw

RUNS ON THE LAPTOP, not on the PYNQ: the M2k is on the laptop's USB, the
Si5351 is on the PYNQ's I2C, and this asks the one what the other did.

WHY THIS IS WORTH DOING.  The whole instrument rests on one claim -- that
CLK0 and CLK1 differ by exactly F_BEAT, because both PLLs lock to the same
crystal -- and until a front-end board exists there is nothing on the PYNQ
that can check it: the squarers and flip-flops that would make the beat are
on the board that has not been fabricated.  An M2k on CLK1 and CLK2 can
check it today.

WHAT IS AND IS NOT TRUSTWORTHY HERE.  The M2k samples on its own ~100 MHz
crystal, good to a few tens of ppm, so an ABSOLUTE frequency from it is worth
about +/-300 Hz at 10 MHz and proves only that the part is roughly where it
should be.  The DIFFERENCE between two channels captured into the SAME buffer
is referred to that same crystal in both, so it cancels to first order: the
beat is good to the edge-timing noise, not to the crystal.  That ratio --
f2 - f1 against f1 -- is the number this prints last, and it is the one that
means something.

    ./pynq-run bringup.py --no-heater --clk2 helper      # on the PYNQ
    python3 m2k_beat.py                                  # here

expects CLK1 = 10.000000 MHz, CLK2 = 10.0012344 MHz, 1234.4 Hz apart.
"""
import argparse
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # gateware/, for driver/
try:
    from driver.dmtd_constants import F_HELPER, F_SIGNAL, F_BEAT
except Exception:                                   # pragma: no cover
    F_SIGNAL, F_HELPER = 10e6, 10_001_234.4
    F_BEAT = F_HELPER - F_SIGNAL

ADC = 'm2k-adc'
FABRIC = 'm2k-fabric'


def open_scope(uri, rate, samples, chans=(0, 1)):
    """Both scope channels, at `rate`, with a buffer of `samples`."""
    import iio
    ctx = iio.Context(uri)
    adc = ctx.find_device(ADC)
    if adc is None:
        raise SystemExit('no %s in the context at %s -- is this an M2k?'
                         % (ADC, uri))
    # WAKE THE ANALOG FRONT END.  With nothing else driving the M2k, the
    # fabric leaves both input amplifiers powered down (`powerdown = 1`), and
    # a capture then returns four ADC counts of noise that look exactly like a
    # broken connection.  libm2k does this for you and Scopy does it through
    # libm2k, which is why this is invisible until you drive the device from
    # raw libiio -- as this does, so that it needs neither.
    #
    # The same device carries the per-channel input range: "high" is the
    # +/-2.5 V range and "low" the +/-25 V one (the fabric's names, not mine).
    # A 3.3 V CMOS clock is fine on either; "low" keeps it well inside the
    # ADC's range, and for a FREQUENCY measurement clipping would be harmless
    # anyway.
    fab = ctx.find_device(FABRIC)
    if fab is not None:
        for n in chans:
            ch = fab.find_channel('voltage%d' % n, False)
            if ch is None:
                continue
            for attr, val in (('powerdown', '0'), ('gain', 'low')):
                try:
                    ch.attrs[attr].value = val
                except Exception as e:
                    print('  (could not set ch%d %s: %s)' % (n + 1, attr, e))
        try:
            fab.attrs['clk_powerdown'].value = '0'
        except Exception:
            pass
        time.sleep(0.2)                      # the amplifiers need a moment
    try:
        adc.attrs['sampling_frequency'].value = str(int(rate))
    except Exception:
        pass
    got = int(float(adc.attrs['sampling_frequency'].value))
    for c in adc.channels:
        c.enabled = c.id in ['voltage%d' % n for n in chans]
    buf = iio.Buffer(adc, samples, False)
    return ctx, adc, buf, got


def read_block(adc, buf, chans=(0, 1)):
    """One buffer, as a list of lists of ints (raw ADC counts, signed 12-bit
    in a 16-bit word).  Raw is all a frequency measurement needs."""
    import array
    buf.refill()
    raw = array.array('h')
    raw.frombytes(bytes(buf.read()))
    n = len(chans)
    return [list(raw[i::n]) for i in range(n)]


def crossings(y, level=None):
    """Rising-edge crossing times, in samples, linearly interpolated.

    A clock is the easy case -- one crossing per cycle, big slew -- so linear
    interpolation between the two samples that straddle the level is good to
    far better than a sample, and the frequency estimate comes from a
    least-squares fit through the crossing INDEX, which uses every edge in
    the buffer rather than just the first and last.
    """
    if level is None:
        level = 0.5 * (max(y) + min(y))
    out = []
    prev = y[0]
    for i in range(1, len(y)):
        cur = y[i]
        if prev < level <= cur:
            out.append(i - 1 + (level - prev) / float(cur - prev))
        prev = cur
    return out


def fit_frequency(times, fs):
    """Least-squares slope of crossing time against crossing number -> Hz.

    Returns (hz, n_edges, residual_rms_samples).  The residual is the honest
    error bar: on a clean clock it is a small fraction of a sample, and if it
    is not, the 'frequency' below is not measuring a clock.
    """
    n = len(times)
    if n < 3:
        return 0.0, n, float('inf')
    xbar = (n - 1) / 2.0
    ybar = sum(times) / n
    sxx = sum((i - xbar) ** 2 for i in range(n))
    sxy = sum((i - xbar) * (times[i] - ybar) for i in range(n))
    slope = sxy / sxx                        # samples per cycle
    resid = [times[i] - (ybar + slope * (i - xbar)) for i in range(n)]
    rms = math.sqrt(sum(r * r for r in resid) / n)
    return (fs / slope if slope else 0.0), n, rms


def beat_from_phase(c1, c2, fs, f_nominal):
    """The beat, from the PHASE RAMP between the two channels.

    This is the measurement that is worth making, and it is a DDMTD done in
    software.  Subtracting two separately-fitted 10 MHz frequencies throws
    away everything the simultaneous capture bought: each one carries its own
    end-to-end timing error, and the difference of two ~0.3 ppm numbers is a
    ~0.3 ppm number -- 3 Hz of a 1234 Hz beat.

    The two channels are sampled by ONE ADC clock, so pair the crossings and
    the common error cancels.  What is left is

        delta_k = t2_k - t1_k = k (T2 - T1) + const

    a straight line whose slope is the period difference: -12.34 ps per cycle
    for this instrument, which over a 1.3 ms buffer is 160 ns of ramp -- 16
    whole samples, measured against a per-edge noise of 0.4 ns.

    The pairing slips, because that is the entire point: 160 ns is 1.6 cycles
    of 10 MHz, so `delta` wraps once or twice per buffer.  Consecutive
    crossings differ by 12 ps, so unwrapping is unambiguous.
    """
    n = min(len(c1), len(c2))
    if n < 100:
        return 0.0, 0.0, 0
    period = fs / f_nominal                       # samples per cycle
    d = [c2[k] - c1[k] for k in range(n)]
    # unwrap into a continuous ramp
    out, off = [d[0]], 0.0
    for k in range(1, n):
        step = d[k] + off - out[-1]
        while step > 0.5 * period:
            off -= period
            step -= period
        while step < -0.5 * period:
            off += period
            step += period
        out.append(d[k] + off)
    xbar = (n - 1) / 2.0
    ybar = sum(out) / n
    sxx = sum((k - xbar) ** 2 for k in range(n))
    sxy = sum((k - xbar) * (out[k] - ybar) for k in range(n))
    slope = sxy / sxx                             # samples of slip per cycle
    resid = [out[k] - (ybar + slope * (k - xbar)) for k in range(n)]
    rms = math.sqrt(sum(r * r for r in resid) / n)
    # slope is dT/dcycle in samples; T1 = period samples, T2 = period + slope
    # f2 - f1 = fs/(period+slope) - fs/period
    beat = fs / (period + slope) - fs / period
    return beat, rms, n


def main():
    ap = argparse.ArgumentParser(
        description='Measure the Si5351 outputs with an ADALM2000.')
    ap.add_argument('--uri', default='ip:192.168.2.1',
                    help='libiio URI of the M2k (default the USB gadget IP)')
    ap.add_argument('--rate', type=float, default=100e6, help='sample rate')
    ap.add_argument('--samples', type=int, default=1 << 18, help='per buffer')
    ap.add_argument('--blocks', type=int, default=4, help='buffers to average')
    ap.add_argument('--plot', default=None, help='write a PNG of the capture')
    a = ap.parse_args()

    ctx, adc, buf, fs = open_scope(a.uri, a.rate, a.samples)
    print('M2k    : %s' % ctx.attrs.get('hw_model', '?'))
    print('rate   : %.3f MS/s   buffer %d samples = %.3f ms   %d block(s)'
          % (fs / 1e6, a.samples, 1e3 * a.samples / fs, a.blocks))
    print('expect : CLK1 %.4f Hz, CLK2 %.4f Hz, %.1f Hz apart'
          % (F_SIGNAL, F_HELPER, F_BEAT))
    print()

    per, blocks = [[], []], []
    last = None
    for b in range(a.blocks):
        ch = read_block(adc, buf)
        last = ch
        blocks.append(ch)
        for i in (0, 1):
            y = ch[i]
            span = max(y) - min(y)
            hz, n, rms = fit_frequency(crossings(y), fs)
            per[i].append((hz, n, rms, span))
            print('  block %d  ch%d  %12.1f Hz   %5d edges   fit rms %.3f '
                  'samples   pp %d counts' % (b + 1, i + 1, hz, n, rms, span))
    print()

    # Is what we captured a CLOCK?  Two things say no, and both of them are
    # worth saying out loud rather than letting the arithmetic run on: a
    # signal that barely moves, and a crossing fit whose residual is a large
    # fraction of a cycle.  Round 29's lesson, in a different place: do not
    # print a confident number a better check would contradict.
    res, sane = [], True
    for i in (0, 1):
        hz = [p[0] for p in per[i]]
        mean = sum(hz) / len(hz)
        spread = (max(hz) - min(hz)) if len(hz) > 1 else 0.0
        span = per[i][0][3]
        rms = sum(p[2] for p in per[i]) / len(per[i])
        cycle = fs / mean if mean else float('inf')
        res.append(mean)
        print('  ch%d  %12.1f Hz  (block-to-block spread %.1f Hz)'
              % (i + 1, mean, spread))
        why = []
        if span < 200:
            why.append('only %d ADC counts peak-to-peak' % span)
        if rms > 0.05 * cycle:
            why.append('crossing fit residual %.0f samples is %.0f%% of a cycle'
                       % (rms, 100.0 * rms / cycle))
        if spread > max(50.0, 1e-5 * mean):
            why.append('block-to-block spread %.0f Hz' % spread)
        if why:
            sane = False
            print('       NOT A CLOCK: %s' % '; '.join(why))

    f1, f2 = res
    if not sane:
        print()
        print('  Refusing to report a beat: at least one channel is not')
        print('  carrying a clock.  Check that the PYNQ has programmed the')
        print('  Si5351 (./pynq-run bringup.py --no-heater --clk2 helper),')
        print('  that the module has 3.3 V, and that the M2k probes are on')
        print('  CLK1 and CLK2 with their grounds connected.')
        return 2
    print()
    print('  CLK1 vs its nominal : %+.1f Hz (%+.1f ppm) -- M2k crystal, '
          'worth +/-25 ppm' % (f1 - F_SIGNAL, 1e6 * (f1 - F_SIGNAL) / F_SIGNAL))
    print('  CLK2 vs its nominal : %+.1f Hz (%+.1f ppm)'
          % (f2 - F_HELPER, 1e6 * (f2 - F_HELPER) / F_HELPER))
    print()
    print('  difference of the two fits : %.2f Hz' % (f2 - f1))
    print('  -- the crude way: it carries both channels\' end-to-end timing')
    print('     error, so it is only as good as two separate 10 MHz fits.')
    print()
    print('  THE NUMBER THAT MEANS SOMETHING.  Both channels are sampled by')
    print('  one ADC clock, so their PHASE RAMP cancels it -- this is the')
    print('  DDMTD measurement itself, done in software on the raw capture:')
    beats = []
    for b, ch in enumerate(blocks):
        beat, rms, n = beat_from_phase(crossings(ch[0]), crossings(ch[1]),
                                       fs, F_SIGNAL)
        beats.append(beat)
        print('    block %d : %9.3f Hz   %5d paired edges   ramp fit rms '
              '%.3f samples (%.0f ps)' % (b + 1, beat, n, rms, rms * 1e12 / fs))
    beat = sum(beats) / len(beats)
    spread = (max(beats) - min(beats)) if len(beats) > 1 else 0.0
    print()
    print('    measured beat : %.3f Hz   (block-to-block spread %.3f Hz)'
          % (beat, spread))
    print('    by design      : %.3f Hz' % F_BEAT)
    print('    error          : %+.3f Hz (%+.1f ppm of the beat, '
          '%+.4f ppm of 10 MHz)'
          % (beat - F_BEAT, 1e6 * (beat - F_BEAT) / F_BEAT,
             1e6 * (beat - F_BEAT) / F_SIGNAL))
    print()
    print('    one helper cycle of beat displacement = %.4f ps of input phase'
          % (1e12 / F_HELPER / (F_SIGNAL / beat) if beat else 0.0))

    if a.plot and last:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(2, 1, figsize=(11, 6))
            n = min(400, len(last[0]))
            t = [1e9 * k / fs for k in range(n)]
            ax[0].plot(t, last[0][:n], lw=0.8, label='ch1 (CLK1)')
            ax[0].plot(t, last[1][:n], lw=0.8, label='ch2 (CLK2)')
            ax[0].set_xlabel('ns'); ax[0].set_ylabel('ADC counts')
            ax[0].legend(loc='upper right'); ax[0].grid(alpha=0.3)
            c1, c2 = crossings(last[0]), crossings(last[1])
            m = min(len(c1), len(c2))
            ax[1].plot([1e3 * c1[k] / fs for k in range(m)],
                       [1e9 * (c2[k] - c1[k]) / fs for k in range(m)], lw=0.9)
            ax[1].set_xlabel('ms into the capture')
            ax[1].set_ylabel('ch2 - ch1 edge (ns)')
            ax[1].set_title('one full ramp = one beat period = %.1f us'
                            % (1e6 / F_BEAT))
            ax[1].grid(alpha=0.3)
            fig.tight_layout(); fig.savefig(a.plot, dpi=110)
            print('\n  wrote %s' % a.plot)
        except Exception as e:
            print('\n  (no plot: %s)' % e)
    return 0


if __name__ == '__main__':
    sys.exit(main())
