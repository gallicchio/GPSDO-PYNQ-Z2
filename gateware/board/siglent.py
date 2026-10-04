#!/usr/bin/env python3
"""The bench's Siglent generator and scope, over LAN or USB -- round 43.

Runs on the LAPTOP, not the PYNQ.

    python3 siglent.py              # identify both and print their settings
    python3 siglent.py --usb        # the same, over USB
    python3 siglent.py --raw        # over a raw socket (port 5025): avoid

    SDG1032X       function generator   192.168.8.246   /dev/usbtmc* f4ec:1103
    SDS2104X Plus  oscilloscope         192.168.8.203   /dev/usbtmc* f4ec:1011

Three transports carry the same SCPI, with no VISA and nothing to install:

  LAN  VXI-11 (what VISA calls TCPIP::<ip>::INSTR), in ~60 lines of ONC RPC
       below.  The default, and the only one to use with the scope: it
       frames every message.
  raw  a socket on port 5025.  It does not frame replies; see Link.
  USB  the kernel's usbtmc driver.  Linux makes /dev/usbtmcN root-only; one
       udev rule fixes that for good (jason is in plugdev):

       echo 'SUBSYSTEM=="usbmisc", KERNEL=="usbtmc*", ATTRS{idVendor}=="f4ec", GROUP="plugdev", MODE="0660"' \\
           | sudo tee /etc/udev/rules.d/99-siglent-usbtmc.rules
       sudo udevadm control --reload && sudo udevadm trigger

SAFETY, because the generator drives the board's 10 MHz inputs, which are
rated 0.7-3.3 Vpp and 4.1 Vpp at most (HANDBOOK, test point In):

  * no *RST, ever: it would put the generator back to its defaults;
  * an output's LOAD setting is never changed.  It does not change the
    output stage, only how the generator states its amplitude, so the same
    number means twice the volts;
  * amplitude is capped by what reaches an UNTERMINATED input: the open-
    circuit voltage, 3.3 Vpp at most.  That is AMP 3.3 with LOAD HZ but
    1.65 with LOAD 50.  An input with its 50R jumper fitted only gets less;
  * an output is never switched on, and its waveform is never changed;
  * a scope's input impedance and coupling are never changed, because 50 ohm
    against 1 Mohm moves what the board receives as well.
"""
import os
import re
import socket
import struct
import sys
import time

SDG_IP = '192.168.8.246'
SDS_IP = '192.168.8.203'
SDG_USB = 0x1103                  # USB product ids, vendor 0xf4ec (Siglent)
SDS_USB = 0x1011
OPEN_CIRCUIT_MAX_VPP = 3.3        # the board's rated maximum, at the SMA


class _RPC:
    """Just enough ONC RPC over TCP for VXI-11 (RFC 5531 record marking)."""

    def __init__(self, host, port, prog, vers, timeout):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.prog, self.vers = prog, vers
        self.xid = int(time.time() * 1000) & 0x7fffffff

    def call(self, proc, args):
        self.xid = (self.xid + 1) & 0xffffffff
        msg = struct.pack('>10I', self.xid, 0, 2, self.prog, self.vers, proc,
                          0, 0, 0, 0) + args
        self.s.sendall(struct.pack('>I', 0x80000000 | len(msg)) + msg)
        rep = b''
        while True:
            n = struct.unpack('>I', self._recvn(4))[0]
            rep += self._recvn(n & 0x7fffffff)
            if n & 0x80000000:
                break
        xid, mtype, rstat = struct.unpack('>3I', rep[:12])
        vlen = struct.unpack('>I', rep[16:20])[0]
        off = 20 + vlen + (-vlen % 4)
        astat = struct.unpack('>I', rep[off:off + 4])[0]
        if xid != self.xid or mtype != 1 or rstat != 0 or astat != 0:
            raise IOError('RPC reply rejected (%d %d %d %d)'
                          % (xid != self.xid, mtype, rstat, astat))
        return rep[off + 4:]

    def _recvn(self, n):
        b = b''
        while len(b) < n:
            d = self.s.recv(n - len(b))
            if not d:
                raise IOError('connection closed')
            b += d
        return b

    def close(self):
        self.s.close()


def _opaque(b):
    return struct.pack('>I', len(b)) + b + b'\0' * (-len(b) % 4)


class Link:
    """One instrument, over VXI-11 (the default on LAN), a raw socket on
    port 5025, or a /dev/usbtmcN node.

    Round 43: use VXI-11.  It frames every message, so a reply can neither
    arrive late nor run into the next one.  The raw socket can do both: the
    scope keeps unread replies across connections, and a block is followed by
    two line ends.  After one of my raw-socket sessions went out of step and
    ended mid-transfer, the scope's whole remote service stopped, VXI-11 core
    included, until it was restarted."""

    VXI11_CORE = 0x0607AF

    def __init__(self, host=None, usb=None, raw=False, timeout=10.0):
        self.timeout = timeout
        self.sock = self.fd = self.rpc = None
        self.pending = b''
        if usb is not None:
            self.fd = os.open(usb, os.O_RDWR)
            self.where = usb
        elif raw:
            self.sock = socket.create_connection((host, 5025), timeout=timeout)
            self.where = host + ':5025'
        else:
            pm = _RPC(host, 111, 100000, 2, timeout)       # portmapper GETPORT
            port = struct.unpack('>I', pm.call(
                3, struct.pack('>4I', self.VXI11_CORE, 1, 6, 0))[:4])[0]
            pm.close()
            self.rpc = _RPC(host, port, self.VXI11_CORE, 1, timeout)
            r = self.rpc.call(10, struct.pack('>iII', 0x4743, 0, 0)
                              + _opaque(b'inst0'))         # create_link
            err, self.lid = struct.unpack('>ii', r[:8])
            if err:
                raise IOError('%s: VXI-11 create_link error %d' % (host, err))
            self.where = host + ' (VXI-11)'
        self.sync()

    def sync(self, tries=8):
        """Ask *IDN? and discard every reply until its answer arrives: on a
        raw socket or USB, the scope may still hold an earlier one."""
        self.write('*IDN?')
        for _ in range(tries):
            r = self.read_raw()
            if r.startswith(b'Siglent'):
                self.ident = r.decode(errors='replace').strip()
                return self.ident
        raise IOError('%s: no *IDN? answer in %d replies' % (self.where, tries))

    def close(self):
        if self.rpc:
            try:
                self.rpc.call(23, struct.pack('>i', self.lid))  # destroy_link
            finally:
                self.rpc.close()
        if self.sock:
            self.sock.close()
        if self.fd is not None:
            os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def write(self, cmd):
        data = (cmd + '\n').encode()
        if self.rpc:
            ms = int(self.timeout * 1000)
            r = self.rpc.call(11, struct.pack('>iIII', self.lid, ms, 0, 8)
                              + _opaque(data))             # device_write, END
            err = struct.unpack('>i', r[:4])[0]
            if err:
                raise IOError('%s: device_write error %d on %r'
                              % (self.where, err, cmd))
        elif self.sock:
            self.sock.sendall(data)
        else:
            os.write(self.fd, data)

    def _chunk(self):
        if self.sock:
            d = self.sock.recv(1 << 20)
            if not d:
                raise IOError('%s closed the connection' % self.where)
            return d
        return os.read(self.fd, 1 << 20)

    def read_raw(self):
        """One complete reply: a text line, or an IEEE 488.2 block -- an
        optional prefix, '#', one digit n, n digits of length, the bytes."""
        if self.rpc:
            ms = int(self.timeout * 1000)
            out = b''
            while True:                                    # device_read
                r = self.rpc.call(12, struct.pack('>iIIIIi', self.lid, 1 << 22,
                                                  ms, 0, 0, 0))
                err, reason, n = struct.unpack('>iiI', r[:12])
                if err:
                    raise IOError('%s: device_read error %d (15 is a time-out: '
                                  'a query it did not answer)' % (self.where, err))
                out += r[12:12 + n]
                if reason & 4:                             # END
                    return out
        # Raw socket or USB: parse the stream.  Bytes past the reply are kept
        # for the next one, and stray line ends in front of a reply skipped.
        t_end = time.time() + self.timeout
        while True:
            buf = self.pending = self.pending.lstrip(b'\r\n')
            nl = buf.find(b'\n')
            i = buf.find(b'#')
            if i >= 0 and (nl < 0 or i < nl) and len(buf) >= i + 2 \
                    and buf[i + 1:i + 2].isdigit():
                nd = int(buf[i + 1:i + 2])
                if len(buf) >= i + 2 + nd:
                    end = i + 2 + nd + int(buf[i + 2:i + 2 + nd])
                    if len(buf) >= end:
                        self.pending = buf[end:]
                        return buf[:end]
            elif nl >= 0:
                self.pending = buf[nl + 1:]
                return buf[:nl + 1]
            if time.time() > t_end:
                raise IOError('%s: timed out after %r' % (self.where, buf[:80]))
            self.pending += self._chunk()

    def query(self, cmd):
        self.write(cmd)
        return self.read_raw().decode(errors='replace').strip()

    def query_block(self, cmd):
        """The payload of a #N block reply (waveforms, preambles)."""
        self.write(cmd)
        buf = self.read_raw()
        i = buf.find(b'#')
        if i < 0 or not buf[i + 1:i + 2].isdigit():
            raise IOError('%s: %r did not answer with a block: %r'
                          % (self.where, cmd, buf[:40]))
        nd = int(buf[i + 1:i + 2])
        n = int(buf[i + 2:i + 2 + nd])
        return buf[i + 2 + nd:i + 2 + nd + n]

    def idn(self):
        return self.query('*IDN?')


def _kv(reply):
    """'C1:BSWV WVTP,SINE,FRQ,10000000HZ,...' -> {'WVTP': 'SINE', ...}."""
    body = reply.split(' ', 1)[1] if ' ' in reply else ''
    f = body.split(',')
    return dict(zip(f[0::2], f[1::2]))


def _num(s):
    m = re.match(r'[-+0-9.eE]+', s or '')
    return float(m.group(0)) if m else None


# ---------------------------------------------------------------------------
class SDG(Link):
    """Siglent SDG1032X."""

    def channel(self, ch):
        d = _kv(self.query('C%d:BSWV?' % ch))
        o = _kv(self.query('C%d:OUTP?' % ch).replace('OUTP ', 'OUTP STATE,', 1))
        d.update({'OUTPUT': o.get('STATE'), 'LOAD': o.get('LOAD'),
                  'POLARITY': o.get('PLRT')})
        return d

    def status(self):
        out = {'IDN': self.idn()}
        for ch in (1, 2):
            out['C%d' % ch] = self.channel(ch)
            for cmd in ('MDWV', 'SWWV', 'BTWV'):
                out['C%d %s' % (ch, cmd)] = self.query('C%d:%s?' % (ch, cmd))
        for cmd in ('ROSC?', 'COUP?', 'MODE?'):
            try:
                out[cmd] = self.query(cmd)
            except IOError as e:
                out[cmd] = 'no reply (%s)' % e
        return out

    @staticmethod
    def open_circuit(amp_vpp, load):
        """The volts an unterminated input sees for AMP at this LOAD."""
        if load in (None, 'HZ'):
            return amp_vpp
        r = float(load)                       # the generator's own 50 ohm
        return amp_vpp * (r + 50.0) / r

    def set(self, ch, freq=None, phase=None, amp=None):
        """Change frequency (Hz), phase (degrees) or amplitude (Vpp, as the
        generator states it) of a SINE that is already running, then read it
        back.  Anything else is refused."""
        cur = self.channel(ch)
        if cur.get('WVTP') != 'SINE':
            raise ValueError('C%d is %s, not SINE: not touching it'
                             % (ch, cur.get('WVTP')))
        if amp is not None:
            voc = self.open_circuit(amp, cur.get('LOAD'))
            if voc > OPEN_CIRCUIT_MAX_VPP + 1e-9:
                raise ValueError('C%d: AMP %.3f V at LOAD %s is %.2f Vpp open '
                                 'circuit, above the board\'s %.1f'
                                 % (ch, amp, cur.get('LOAD'), voc,
                                    OPEN_CIRCUIT_MAX_VPP))
        if freq is not None and not 9.99e6 <= freq <= 10.01e6:
            raise ValueError('frequency %.3f Hz is not within 0.1 %% of 10 MHz'
                             % freq)
        parts = []
        if freq is not None:
            parts.append('FRQ,%.6f' % freq)
        if amp is not None:
            parts.append('AMP,%.4f' % amp)
        if phase is not None:
            parts.append('PHSE,%.3f' % phase)
        if parts:
            self.write('C%d:BSWV %s' % (ch, ','.join(parts)))
            time.sleep(0.15)
        return self.channel(ch)

    def snapshot(self, ch):
        """What restore() needs to put a channel back as it was found."""
        c = self.channel(ch)
        return {k: c[k] for k in ('WVTP', 'FRQ', 'AMP', 'OFST', 'PHSE', 'LOAD')}

    def restore(self, ch, snap):
        """Put back a snapshot -- the one way to write an amplitude above the
        cap, because it was the user's own setting when the snapshot was taken
        and LOAD has not changed since (round 43: both outputs were found at
        4 Vpp open circuit)."""
        cur = self.channel(ch)
        if cur.get('WVTP') != snap['WVTP'] or cur.get('LOAD') != snap['LOAD']:
            raise ValueError('C%d changed under us (%s %s -> %s %s): not restoring'
                             % (ch, snap['WVTP'], snap['LOAD'], cur.get('WVTP'),
                                cur.get('LOAD')))
        self.write('C%d:BSWV FRQ,%s,AMP,%s,OFST,%s,PHSE,%s'
                   % (ch, _num(snap['FRQ']), _num(snap['AMP']),
                      _num(snap['OFST']), _num(snap['PHSE'])))
        time.sleep(0.15)
        back = self.snapshot(ch)
        if any(_num(back[k]) != _num(snap[k]) for k in ('FRQ', 'AMP', 'OFST', 'PHSE')):
            raise IOError('C%d did not restore: %s -> %s' % (ch, snap, back))
        return back


# ---------------------------------------------------------------------------
class SDS(Link):
    """Siglent SDS2104X Plus (the SDS2000X Plus command set)."""

    def channel(self, ch):
        out = {}
        for item in ('SWITch', 'SCALe', 'OFFSet', 'COUPling', 'IMPedance',
                     'PROBe', 'BWLimit', 'INVert', 'SKEW', 'UNIT'):
            out[item] = self.query(':CHANnel%d:%s?' % (ch, item))
        return out

    def status(self):
        out = {'IDN': self.idn()}
        for ch in (1, 2, 3, 4):
            out['C%d' % ch] = self.channel(ch)
        for q in (':TIMebase:SCALe?', ':TIMebase:DELay?', ':ACQuire:SRATe?',
                  ':ACQuire:MDEPth?', ':ACQuire:TYPE?', ':ACQuire:MODE?',
                  ':TRIGger:MODE?', ':TRIGger:STATus?', ':TRIGger:TYPE?',
                  ':TRIGger:EDGE:SOURce?', ':TRIGger:EDGE:LEVel?',
                  ':TRIGger:EDGE:SLOPe?', ':TRIGger:EDGE:COUPling?'):
            out[q] = self.query(q)
        return out

    def waveform(self, ch, points=None):
        """One channel's record as volts, with its time axis (s): the whole
        acquisition, or its first `points`.  (POINt 0 means none, not all.)"""
        if points is None:
            points = int(float(self.query(':ACQuire:POINts?')))
        self.write(':WAVeform:SOURce C%d' % ch)
        self.write(':WAVeform:STARt 0')
        self.write(':WAVeform:WIDTh BYTE')
        self.write(':WAVeform:POINt %d' % points)
        pre = self.query_block(':WAVeform:PREamble?')
        n = struct.unpack_from('<i', pre, 0x74)[0]
        vdiv = struct.unpack_from('<f', pre, 0x9c)[0]
        voff = struct.unpack_from('<f', pre, 0xa0)[0]
        # Codes per division.  Siglent's examples read it at 0xa4, but this
        # firmware puts 127 (the largest code) there.  It is 30: round 43's
        # raw peaks of 31, 52 and -53 codes at 1 V/div are exactly the scope's
        # own MAX/MIN measurements of 1.033, 1.733 and -1.767 V.
        code = 30.0
        dt = struct.unpack_from('<f', pre, 0xb0)[0]
        delay = struct.unpack_from('<d', pre, 0xb4)[0]
        probe = struct.unpack_from('<f', pre, 0x148)[0]
        tdiv = float(self.query(':TIMebase:SCALe?'))
        raw = self.query_block(':WAVeform:DATA?')
        import numpy as np
        v = np.frombuffer(raw, dtype=np.int8).astype(float)
        volts = v * (vdiv * probe / code) - voff * probe
        # the first point sits five divisions before the (delayed) centre
        t = -delay - 5 * tdiv + np.arange(len(volts)) * dt
        return t, volts, dict(points=n, vdiv=vdiv, voff=voff, code=code,
                              dt=dt, delay=delay, tdiv=tdiv, probe=probe)

    def screenshot(self, path):
        """The screen as a PNG.  This firmware sends the bare file, with no
        #N length header, so read to the PNG's own end marker."""
        end_mark = b'IEND\xaeB`\x82'
        if self.rpc:
            self.write(':PRINt? PNG')
            buf = self.read_raw()
            png = buf[buf.find(b'\x89PNG'):buf.find(end_mark) + len(end_mark)]
            with open(path, 'wb') as f:
                f.write(png)
            return len(png)
        self.write(':PRINt? PNG')
        t_end = time.time() + max(self.timeout, 20.0)
        while end_mark not in self.pending:
            if time.time() > t_end:
                raise IOError('%s: screenshot timed out at %d bytes'
                              % (self.where, len(self.pending)))
            self.pending += self._chunk()
        buf = self.pending
        end = buf.find(end_mark) + len(end_mark)
        png = buf[buf.find(b'\x89PNG'):end]
        self.pending = buf[end:]
        with open(path, 'wb') as f:
            f.write(png)
        return len(png)


def usb_node(product):
    """/dev/usbtmcN for a Siglent product id, from sysfs."""
    for d in sorted(os.listdir('/sys/class/usbmisc')):
        pid = open('/sys/class/usbmisc/%s/device/../idProduct' % d).read()
        if int(pid, 16) == product:
            return '/dev/' + d
    raise IOError('no USB instrument with product id %04x' % product)


def connect(kind, usb=False, raw=False):
    cls, ip, pid = {'sdg': (SDG, SDG_IP, SDG_USB),
                    'sds': (SDS, SDS_IP, SDS_USB)}[kind]
    if usb:
        return cls(usb=usb_node(pid))
    return cls(ip, raw=raw)


def main():
    usb, raw = '--usb' in sys.argv, '--raw' in sys.argv
    for name, kind in (('generator', 'sdg'), ('scope', 'sds')):
        try:
            with connect(kind, usb, raw) as inst:
                print('== %s, %s' % (name, inst.where))
                for k, v in inst.status().items():
                    print('  %-24s %s' % (k, v))
        except (IOError, OSError) as e:
            print('== %s: %s' % (name, e))


if __name__ == '__main__':
    main()
