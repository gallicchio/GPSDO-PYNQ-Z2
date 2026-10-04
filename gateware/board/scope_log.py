#!/usr/bin/env python3
"""Log the scope's own measurements, time-stamped, while you probe -- round 43.

Runs on the LAPTOP.  Read-only: it changes no setting on the scope.

    python3 scope_log.py 3600            # an hour, into scope_log_<UTC time>/
    python3 scope_log.py 3600 3 4        # only CH3 and CH4

Once a second it asks the SDS2104X Plus, over VXI-11, for frequency, peak-to-
peak, maximum, minimum, mean and rise time of every channel that is switched
on, and writes one CSV row per channel.  Every 20 s it saves a screenshot.
Probing a node shows up as a step in that channel's numbers, so the log also
records when a probe went on and came off -- which is what handbook test 4
(round 42) asks you to note by hand.

Turn a channel on, and set its probe factor (10x for the PP215), on the scope
itself; this script never does.
"""
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import siglent as S                                            # noqa: E402

ITEMS = ('FREQ', 'PKPK', 'MAX', 'MIN', 'MEAN', 'RISE')


def value(reply):
    """'C3:PAVA FREQ,5.571E+05Hz' -> 557100.0; '****' -> None."""
    try:
        return float(S._num(reply.split(',', 1)[1]))
    except (IndexError, TypeError, ValueError):
        return None


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 3600.0
    only = [int(a) for a in sys.argv[2:]] or [1, 2, 3, 4]
    out = os.path.join(HERE, 'scope_log_%s' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    os.makedirs(out)
    f = open(os.path.join(out, 'measurements.csv'), 'w', newline='')
    w = csv.writer(f)
    w.writerow(['utc', 'unix', 'ch'] + [i.lower() for i in ITEMS])
    t_end = time.time() + seconds
    next_shot = 0.0
    n = 0
    with S.connect('sds') as s:
        print('logging %s to %s for %.0f s (Ctrl-C to stop)' % (s.ident, out, seconds), flush=True)
        try:
            while time.time() < t_end:
                t0 = time.time()
                on = [c for c in only if s.query(':CHANnel%d:SWITch?' % c).upper() == 'ON']
                for c in on:
                    row = [value(s.query('C%d:PAVA? %s' % (c, item))) for item in ITEMS]
                    w.writerow([time.strftime('%H:%M:%S', time.gmtime(t0)), '%.2f' % t0, c] + row)
                f.flush()
                n += 1
                if on and t0 >= next_shot:
                    s.screenshot(os.path.join(out, 'screen_%s.png'
                                              % time.strftime('%H%M%S', time.gmtime(t0))))
                    next_shot = t0 + 20.0
                time.sleep(max(0.0, 1.0 - (time.time() - t0)))
        except KeyboardInterrupt:
            pass
    f.close()
    print('%d samples in %s' % (n, out))


if __name__ == '__main__':
    main()
