#!/usr/bin/env python3
"""The DDMTD against the bench: generator settings, scope, PYNQ -- round 43.

Runs on the LAPTOP.  The SDG1032X's two outputs each go through a splitter to
a scope channel and to a board input: output 1 -> unit 1 and scope CH1,
output 2 -> unit 2 and scope CH2.  Each experiment makes ONE recording of
units 1 and 2 on the PYNQ while it changes output 2 at logged moments, then
puts the generator back exactly as it found it.

    python3 xcheck.py steps [deg ...]   # output 2's phase, 3 s per setting
    python3 xcheck.py ramp [df] [s]     # output 2 at 10 MHz + df (0.05 Hz)
    python3 xcheck.py amp [Vpp ...]     # output 2's amplitude, open circuit
    python3 xcheck.py analyse DIR       # analyse a saved run again

    --scope   also capture CH1/CH2 at each setting and fit their phases
    --ch1     amp: change output 1 (unit 1) instead of output 2

What each one checks:

  steps  a phase step of x degrees is x/360 x 100 ns of input time.  The
         DDMTD's unit 1 - unit 2 difference must move by exactly that: the
         ps-per-helper-cycle scale (REVB_CHANGES item 17) and its sign.
  ramp   a frequency offset df slides unit 2 through the whole 100 ns at a
         known rate, df/f.  The slope checks the scale to a few ppm; the
         residual shows any non-linearity across the range, and a tone at
         df is the crosstalk between the two channels (round 41's method).
  amp    the input's amplitude must not move its timing; whatever it does is
         the squarer's AM-to-PM, in ps per dB.

The PYNQ is reached with $PYNQ_SSH and $PYNQ_SCP (default `ssh`/`scp` as
$PYNQ_HOST, xilinx@192.168.8.156) in $PYNQ_DIR (~/gpsdo-dmtd).  Each run is
saved under xcheck_<UTC time>/ beside this file: the recording, the events,
the results.

The instruments are driven through lab-instrument-control (round 44:
QuantumQuasars/lab-instrument-control, at $LAB_INSTRUMENT_CONTROL or
~/lab-instrument-control).  The board's own limits are kept here:

  * the generator's open-circuit swing stays at or below 3.3 Vpp, the rated
    maximum of an input without its 50R jumper (driver vlimit, 1.65 V peak);
  * only an output already running a SINE is touched, and only its
    frequency (within 0.1 % of 10 MHz), amplitude and phase -- never its
    LOAD (the same number would then mean other volts), waveform or on/off;
  * both outputs are put back exactly as found, and the scope is left
    running or stopped as found.
"""
import contextlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import beats as B                                              # noqa: E402

LIC = os.environ.get('LAB_INSTRUMENT_CONTROL',
                     os.path.expanduser('~/lab-instrument-control'))
sys.path.insert(0, os.path.join(LIC, 'siglent'))
from siglent_SDG1032X import SDG1032X                          # noqa: E402
from siglent_SDS2104X import SDS2104X                          # noqa: E402

PYNQ = os.environ.get('PYNQ_HOST', 'xilinx@192.168.8.156')
SSH = shlex.split(os.environ.get('PYNQ_SSH', 'ssh ' + PYNQ))
SCP = shlex.split(os.environ.get('PYNQ_SCP', 'scp'))
RDIR = os.environ.get('PYNQ_DIR', 'gpsdo-dmtd')
SETTLE = 0.4         # s ignored after each change
START = 1.0          # s of recording before the first change
BOARD_VPEAK = 1.65   # V peak open circuit: 3.3 Vpp, the board's rated maximum


class Generator:
    """The SDG1032X, with the board's rules on top of the driver's."""

    def __init__(self):
        self.g = SDG1032X(vlimit=BOARD_VPEAK)

    def close(self):
        self.g.close()

    KEYS = (('freq', 'FRQ'), ('amp', 'AMP'), ('offset', 'OFST'), ('phase', 'PHSE'))

    def snapshot(self, ch):
        """What restore() needs.  A DC output has only an offset, so absent
        settings are None."""
        w = self.g.wave(ch)
        snap = {k: w.get(k) for k, _ in self.KEYS}
        snap.update(type=w['type'], load=self.g.output_state(ch)['load'])
        return snap

    def set(self, ch, freq=None, amp=None, phase=None):
        """Change a running SINE's frequency (Hz), amplitude (Vpp as the
        generator states it) or phase (degrees); returns the read-back."""
        w = self.g.wave(ch)
        if w['type'] != 'SINE':
            raise ValueError('output %d is %s, not SINE: not touching it' % (ch, w['type']))
        if freq is not None and not 9.99e6 <= freq <= 10.01e6:
            raise ValueError('%.3f Hz is not within 0.1 %% of 10 MHz' % freq)
        params = {}
        if freq is not None:
            params['FRQ'] = '%.6f' % freq
        if amp is not None:
            params['AMP'] = '%.4f' % amp
        if phase is not None:
            params['PHSE'] = '%.3f' % phase
        w = self.g.set_wave(ch, **params)       # the driver refuses > BOARD_VPEAK
        return dict(freq=w['freq'], amp=w['amp'], phase=w['phase'])

    def restore(self, ch, snap):
        """Put a snapshot back: the one way to write more than the cap, since
        it was the setting found (round 43 found both outputs at 4 Vpp)."""
        now = self.snapshot(ch)
        if now['type'] != snap['type'] or now['load'] != snap['load']:
            raise ValueError('output %d changed under us: %s -> %s' % (ch, snap, now))
        params = {scpi: ('%.6f' % snap[k] if k == 'freq' else snap[k])
                  for k, scpi in self.KEYS if snap[k] is not None}
        self.g.vlimit = None
        try:
            self.g.set_wave(ch, **params)
        finally:
            self.g.vlimit = BOARD_VPEAK
        back = self.snapshot(ch)
        if any(snap[k] is not None and abs(back[k] - snap[k]) > 1e-9 for k, _ in self.KEYS):
            raise IOError('output %d did not restore: %s -> %s' % (ch, snap, back))
        return back


def ntp_synced():
    """Both clocks must be NTP-disciplined: the events are placed in the
    recording by wall-clock time.  (Round 43: estimating the offset from one
    ssh round trip was 1.2 s wrong, because the login is most of the trip
    and comes before the remote clock is read.)"""
    here = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized'],
                          capture_output=True, text=True).stdout.strip()
    there = subprocess.run(SSH + ['timedatectl show -p NTPSynchronized'],
                           capture_output=True, text=True, timeout=60).stdout.strip()
    return here.endswith('yes') and there.endswith('yes'), here, there


def run(kind, plan, scope=False, df=None, ch=2):
    """plan: list of (seconds, {set() keywords}) applied to output `ch`."""
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    out = os.path.join(HERE, 'xcheck_%s_%s' % (kind, stamp))
    os.makedirs(out)
    ok, here, there = ntp_synced()
    if not ok:
        raise SystemExit('clocks not both NTP-synchronized (laptop %r, PYNQ %r)'
                         % (here, there))
    off = 0.0
    total = START + sum(p[0] for p in plan) + 3.0
    rec = subprocess.Popen(SSH + ['cd %s && ./pynq-run beats.py record %.1f 1 2 2>&1'
                                  % (RDIR, total)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    head = []
    for line in rec.stdout:                  # wait until it is really polling
        head.append(line)
        if 'recording from' in line:      # after sudo's prompt, no newline
            break
    else:
        raise IOError('the recording never started:\n' + ''.join(head))
    events = []
    g = Generator()
    sds = SDS2104X() if scope else None
    sds_stopped = sds and sds.q(':TRIGger:STATus?').endswith('Stop')
    snap = {c: g.snapshot(c) for c in (1, 2)}
    try:
        time.sleep(START)
        for seconds, kw in plan:
            # the change lands somewhere between these two: set() writes,
            # waits 0.15 s and reads back
            t_before = time.time()
            c = g.set(ch, **kw)
            t = time.time()
            ev = dict(t_before=t_before, t_laptop=t, t_pynq=t + off, set=kw,
                      readback=c)
            print('  %s  output %d: %.6f Hz, %.3f Vpp, %.2f deg'
                  % (time.strftime('%H:%M:%S'), ch, c['freq'], c['amp'], c['phase']))
            if sds:
                time.sleep(SETTLE)
                ev['scope'] = scope_phase(sds)
                print('      scope: CH2 - CH1 %+.3f ns, %.3f / %.3f Vpp'
                      % (ev['scope']['dt_ns'], ev['scope']['vpp1'], ev['scope']['vpp2']))
                time.sleep(max(0.0, seconds - SETTLE - 1.0))
            else:
                time.sleep(seconds)
            events.append(ev)
        t_plan_end = time.time()       # the restore below must not count
    finally:
        for out_ch in (1, 2):              # not `ch`: that names the experiment's
            g.restore(out_ch, snap[out_ch])  # output, and is saved below
        g.close()
        if sds:
            if sds_stopped:
                sds.stop()                 # as it was found
            sds.close()
        print('generator restored')
    log = ''.join(head) + rec.communicate(timeout=total + 120)[0]
    remote = [w for w in log.split() if w.endswith('.npz')]
    if rec.returncode or not remote:
        raise IOError('recording failed:\n' + log)
    local = os.path.join(out, 'beats.npz')
    subprocess.run(SCP + ['%s:%s' % (PYNQ, remote[-1]), local], check=True,
                   timeout=120)
    # the file name only: a committed record names no place on any machine
    # (CLAUDE_PCB.md section 2), and this one is the PYNQ's home directory
    log = re.sub(r'(?<!\S)/\S*/([^/\s]+\.npz)', r'\1', log)
    meta = dict(kind=kind, df=df, ch=ch, plan=plan, events=events,
                clock_offset=off, t_plan_end=t_plan_end, recording_log=log,
                snapshot=snap)
    with open(os.path.join(out, 'events.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    print('saved %s' % out)
    analyse(out)


def scope_phase(sds):
    """CH2 minus CH1 at 10 MHz, by a sine fit to one complete, fresh acquisition.

    acquire_now() forces one record, so both channels come from the same
    instant and the record is whole.  (Round 44: running briefly and stopping
    can leave no record at all on a slow timebase; the library now says so.)
    The trigger mode and run state are put back as found."""
    mode = sds.q(':TRIGger:MODE?')
    running = not sds.q(':TRIGger:STATus?').endswith('Stop')
    try:
        sds.acquire_now()
        fits = []
        for ch in (1, 2):
            t, v, _ = sds.waveform(ch)
            A = np.vstack([np.sin(2 * np.pi * 1e7 * t), np.cos(2 * np.pi * 1e7 * t),
                           np.ones_like(t)]).T
            c = np.linalg.lstsq(A, v, rcond=None)[0]
            fits.append((np.hypot(c[0], c[1]), np.arctan2(c[1], c[0])))
    finally:
        if mode not in ('STOP', 'FTRIG'):
            sds.w(':TRIGger:MODE %s' % mode)
        if running:
            sds.run()
        else:
            sds.stop()
    d = (fits[1][1] - fits[0][1] + np.pi) % (2 * np.pi) - np.pi
    # a phase LEAD of CH2 is an earlier waveform: CH2 - CH1 in time is -d/w
    return dict(dt_ns=-d / (2 * np.pi * 1e7) * 1e9, vpp1=2 * fits[0][0],
                vpp2=2 * fits[1][0])


# ---------------------------------------------------------------------------
def unit(z, name, helper, force=False):
    with contextlib.redirect_stdout(io.StringIO()):
        a = B.analyse_unit(name, z[name], helper, force=force)
    if not a.get('beat') and not (force and 'sel' in a):
        raise ValueError('%s is not a beat in this recording' % name)
    last, _, host = B.bursts(z[name])
    sel = a['sel']
    return dict(P=a['P'], ps=a['ps_per_cycle'], l=last[sel], host=host[sel])


def cycle_index(l, P):
    """Each transition's beat-cycle number, counted gap by gap, so that a
    missed transition or a source wandering against the helper cannot slip
    it.  (Round 40: the Siglent wanders ~15 % of a beat period in 0.2 s.)"""
    n = np.zeros(len(l))
    n[1:] = np.cumsum(np.round(np.diff(l) / P))
    return n


def pair_series(a, b):
    """Unit a minus unit b as input time, ps, at each of a's rising
    transitions, with that transition's PYNQ host time.

    Unit b's beat-cycle count is interpolated at a's transitions.  One beat
    cycle of relative displacement is one 10 MHz cycle, 100 ns, exactly
    (design.py), so this needs no ps-per-helper-cycle constant, has no
    wrap-around, and the generator's wander, common to both, cancels.  A
    DELAY of unit b's input makes its beat transitions EARLIER, so a - b
    rises by that delay: the convention of beats.py's d = la - lb."""
    na, nb = cycle_index(a['l'], a['P']), cycle_index(b['l'], b['P'])
    ok = (a['l'] >= b['l'][0]) & (a['l'] <= b['l'][-1])
    x = np.interp(a['l'][ok], b['l'], nb) - na[ok]
    x -= np.round(np.median(x[:200]))
    return x * 1e5, a['host'][ok]


def analyse(out):
    meta = json.load(open(os.path.join(out, 'events.json')))
    z = np.load(os.path.join(out, 'beats.npz'))
    helper = float(z['helper_hz'][0])
    u1, u2 = unit(z, 'unit1', helper), unit(z, 'unit2', helper)
    tau, host = pair_series(u1, u2)
    tw = float(z['wall0'][0]) + (host - int(z['mono0'][0])) / 1e9
    ev = meta['events']
    lines = ['%s, %s: helper %.3f Hz; beat periods %.3f and %.3f helper cycles, '
             'so %.4f ps of input per helper cycle today (design %.4f); '
             '%d pairs' % (meta['kind'], os.path.basename(out), helper, u1['P'],
                           u2['P'], u1['ps'], 1e5 / (B.F_HELPER_NOM / (B.F_HELPER_NOM - 1e7)),
                           len(tau))]
    res = dict(helper=helper, P1=u1['P'], P2=u2['P'], ps_per_cycle=u1['ps'])
    if meta['kind'] in ('steps', 'amp'):
        rows = []
        for i, e in enumerate(ev):
            t0 = e['t_pynq'] + SETTLE
            # end before the next change can land (round 43: ending 0.1 s
            # before the next event's logged time, which is after its set()
            # returned, let 2 % of the next setting in)
            if i + 1 < len(ev):
                nxt = ev[i + 1].get('t_before', ev[i + 1]['t_laptop'] - 0.3)
            else:
                nxt = meta.get('t_plan_end', tw[-1] + 0.05)
            t1 = nxt - 0.05
            s = (tw >= t0) & (tw < t1)
            if s.sum() < 50:
                continue
            row = dict(set=e['set'], readback=e['readback'], n=int(s.sum()),
                       mean_ps=float(tau[s].mean()), rms_ps=float(tau[s].std()))
            if 'scope' in e:
                row['scope_dt_ns'] = e['scope']['dt_ns']
                row['scope_vpp'] = [e['scope']['vpp1'], e['scope']['vpp2']]
            rows.append(row)
        res['segments'] = rows
        if meta['kind'] == 'steps':
            ph = np.array([_rb(r, 'phase') for r in rows])
            m = np.array([r['mean_ps'] for r in rows]) / 1e3
            want = ph / 360.0 * 100.0                  # the setting, as ns
            k, c = np.polyfit(want, m, 1)
            res.update(slope=k, offset_ns=c, resid_ps=list((m - (k * want + c)) * 1e3))
            lines.append('  phase deg   setting as ns   unit1-unit2 ns    rms ps   '
                         'fit resid ps' + ('   scope CH2-CH1 ns' if 'scope_dt_ns' in rows[0] else ''))
            for r, p, w, mm, rr in zip(rows, ph, want, m, res['resid_ps']):
                lines.append('  %8.2f   %14.3f   %14.4f   %7.1f   %10.1f%s'
                             % (p, w, mm, r['rms_ps'], rr,
                                ('   %15.3f' % r['scope_dt_ns']) if 'scope_dt_ns' in r else ''))
            lines.append('  slope %+.6f: unit 1 - unit 2 moves by that times the '
                         'setting.  -1 means a positive phase ADVANCES output 2 '
                         '(a delay of unit 2 raises unit 1 - unit 2)' % k)
        else:
            # The generator's own delay moves with its amplitude range
            # (round 43: -1.56 ns at 1.6 V and below, on output 2).  The scope
            # sees that at the generator, before the board, so the board's
            # own part is the DDMTD minus the scope.
            ch = meta.get('ch', 2)
            m = np.array([r['mean_ps'] for r in rows])
            if 'scope_dt_ns' in rows[0]:
                vpp = np.array([r['scope_vpp'][ch - 1] for r in rows])
                board = m - np.array([r['scope_dt_ns'] for r in rows]) * 1e3
            else:
                vpp = np.array([_rb(r, 'amp') for r in rows])
                board = m
            sign = 1.0 if ch == 2 else -1.0          # a delay of unit `ch`
            delay = sign * (board - board[0])
            db = 20 * np.log10(vpp / vpp.max())
            k, c = np.polyfit(db, delay, 1)
            res.update(ps_per_db=k, ch=ch)
            lines.append('  output %d   Vpp at the scope   dB      unit1-unit2 ps   '
                         'scope CH2-CH1 ns   unit %d delay change ps   rms ps' % (ch, ch))
            for r, v_, d_, mm, dl in zip(rows, vpp, db, m, delay):
                lines.append('  %7.3fV   %16.3f   %6.2f   %14.1f   %16s   %21.1f   %6.1f'
                             % (_rb(r, 'amp'), v_, d_, mm,
                                ('%+.4f' % r['scope_dt_ns']) if 'scope_dt_ns' in r else '-',
                                dl, r['rms_ps']))
            lines.append('  AM-to-PM of unit %d: %+.1f ps of delay per dB of amplitude '
                         '(negative: the delay grows as the input shrinks)' % (ch, k))
    else:                                                       # ramp
        t0 = ev[0]['t_pynq'] + SETTLE
        t1 = (ev[1].get('t_before', ev[1]['t_laptop'] - 0.3) - 0.05) if len(ev) > 1 else tw[-1]
        s = (tw >= t0) & (tw < t1)
        t = tw[s] - tw[s][0]
        y = tau[s]
        k, c = np.polyfit(t, y, 1)
        df = meta['df']
        # output 2 higher by df advances at df cycles a second: its delay
        # falls by df/f seconds per second, and so does unit 1 - unit 2
        want = -df / 1e7 * 1e12                                 # ps per s
        r = y - (k * t + c)
        # crosstalk: a tone at df in the residual
        A = np.vstack([np.sin(2 * np.pi * df * t), np.cos(2 * np.pi * df * t)]).T
        cs = np.linalg.lstsq(A, r, rcond=None)[0]
        tone = float(np.hypot(*cs))
        res.update(slope_ps_per_s=k, want_ps_per_s=want, ratio=k / want,
                   resid_rms_ps=float(r.std()), tone_at_df_ps=tone,
                   seconds=float(t[-1]))
        lines.append('  ramp over %.1f s: slope %.3f ps/s, expected %+.3f (df/f): '
                     'ratio %.6f' % (t[-1], k, want, k / want))
        lines.append('  residual %.1f ps rms; a tone at df = %.3f Hz of %.1f ps '
                     '(crosstalk between the channels, both ways, with the '
                     'generator\'s own)' % (r.std(), df, tone))
    print('\n'.join(lines))
    with open(os.path.join(out, 'results.json'), 'w') as f:
        json.dump(res, f, indent=1, default=float)
    with open(os.path.join(out, 'results.txt'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return res


def _rb(row, key):
    """A read-back setting, from round 44's numbers or round 43's strings
    ('10000000HZ', '4V', '0'), so old runs still analyse."""
    rb = row['readback']
    if key in rb:
        return float(rb[key])
    old = str(rb[{'freq': 'FRQ', 'amp': 'AMP', 'phase': 'PHSE'}[key]])
    return float(re.match(r'[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?', old).group(0))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    scope = '--scope' in sys.argv
    ch = 1 if '--ch1' in sys.argv else 2
    if not args:
        print(__doc__)
        return 2
    kind, rest = args[0], [float(a) for a in args[1:]] if args[0] != 'analyse' else args[1:]
    if kind == 'steps':
        degs = rest or [0, 20, 40, 60, 40, 20, 0, -20, -40, -60, -40, -20, 0]
        run('steps', [(3.0, dict(phase=d)) for d in degs], scope)
    elif kind == 'ramp':
        df = rest[0] if rest else 0.05
        secs = rest[1] if len(rest) > 1 else 45.0
        run('ramp', [(secs, dict(freq=1e7 + df)), (2.0, dict(freq=1e7))], scope=False,
            df=df)
    elif kind == 'amp':
        amps = rest or [3.3, 2.6, 2.0, 1.6, 1.25, 1.6, 2.0, 2.6, 3.3]
        run('amp', [(3.0, dict(amp=a)) for a in amps], scope, ch=ch)
    elif kind == 'analyse':
        analyse(rest[0])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
