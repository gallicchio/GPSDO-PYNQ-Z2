#!/usr/bin/env python3
"""How well can each way of comparing 10 MHz references do, and over what tau?

    python3 floor_compare.py --ddmtd-npz FLOOR.npz [--rfsoc DIR] [--logs DIR]

Measured, not modelled, wherever there is a measurement:

  DDMTD (this board, rev A)    one source split to several channels -- the OCXO's
                               distribution amplifier on units 1, 2, 10, 11.
                               * short tau: a 300 s continuous recording, every
                                 beat transition (tau0 = 1/1234 Hz);
                               * long tau: the quiet overnight logs, one 20 s mean
                                 every ~120 s (N2 before the L1 strap, N3/N3b
                                 after it).
                               Pair 2-1 (and 11-10) share a rev A helper buffer:
                               that is rev B's case, one fan-out for all.  Pairs
                               across buffers (10-1 ...) are rev A's penalty.
  RFSoC 4x2 (DroneSDR)         its own null: one LBE-1421 split by a tee into
                               ADC_A and ADC_D, 10 MHz fundamental, 8.5 h outdoors
                               (sky-20260901), recomputed here from the raw 1 kHz
                               IQ dumps; and its 9th-harmonic night null from that
                               run's report (self-referenced, so a best case).
                               Plus three GPSDO pairs from the same day, which is
                               what these instruments are for.
  Analog DMTD (estimated)      double-balanced mixers against a common offset LO,
                               a low-noise IF amplifier, a 24-bit audio ADC and
                               IQ demodulation of the beat.  A noise model with
                               its numbers stated below: there is no such board
                               here to measure.

Writes floor_compare_adev.png, floor_compare_tdev.png and floor_compare.json
beside itself.  Paths are relative: the DroneSDR repository is expected at
../../../../radio/DroneSDR/GPSDO-comparison from here unless --rfsoc says
otherwise.
"""
import argparse, contextlib, csv, glob, io, json, math, os, sys

import numpy as np
import allantools as at

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "..", "..", "gateware", "board")
sys.path.insert(0, BOARD)
import beats as B          # noqa: E402
import xcheck as X         # noqa: E402

F0 = 10e6
# One bandwidth for every instrument's ADEV: phase averaged into 10 ms bins
# (f_H ~ 50 Hz).  White phase noise makes ADEV depend on the bandwidth, and the
# DDMTD (a raw 5 ps timestamp at every 1/1226 s transition) and the RFSoC (a
# phase already boxcar-averaged over 1 ms) do not share one natively.
TAU0 = 0.010


# ---------------------------------------------------------------------------
def taus_log(t0, tmax, per_decade=8):
    n = int(math.floor(math.log10(tmax / t0) * per_decade))
    return np.unique(np.round(t0 * 10 ** (np.arange(n + 1) / per_decade) / t0)) * t0


def binned(x, rate, tau0=TAU0):
    """Phase averaged into tau0 bins (the samples are uniform in time)."""
    k = max(1, int(round(tau0 * rate)))
    n = len(x) // k
    return x[:n * k].reshape(n, k).mean(axis=1), rate / k


def adev(x_s, rate, tmin=None, tmax=None, kind="oadev"):
    """Overlapping ADEV (or TDEV) of a phase series in seconds."""
    n = len(x_s)
    tmin = tmin or 1.0 / rate
    tmax = tmax or n / rate / 5.0          # keep at least ~5 averaging intervals
    t = taus_log(tmin, tmax)
    fn = at.oadev if kind == "oadev" else at.tdev
    tt, dev, err, ns = fn(x_s, rate=rate, data_type="phase", taus=t)
    keep = ns >= 3
    return tt[keep], dev[keep]


# ---------------------------------------------------------------------------
# DDMTD, short tau: one continuous recording, every transition
# ---------------------------------------------------------------------------
def ddmtd_units(npz):
    z = np.load(npz)
    h = float(z["helper_hz"][0])
    U = {}
    for k in z.files:
        if not k.startswith("unit"):
            continue
        with contextlib.redirect_stdout(io.StringIO()):
            a = B.analyse_unit(k, z[k], h, force=True)
            if "sel" in a:
                U[int(k[4:])] = X.unit(z, k, h, force=True)
    return U


def ddmtd_short(npz, pairs):
    U = ddmtd_units(npz)
    out = {}
    for a, b in pairs:
        if a not in U or b not in U:
            continue
        x_ps, host = X.pair_series(U[a], U[b])
        dt = np.diff(host) / 1e9
        rate = 1.0 / np.median(dt)
        gaps = int(np.sum(dt > 1.5 / rate))
        x = x_ps * 1e-12
        x = x - np.polyval(np.polyfit(np.arange(len(x)), x, 1), np.arange(len(x)))
        ta, da = adev(x, rate, kind="oadev")                # native, every transition
        xb, rb = binned(x, rate)
        tb, db = adev(xb, rb, kind="oadev")                 # 50 Hz bandwidth
        tt, dt_ = adev(x, rate, kind="tdev")
        out["%d-%d" % (a, b)] = dict(rate=rate, n=len(x), gaps=gaps,
                                     rms_ps_per_transition=float(np.std(x) * 1e12),
                                     adev_native=[ta.tolist(), da.tolist()],
                                     adev=[tb.tolist(), db.tolist()],
                                     tdev=[tt.tolist(), dt_.tolist()])
    return out


# ---------------------------------------------------------------------------
# DDMTD, long tau: the overnight logs, one 20 s mean per row
# ---------------------------------------------------------------------------
def ddmtd_log(logdir, pairs, heater_free=True):
    rows = list(csv.DictReader(open(os.path.join(logdir, "log.csv"))))
    t = np.array([float(r["unix"]) for r in rows])
    out = {}
    for a, b in pairs:
        k = "p%d_%d_ps" % (a, b)
        if k not in rows[0]:
            continue
        v = []
        for r in rows:
            try:
                v.append(float(r[k]))
            except (TypeError, ValueError):
                v.append(np.nan)
        v = np.array(v)
        ok = np.isfinite(v)
        if heater_free and "heater" in rows[0]:
            ok &= np.array([not (r.get("heater") or "").startswith("on") for r in rows])
        if ok.sum() < 12:
            continue
        tt, vv = t[ok], v[ok]
        step = float(np.median(np.diff(tt)))
        # onto a uniform grid (rows are ~120 s apart, a few late)
        grid = np.arange(tt[0], tt[-1], step)
        x = np.interp(grid, tt, vv) * 1e-12
        rate = 1.0 / step
        ta, da = adev(x, rate, tmax=len(x) * step / 3.0)
        tq, dq = adev(x, rate, tmax=len(x) * step / 3.0, kind="tdev")
        out["%d-%d" % (a, b)] = dict(hours=(tt[-1] - tt[0]) / 3600.0, step_s=step,
                                     adev=[ta.tolist(), da.tolist()],
                                     tdev=[tq.tolist(), dq.tolist()])
    return out


# ---------------------------------------------------------------------------
# RFSoC: the sky day's raw 1 kHz IQ dumps
# ---------------------------------------------------------------------------
def rfsoc_sky(rdir, pairs=(("ADC_A", "ADC_D"), ("ADC_A", "ADC_B"),
                           ("ADC_A", "ADC_C"), ("ADC_B", "ADC_C"))):
    log = os.path.join(rdir, "gpsdo-log")
    meta = json.load(open(os.path.join(log, "sky-20260901-meta.json")))
    port = meta["port_of_sma"]
    fref = meta["f_ref_hz"]["ADC_A"]
    rate = float(meta["dump_rate_hz"])
    files = sorted(glob.glob(os.path.join(log, "sky-20260901-0*.npz")))
    ph = {p: [] for p in pairs}
    seqs = []
    for f in files:
        z = np.load(f)
        iq = z["iq"].astype(np.float64)
        zc = iq[:, :, 0] + 1j * iq[:, :, 1]
        for a, b in pairs:
            d = zc[:, port[a]] * np.conj(zc[:, port[b]])
            ph[(a, b)].append(np.angle(d))
        seqs.append(z["seq"])
    out = {}
    for (a, b), parts in ph.items():
        p = np.unwrap(np.concatenate(parts))
        x = p / (2 * np.pi * fref)
        x = x - np.polyval(np.polyfit(np.arange(len(x)), x, 1), np.arange(len(x)))
        ta, da = adev(x, rate, tmin=1e-3, tmax=len(x) / rate / 3.0)
        xb, rb = binned(x, rate)
        tb, db = adev(xb, rb, tmax=len(x) / rate / 3.0)
        tq, dq = adev(x, rate, tmin=1e-3, tmax=len(x) / rate / 3.0, kind="tdev")
        out["%s-%s" % (a, b)] = dict(hours=len(x) / rate / 3600.0,
                                     adev_native=[ta.tolist(), da.tolist()],
                                     adev=[tb.tolist(), db.tolist()],
                                     tdev=[tq.tolist(), dq.tolist()])
    return out


# The 9th-harmonic night null, from DroneSDR analysis/20260830/report.txt
# (overlapping ADEV, 16.0 h indoors; self-referenced: the source also clocks
# the ADC, so this is the instrument's best case, not a typical one).
RFSOC_NIGHT = ([0.01, 1.0, 10.0, 107.0, 1112.0], [8.61e-12, 1.61e-13, 1.89e-14, 1.82e-15, 1.89e-16])


# ---------------------------------------------------------------------------
# Analog DMTD: mixers + IF amplifier + 24-bit audio ADC, a noise model
# ---------------------------------------------------------------------------
def analog_sim(white_dbc, flicker_dbc_1hz, tdev_1000s_ps, f_h=50.0, hours=60.0, seed=1):
    """An analog DMTD channel PAIR, simulated as a phase series and measured
    with the same estimators as the real data (so no closed-form subtleties).

    white PM   L(f) = white_dbc: the 24-bit ADC's dynamic range against a
               full-scale beat (the mixer at +7 dBm LO, and a 1 nV/rtHz IF
               amplifier, sit below it).
    flicker PM L(1 Hz) = flicker_dbc_1hz: the mixer diodes' and the IF
               amplifier's 1/f phase noise.
    wander     the two channels' differential delay drifting with the room
               (mixer and IF-filter group delay against temperature): a random
               walk in x, scaled to TDEV(1000 s) = tdev_1000s_ps.  That is the
               shape this board's own same-buffer pair showed through a night
               of heater steps (N1: TDEV 0.31 ps at 1000 s, 2.2 ps at 10^4 s,
               slope ~1/2), and a mixer's and an IF filter's delay drift with
               temperature no less than a gate's does: ~0.1-0.3 ps/K between
               channels, against this board's < 0.5 ps/K (N1).
    f_h        the phase estimate's bandwidth: samples at 2 f_h.
    Two channels, so every noise term enters twice."""
    rng = np.random.default_rng(seed)
    fs = 2 * f_h
    n = int(hours * 3600 * fs)
    k = 1.0 / (2 * np.pi * F0)                     # rad -> s
    s0 = 2 * 10 ** (white_dbc / 10.0) * k ** 2     # S_x, s^2/Hz (one-sided)
    s1 = 2 * 10 ** (flicker_dbc_1hz / 10.0) * k ** 2
    x = rng.standard_normal(n) * np.sqrt(2 * s0 * fs / 2)
    # flicker PM: shape white noise to S(f) = 2 s1 / f
    f = np.fft.rfftfreq(n, 1 / fs)
    w = np.fft.rfft(rng.standard_normal(n))
    shape = np.zeros_like(f)
    shape[1:] = np.sqrt(2 * s1 / f[1:] * fs / 2)
    x += np.fft.irfft(w * shape, n)
    # wander: a random walk in x, scaled so its own TDEV at 1000 s is the target
    rw = np.cumsum(rng.standard_normal(n))
    _, t1000 = adev(rw, fs, tmin=1000.0, tmax=1000.0, kind="tdev")
    x += rw * (tdev_1000s_ps * 1e-12 / t1000[0])
    ta, da = adev(x, fs, tmin=1.0 / fs, tmax=n / fs / 5)
    tt, dt_ = adev(x, fs, tmin=1.0 / fs, tmax=n / fs / 5, kind="tdev")
    return [ta.tolist(), da.tolist()], [tt.tolist(), dt_.tolist()]


ANALOG = {
    # the best a careful build could reach: AK5578-class ADC (121 dB DR), the
    # beat at full scale, Schottky DBMs at +7 dBm LO, a thermostatted box
    "best": dict(white_dbc=-160.0, flicker_dbc_1hz=-145.0, tdev_1000s_ps=0.1),
    # what a first build usually gets: LO coupling, ground loops, an untuned
    # IF chain: ~1e-13 at 1 s, the DroneSDR README's own estimate (R:1721-1733)
    "typical": dict(white_dbc=-145.0, flicker_dbc_1hz=-130.0, tdev_1000s_ps=0.3),
}


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ddmtd-npz", required=True)
    ap.add_argument("--logs", nargs="*", default=[])
    ap.add_argument("--rfsoc", default=os.path.join(HERE, "..", "..", "..", "..", "radio",
                                                    "DroneSDR", "GPSDO-comparison"))
    ap.add_argument("--json", default=os.path.join(HERE, "floor_compare.json"))
    a = ap.parse_args()
    pairs = ((2, 1), (11, 10), (10, 1), (11, 1), (10, 2), (11, 2))
    res = {"ddmtd_short": ddmtd_short(a.ddmtd_npz, pairs),
           "ddmtd_logs": {os.path.basename(os.path.normpath(d)): ddmtd_log(d, pairs) for d in a.logs},
           "rfsoc_night_report": RFSOC_NIGHT}
    if os.path.isdir(a.rfsoc):
        res["rfsoc_sky"] = rfsoc_sky(a.rfsoc)
    res["analog"] = {}
    for name, prm in ANALOG.items():
        ad, td = analog_sim(**prm)
        res["analog"][name] = dict(params=prm, adev=ad, tdev=td)
    json.dump(res, open(a.json, "w"))
    print("wrote", os.path.relpath(a.json))
    for k, v in res["ddmtd_short"].items():
        print("DDMTD %-6s %d samples at %.1f Hz, %d gaps, %.1f ps rms per transition"
              % (k, v["n"], v["rate"], v["gaps"], v["rms_ps_per_transition"]))


if __name__ == "__main__":
    main()
