#!/usr/bin/env python3
"""Put the GPSDO bench's 10 MHz sources into a known state, or out of it -- round 44.

Runs on the LAPTOP.  The wiring is BENCH_WIRING.md's; the instruments are driven
through lab-instrument-control ($LAB_INSTRUMENT_CONTROL or ~/lab-instrument-control).

    python3 bench_setup.py status       # read-only: what every source is doing
    python3 bench_setup.py on           # all sources: 10 MHz sine, 3.3 Vpp open circuit
    python3 bench_setup.py on --amp 2.5 # a lower amplitude (Vpp, open circuit)
    python3 bench_setup.py unit4 off    # the 33220A's output off: unit 4 undriven
    python3 bench_setup.py unit4 on
    python3 bench_setup.py off          # outputs off; the 33120A (no switch) to 0 V DC

The sources and where they go (BENCH_WIRING.md, section C):

    SDG1032X output 1  -> unit 1     (and scope CH1, through a tee)
    SDG1032X output 2  -> unit 2     (and scope CH2)
    33220A             -> unit 4     (and scope CH4): the switchable one
    HP 33120A          -> unit 11    (no output switch: 'off' is 0 V DC)
    (HO, the board's own CLK1 -> unit 12 and scope CH3; set by the PYNQ)

Every amplitude is set as an OPEN-CIRCUIT voltage (load setting high-Z / INF) and
capped at 3.3 Vpp: the rating of a board input without its 50R jumper.  With the
jumper fitted, the input sees about half.  Instruments that do not answer are
skipped and reported, so this works with part of the bench switched on.
"""
import os
import sys

LIC = os.environ.get('LAB_INSTRUMENT_CONTROL', os.path.expanduser('~/lab-instrument-control'))
for sub in ('siglent', 'hp'):
    sys.path.insert(0, os.path.join(LIC, sub))

F = 10e6
CAP_VPP = 3.3            # open circuit: the rating of an unterminated board input


def _try(name, fn):
    try:
        return fn()
    except Exception as e:                     # an instrument that is off or unplugged
        print('  %-10s not reached (%s)' % (name, str(e).splitlines()[0][:70]))
        return None


def sdg(action, amp):
    from siglent_SDG1032X import SDG1032X
    with SDG1032X(vlimit=CAP_VPP / 2) as g:
        if action == 'on':
            g.phase_locked(True)
            for ch in (1, 2):
                g.output(ch, load='HZ')            # amplitudes in open-circuit volts
                g.sine(ch, F, amp)                 # vlimit refuses more than the cap
                g.output(ch, on=True)
        elif action == 'off':
            for ch in (1, 2):
                g.output(ch, on=False)
        for ch in (1, 2):
            w, o = g.wave(ch), g.output_state(ch)
            print('  SDG out %d  %s %s Hz %s Vpp load %s, %s'
                  % (ch, w['type'], w.get('freq'), w.get('amp'), o['load'],
                     'ON' if o['on'] else 'off'))


def ag(action, amp):
    from agilent_33220A import Agilent33220A
    with Agilent33220A() as g:
        if action in ('on', 'unit4 on'):
            g.output(load='INF')
            g.sine(F, amp)
            g.output(on=True)
        elif action in ('off', 'unit4 off'):
            g.output(on=False)
        print('  33220A     %s' % g.status())


def hp(action, amp):
    from hp_33120A import HP33120A
    with HP33120A() as g:
        if action == 'on':
            g.output(load='INF')
            g.sine(F, amp)
        elif action == 'off':
            g.off()                                # no output switch: 0 V DC
        print('  33120A     %s' % g.status())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    amp = CAP_VPP
    if '--amp' in sys.argv:
        amp = float(sys.argv[sys.argv.index('--amp') + 1])
        args = [a for a in args if a != sys.argv[sys.argv.index('--amp') + 1]]
    if amp > CAP_VPP + 1e-9:
        raise SystemExit('%.2f Vpp is above the %.1f Vpp cap' % (amp, CAP_VPP))
    action = ' '.join(args) or 'status'
    if action not in ('status', 'on', 'off', 'unit4 on', 'unit4 off'):
        print(__doc__)
        return 2
    if action.startswith('unit4'):
        _try('33220A', lambda: ag(action, amp))
        return 0
    _try('SDG1032X', lambda: sdg(action, amp))
    _try('33220A', lambda: ag(action, amp))
    _try('HP 33120A', lambda: hp(action, amp))
    return 0


if __name__ == '__main__':
    sys.exit(main())
