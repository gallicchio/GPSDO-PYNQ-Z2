#!/usr/bin/env python3
"""Put the GPSDO bench's sources into a known state -- the OCXO bench, round 45.19.

Runs on the LAPTOP.  The wiring is BENCH_WIRING_OCXO.md's; the instruments are
driven through lab-instrument-control ($LAB_INSTRUMENT_CONTROL or
~/lab-instrument-control).

    python3 bench_setup.py status       # read-only: every source, and the HPs' lock
    python3 bench_setup.py on           # units 4 and 9: 10 MHz sine, 2.94 Vpp open circuit
    python3 bench_setup.py on --amp 2.5 # another amplitude (Vpp, open circuit)
    python3 bench_setup.py unit4 off    # the top HP to 0 V DC: unit 4 undriven
    python3 bench_setup.py unit4 on
    python3 bench_setup.py unit9 off    # the same for the bottom HP and unit 9
    python3 bench_setup.py off          # both HPs to 0 V DC

The sources (BENCH_WIRING_OCXO.md, section 3):

    OCXO ports 1, 2, 5, 6 -> units 1, 2, 10, 11   (fixed; on scope CH1-CH4)
    top HP (RS-232)       -> unit 4   (JP401 fitted)
    bottom HP (RS-232)    -> unit 9   (JP901 off)
    HO, the board's CLK1  -> unit 12  (set by the PYNQ)
    right HP (GPIB 10), the SDG's outputs, the 33220A: not on the board

Both HPs take their 10 MHz reference from the OCXO.  Each amplitude is set as an
OPEN-CIRCUIT voltage (load setting INF) and capped at 3.3 Vpp, the rating of a
board input without its 50R jumper, so a cable on the wrong jack can't hurt
anything.  The 33120A has no output switch: 'off' is 0 V DC, which leaves the
input undriven (and still terminated by the generator's 50 ohm).  'on' and
'off' also switch the SDG's outputs and the 33220A's output off: nothing of
theirs is on the board.  Instruments that do not answer are skipped and
reported.
"""
import os
import sys

LIC = os.environ.get('LAB_INSTRUMENT_CONTROL', os.path.expanduser('~/lab-instrument-control'))
for sub in ('siglent', 'hp'):
    sys.path.insert(0, os.path.join(LIC, sub))

F = 10e6
CAP_VPP = 3.3            # open circuit: the rating of an unterminated board input
NOMINAL_VPP = 2.94       # 1 dB under the cap, so AM-to-PM can step +/-1 dB (O4)
HP_PORTS = {
    4: ('top HP', '/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A9WV8RTV-if00-port0'),
    9: ('bottom HP', '/dev/serial/by-id/usb-FTDI_USB_Serial_Converter_FTER3DQU-if00-port0'),
}


def _try(name, fn):
    try:
        return fn()
    except Exception as e:                     # an instrument that is off or unplugged
        print('  %-10s not reached (%s)' % (name, str(e).splitlines()[0][:70]))
        return None


def hp_unit(unit, action, amp=NOMINAL_VPP):
    """One of the RS-232 HPs: 'on' (10 MHz, amp Vpp open circuit), 'off'
    (0 V DC) or 'status'.  Returns its wave() and whether its phase lock held
    since the last look (Questionable Data bit 6 clear)."""
    from hp_33120A import HP33120A
    if amp > CAP_VPP + 1e-9:
        raise ValueError('%.2f Vpp is above the %.1f Vpp cap' % (amp, CAP_VPP))
    name, port = HP_PORTS[unit]
    with HP33120A(serial=port) as g:
        if action == 'on':
            g.output(load='INF')
            g.sine(F, amp)
        elif action == 'off':
            g.output(load='INF')
            g.off()
        ques = int(float(g.q('STATus:QUEStionable:EVENt?')))
        w = g.wave()
        locked = not ques & 64
        print('  %-10s unit %d: %s %s Hz %s Vpp (load %s, open circuit), offset %s; %s'
              % (name, unit, w['function'], w['freq'], w['vpp'], w['load'], w['offset'],
                 'locked' if locked else 'LOST LOCK since the last look (bit 6)'))
        return w, locked


def right_hp():
    from hp_33120A import HP33120A
    with HP33120A() as g:
        ques = int(float(g.q('STATus:QUEStionable:EVENt?')))
        print('  right HP   (not on the board) %s; %s'
              % (g.wave(), 'locked' if not ques & 64 else 'lock lost since the last look'))


def sdg(action):
    from siglent_SDG1032X import SDG1032X
    with SDG1032X() as g:
        if action in ('on', 'off'):
            for ch in (1, 2):
                g.output(ch, on=False)
        for ch in (1, 2):
            o = g.output_state(ch)
            print('  SDG out %d  %s (not on the board)' % (ch, 'ON' if o['on'] else 'off'))


def ag(action):
    from agilent_33220A import Agilent33220A
    with Agilent33220A() as g:
        if action in ('on', 'off'):
            g.output(on=False)
        print('  33220A     %s (not on the board)' % g.status())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    amp = NOMINAL_VPP
    if '--amp' in sys.argv:
        amp = float(sys.argv[sys.argv.index('--amp') + 1])
        args = [a for a in args if a != sys.argv[sys.argv.index('--amp') + 1]]
    if amp > CAP_VPP + 1e-9:
        raise SystemExit('%.2f Vpp is above the %.1f Vpp cap' % (amp, CAP_VPP))
    action = ' '.join(args) or 'status'
    units = {'unit4 on': (4, 'on'), 'unit4 off': (4, 'off'),
             'unit9 on': (9, 'on'), 'unit9 off': (9, 'off')}
    if action in units:
        u, a = units[action]
        _try(HP_PORTS[u][0], lambda: hp_unit(u, a, amp))
        return 0
    if action not in ('status', 'on', 'off'):
        print(__doc__)
        return 2
    for u in (4, 9):
        _try(HP_PORTS[u][0], lambda u=u: hp_unit(u, action, amp))
    _try('right HP', right_hp)
    _try('SDG1032X', lambda: sdg(action))
    _try('33220A', lambda: ag(action))
    return 0


if __name__ == '__main__':
    sys.exit(main())
