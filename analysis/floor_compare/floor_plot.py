#!/usr/bin/env python3
"""Plot floor_compare.json: the instruments' measurement floors against the
GPSDOs they exist to compare.

    python3 floor_plot.py            # writes floor_compare_adev.png, _tdev.png
    python3 floor_plot.py --table    # the README's two tables, from the same curves

ADEV panel: every instrument's phase averaged into 10 ms bins first (one
50 Hz bandwidth for all), so the floors compare like with like.  TDEV panel:
bandwidth-independent, in picoseconds, where the long-tau story is clearest.
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "floor_compare.json")))

C_DD, C_DDX, C_RF, C_AN, C_SIG = "#1f5fbf", "#8fa8d0", "#c0392b", "#2e8b57", "#333333"


def seg(curve, tmin=None, tmax=None):
    t, d = np.array(curve[0]), np.array(curve[1])
    k = np.ones_like(t, bool)
    if tmin:
        k &= t >= tmin
    if tmax:
        k &= t <= tmax
    return t[k], d[k]


def ddmtd_long(pair, key):
    """The long-tau DDMTD curve: N3b, the 14 h quiet night after the L1 strap
    (2026-10-09/10), or failing that the short quiet logs N3 and N2 before it.
    N1 (heater stepped) is drawn separately as the thermal case."""
    d = R["ddmtd_logs"].get("overnight_20261009T1714Z", {}).get(pair)
    if d:
        return [("overnight_20261009T1714Z", d)]
    out = []
    for name in ("overnight_20261009T1541Z", "overnight_20261009T1320Z"):
        d = R["ddmtd_logs"].get(name, {}).get(pair)
        if d:
            out.append((name, d))
    return out


def panel(ax, key, ylabel):
    # ---- the GPSDOs (RFSoC sky day): what the instruments are for ---------
    sky = R.get("rfsoc_sky", {})
    for k, lab in (("ADC_A-ADC_B", "GPSDO pair: LBE-1421 vs LBE-1421"),
                   ("ADC_B-ADC_C", "GPSDO pair: LBE-1421 vs TM-4")):
        if k in sky:
            t, d = seg(sky[k][key], tmin=0.01)
            if key == "tdev":
                d = d * 1e12
            ax.plot(t, d, color=C_SIG, lw=1.6, ls="-" if "LBE-1421 vs LBE" in lab else "--",
                    label=lab + " (RFSoC, measured)")
    # ---- RFSoC floors ---------------------------------------------------------
    if "ADC_A-ADC_D" in sky:
        t, d = seg(sky["ADC_A-ADC_D"][key], tmin=0.01)
        if key == "tdev":
            d = d * 1e12
        ax.plot(t, d, color=C_RF, lw=2.2, label="RFSoC 4x2 floor: one LBE split, 10 MHz, 8.5 h outdoors (4 ch)")
    if key == "adev":
        t, d = R["rfsoc_night_report"]
        ax.plot(t, d, color=C_RF, lw=1.4, ls=":", marker="o", ms=3,
                label="RFSoC floor, 9th harmonic, self-clocked, 16 h indoors (its report, 1 kHz)")
    # ---- DDMTD -------------------------------------------------------------
    sh = R["ddmtd_short"]
    for pair, col, lw, lab in (("2-1", C_DD, 2.6, "DDMTD (this board) floor: same helper buffer = rev B's case (13 ch)"),
                               ("10-1", C_DDX, 1.6, "DDMTD rev A, across helper buffers (fixed in rev B)")):
        # from 9.8 ms: twelve transitions to a 10 ms bin at 1226 Hz
        t, d = seg(sh[pair][key], tmin=0.0095)
        if key == "tdev":
            d = d * 1e12
        ax.plot(t, d, color=col, lw=lw, label=lab + ", 300 s")
        # the logs are 20 s means: at 50 Hz the white PM measured in the 300 s
        # recording is added back, so the long-tau ADEV shares the bandwidth
        tw, dw = seg(sh[pair]["adev"], tmin=0.1, tmax=10.0)
        a_w = float(np.median(dw * tw))
        first = True
        for name, dl in ddmtd_long(pair, key):
            t2, d2 = seg(dl[key], tmin=240.0)
            if key == "tdev":
                d2 = d2 * 1e12
            else:
                d2 = np.sqrt(d2 ** 2 + (a_w / t2) ** 2)
            ax.plot(t2, d2, color=col, lw=lw, ls="-" if first else "-.", marker="s", ms=3,
                    label=(lab.split(":")[0] + ", quiet night N3b (%.1f h)" % dl["hours"]) if first else None)
            first = False
        n1 = R["ddmtd_logs"].get("overnight_20261008T2322Z", {}).get(pair)
        if n1 and pair == "2-1":
            t3, d3 = seg(n1[key], tmin=240.0)
            if key == "tdev":
                d3 = d3 * 1e12
            else:
                d3 = np.sqrt(d3 ** 2 + (a_w / t3) ** 2)
            ax.plot(t3, d3, color=col, lw=1.0, ls=":", marker="^", ms=3,
                    label="DDMTD same buffer, N1: 13 h, heater stepped 4x (thermal case)")
    # ---- analog DMTD estimate -------------------------------------------------
    an = R.get("analog", {})
    if "best" in an and "typical" in an:
        tb, db = seg(an["best"][key], tmin=0.01)
        tt, dt = seg(an["typical"][key], tmin=0.01)
        if key == "tdev":
            db, dt = db * 1e12, dt * 1e12
        n = min(len(tb), len(tt))
        ax.fill_between(tb[:n], db[:n], dt[:n], color=C_AN, alpha=0.18, lw=0)
        ax.plot(tb, db, color=C_AN, lw=1.6, label="Analog DMTD (mixers + 24-bit audio ADC): ESTIMATE, careful build")
        ax.plot(tt, dt, color=C_AN, lw=1.2, ls="--", label="Analog DMTD: ESTIMATE, a typical first build")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("averaging time tau (s)")
    ax.set_ylabel(ylabel)
    ax.grid(True, which="both", alpha=0.25)
    ax.set_xlim(8e-3, 2e4)


# The README's tables, read off the plotted curves themselves: (row, the
# legend labels whose points make it up).  Where tau falls in the gap between
# the 300 s recording (to ~50 s) and a log's first point (240 s), the value is
# interpolated across it and marked "~".
TABLE_TAUS = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0, 3600.0, 10000.0)
TABLE_ROWS = (
    ("DDMTD, same buffer (rev B's case)", ("same helper buffer = rev B", "floor, quiet night")),
    ("DDMTD, across buffers (rev A)", ("across helper buffers (fixed in rev B), 300 s",
                                       "across helper buffers (fixed in rev B), quiet night")),
    ("DDMTD, same buffer, N1 (heater stepped)", ("N1: 13 h",)),
    ("RFSoC null, 10 MHz, outdoors", ("RFSoC 4x2 floor",)),
    ("RFSoC null, 9th harmonic, indoors (report, 1 kHz)", ("9th harmonic",)),
    ("Analog DMTD, estimate: careful build", ("ESTIMATE, careful build",)),
    ("Analog DMTD, estimate: typical first build", ("ESTIMATE, a typical first build",)),
    ("GPSDO pair: LBE-1421 vs LBE-1421", ("LBE-1421 vs LBE-1421",)),
    ("GPSDO pair: LBE-1421 vs TM-4", ("LBE-1421 vs TM-4",)),
)


def table(ax, key):
    lines = [(l.get_label(), np.asarray(l.get_xdata(), float), np.asarray(l.get_ydata(), float))
             for l in ax.get_lines()]
    fmt = (lambda v: "%.2g" % v) if key == "tdev" else (lambda v: "%.1e" % v)
    out = ["| tau (s) | " + " | ".join("%g" % t for t in TABLE_TAUS) + " |",
           "|---" * (len(TABLE_TAUS) + 1) + "|"]
    for row, parts in TABLE_ROWS:
        t = np.concatenate([x for lab, x, y in lines if any(p in lab for p in parts)] or [[]])
        d = np.concatenate([y for lab, x, y in lines if any(p in lab for p in parts)] or [[]])
        if not len(t):
            continue
        o = np.argsort(t)
        t, d = t[o], d[o]
        cells = []
        for tau in TABLE_TAUS:
            if tau < t[0] / 1.1 or tau > t[-1] * 1.1:          # within 10% of an end
                cells.append("")
                continue
            v = float(np.exp(np.interp(np.log(tau), np.log(t), np.log(d))))
            i = int(np.searchsorted(t, tau))
            on_point = np.min(np.abs(np.log(t / tau))) < 0.02
            gap = not on_point and 0 < i < len(t) and t[i] / t[i - 1] > 2.5
            cells.append(("~" if gap else "") + fmt(v))
        out.append("| %s | %s |" % (row, " | ".join(cells)))
    return "\n".join(out)


def main():
    if "--table" in sys.argv:
        for key in ("adev", "tdev"):
            fig, ax = plt.subplots()
            panel(ax, key, "")
            print(key.upper() + (" (ps)" if key == "tdev" else ", 50 Hz bandwidth"))
            print(table(ax, key))
            print()
        return
    for key, ylabel, fn, ylim in (
            ("adev", "Allan deviation  sigma_y(tau)   [phase averaged to 10 ms: 50 Hz bandwidth]",
             "floor_compare_adev.png", (1e-17, 3e-9)),
            ("tdev", "time deviation  TDEV(tau)  (ps)", "floor_compare_tdev.png", (5e-3, 3e5))):
        fig, ax = plt.subplots(figsize=(12.5, 8.2))
        panel(ax, key, ylabel)
        ax.set_ylim(*ylim)
        ax.set_title("Comparing 10 MHz references: each instrument's own floor (one source split), "
                     "against GPSDO pairs it measured\n(DDMTD: this board, rev A, 2026-10-09/10; "
                     "RFSoC: DroneSDR GPSDO-comparison, 2026-09-01; analog: a noise model)",
                     fontsize=11)
        ax.legend(fontsize=8.3, loc="lower left" if key == "adev" else "upper left", framealpha=0.92)
        fig.tight_layout()
        out = os.path.join(HERE, fn)
        fig.savefig(out, dpi=120)
        print("wrote", os.path.relpath(out))


if __name__ == "__main__":
    main()
