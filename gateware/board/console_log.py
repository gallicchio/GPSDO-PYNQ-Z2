#!/usr/bin/env python3
"""Log the PYNQ-Z2's serial console, across resets and re-enumerations.

    python3 console_log.py                      # -> pynq-console.log
    python3 console_log.py --port /dev/ttyUSB1 --out /tmp/pynq.log

RUNS ON THE LAPTOP.  Leave it running during a long bring-up: if the board
resets you get the boot, and if it does not come back you get whatever it said
on the way down, which is the one diagnostic this setup otherwise has none of.

WHICH PORT.  On this bench the Xilinx/TUL FT2232 presents two interfaces --
`/dev/ttyUSB0` is its JTAG and `/dev/ttyUSB1` its UART -- and `/dev/ttyACM0`
is the ADALM2000, not the PYNQ.  `--port` defaults to the UART.  To confirm
the mapping on another machine:

    ssh xilinx@<board> 'echo xilinx | sudo -S sh -c "echo HELLO > /dev/ttyPS0"'

and watch which one says HELLO.

WHY THE RECONNECT LOOP.  ROUND 30 armed a naive `while True: read()` logger,
the board power-cycled, and the logger died on the first read afterwards with

    SerialException: device reports readiness to read but returned no data
                     (device disconnected or multiple access on port?)

...capturing nothing.  That is not a flaw in the logging; it is the *evidence*.
The FT2232 is powered from the USB cable, so a PS-only reset leaves it
enumerated and the port open.  For the port to vanish, the BOARD's power has to
go -- so a logger that dies this way has just told you the board browned out
rather than crashed.  It should therefore say so, and then wait for the port
to come back, which is what this does.
"""
import argparse
import os
import sys
import time

DEFAULT_PORT = '/dev/ttyUSB1'


def main():
    ap = argparse.ArgumentParser(description="Log the PYNQ's serial console.")
    ap.add_argument('--port', default=DEFAULT_PORT)
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--out', default='pynq-console.log')
    ap.add_argument('--quiet', action='store_true',
                    help='do not echo to stdout as well as the file')
    a = ap.parse_args()
    import serial

    with open(a.out, 'ab', buffering=0) as f:
        def say(s):
            line = ('\n=== %s  %s ===\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), s))
            f.write(line.encode())
            if not a.quiet:
                sys.stdout.write(line)
                sys.stdout.flush()

        say('logger armed on %s at %d baud' % (a.port, a.baud))
        open_since = None
        while True:
            try:
                s = serial.Serial(a.port, a.baud, timeout=1)
            except Exception as e:
                if open_since is not None:
                    say('port GONE (%s) -- the FT2232 is USB-powered, so this '
                        'means the BOARD lost power, not that Linux crashed' % e)
                    open_since = None
                time.sleep(1.0)
                continue
            if open_since is None:
                say('port open')
                open_since = time.time()
            try:
                while True:
                    d = s.read(4096)
                    if d:
                        f.write(d)
                        if not a.quiet:
                            sys.stdout.write(d.decode('utf-8', 'replace'))
                            sys.stdout.flush()
            except Exception as e:
                say('read failed (%s) -- reopening' % e)
                open_since = None
            finally:
                try:
                    s.close()
                except Exception:
                    pass
            time.sleep(0.5)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
