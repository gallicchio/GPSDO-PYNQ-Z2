"""PYNQ driver for the GPSDO DDMTD overlay.

    from pynq import Overlay
    ol = Overlay('dmtd_top.bit')       # .hwh must sit next to it
    d  = ol.dmtd_capture_0             # bound automatically by VLNV
    d.selftest()
    d.phases_ps()                      # ps of each GPSDO against the null channel

The register map lives in dmtd_capture.v and is mirrored in dmtd_constants.py,
which is generated from gen/design.py so the driver cannot disagree with the
board about which GPSDO is on which channel.

WHAT THE NUMBERS MEAN

The core records WHEN each beat edge happened, counted in helper cycles.  One
helper cycle of displacement between two channels' beat edges is T_RES_PS =
12.3425 ps of phase between the two 10 MHz inputs, because the beat divides the
input phase down by N_GAIN = 8101.  A whole beat period of displacement is a
whole 10 MHz cycle, 100 ns, which is where the measurement wraps -- so a raw
phase reading is only ever modulo 100 ns and long runs must be unwrapped.

Everything here is read-only except CONTROL, and every multi-word read is
retried until it is self-consistent: the timestamp and the edge count are three
separate AXI transactions, and the helper domain can update them in between.
"""
import time

try:
    from pynq import DefaultIP, Overlay
    _HAVE_PYNQ = True
except ImportError:          # a host machine: the phase arithmetic still works
    DefaultIP = object
    Overlay = object
    _HAVE_PYNQ = False

from .dmtd_constants import (
    F_HELPER, F_BEAT, N_GAIN, T_RES_PS, WRAP_PS, HELPER_CYCLES_PER_BEAT,
    N_BEAT, N_PPS, PPS0, UNIT_NAMES, PPS_SLOT, NULL_CHANNEL,
    REG_ID, REG_VERSION, REG_CONTROL, REG_HELPER, REG_LIVE_LO, REG_LIVE_HI,
    REG_ALIVE, REG_CHAN0, CHAN_STRIDE, OFF_TS_LO, OFF_TS_HI, OFF_COUNT,
    REG_LIVE_PS_LO, REG_LIVE_PS_HI, REG_PSCHAN0, GATEWARE_MIN_MINOR_FOR_PS,
    MAGIC_ID, BASE_ADDR,
)

# The helper-frequency estimator counts PS clocks per 2^DIV_W helper cycles.
# DIV_W is a parameter of dmtd_capture; the synthesised default is 20 and the
# testbench is the only thing that ever changes it.
HELPER_TICK_CYCLES = 1 << 20

__all__ = ['DmtdRegisters', 'phase_ps', 'wrap_cycles', 'unwrap_ps',
           'beat_period_cycles', 'resolve_cycles']
if _HAVE_PYNQ:
    __all__ += ['DmtdCapture', 'DmtdOverlay', 'attach']


# ---------------------------------------------------------------------------
# phase arithmetic -- no hardware, so it can be tested on any machine
# ---------------------------------------------------------------------------
def beat_period_cycles():
    """Helper cycles in one beat period.  Not an integer: 8101.1017..."""
    return HELPER_CYCLES_PER_BEAT


def wrap_cycles(delta):
    """Wrap a helper-cycle difference into +/- half a beat period.

    Two channels' most recent beat edges can be up to a whole beat period
    apart and still describe the same small phase difference, so the raw
    difference has to be folded before it means anything.  Works on scalars
    and on numpy arrays.
    """
    p = HELPER_CYCLES_PER_BEAT
    return (delta + p / 2.0) % p - p / 2.0


def phase_ps(ts_a, ts_b):
    """Phase of channel a relative to channel b, in ps, wrapped into +/-50 ns.

    ts_a and ts_b are raw 64-bit helper-cycle timestamps as read from the
    core.  The result is the phase between the two 10 MHz inputs: one helper
    cycle of beat displacement is T_RES_PS of input phase.
    """
    return wrap_cycles(ts_a - ts_b) * T_RES_PS


def unwrap_ps(series, wrap=WRAP_PS):
    """Undo the 100 ns wrap in a sequence of phase readings.

    A drifting oscillator walks through 100 ns and starts again; this turns
    that sawtooth back into the continuous ramp it physically is.  Pass a
    sequence, get a list (or a numpy array if numpy is available).
    """
    try:
        import numpy as np
        a = np.asarray(series, dtype=float)
        if a.size < 2:
            return a.copy()
        steps = np.diff(a)
        steps -= wrap * np.round(steps / wrap)
        return np.concatenate(([a[0]], a[0] + np.cumsum(steps)))
    except ImportError:                       # pragma: no cover
        out, acc = [], None
        prev = None
        for x in series:
            if prev is None:
                acc = float(x)
            else:
                step = float(x) - prev
                step -= wrap * round(step / wrap)
                acc += step
            out.append(acc)
            prev = float(x)
        return out


def resolve_cycles(fine_ps, coarse_ps, wrap=WRAP_PS):
    """Combine a beat-derived phase (fine, exact but modulo `wrap`) with a
    pps-derived offset (coarse, 10 ns quantised, unambiguous) into one
    absolute phase in ps.  Returns (phase_ps, n_cycles, residual_ps): the
    residual is how far the coarse value sat from the nearest consistent
    integer -- near +/- wrap/2 means the pps did not decide it.

    ASSUMPTION, stated because no datasheet promises it: each GPSDO's pps
    edge is aligned to a rising edge of its own 10 MHz to better than
    +/- 40 ns.  Measure it per unit before believing the integer.
    """
    n = round((coarse_ps - fine_ps) / wrap)
    return fine_ps + n * wrap, int(n), coarse_ps - (fine_ps + n * wrap)


# ---------------------------------------------------------------------------
# register semantics, on top of anything with .read(offset) / .write(offset, v)
# ---------------------------------------------------------------------------
class DmtdRegisters(object):
    """Everything the core can be asked, independent of how it is reached.

    Mixed into the PYNQ DefaultIP driver below, and usable directly on top of
    a bare MMIO or a JTAG-AXI shim for bring-up.
    """

    ps_clk_hz = 100e6           # FCLK_CLK0; overridden from the overlay
    _RETRIES = 8

    # ---- identity --------------------------------------------------------
    @property
    def id(self):
        return self.read(REG_ID)

    @property
    def version(self):
        """(major, minor, n_beat, n_pps) as built into the bitstream."""
        v = self.read(REG_VERSION)
        return ((v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)

    @property
    def alive(self):
        """True while the helper clock is running."""
        return bool(self.read(REG_ALIVE) & 1)

    @property
    def has_ps_timestamps(self):
        """Gateware 1.1 and later stamp every pps in the PS domain too."""
        maj, minr, _, _ = self.version
        return (maj, minr) >= (1, GATEWARE_MIN_MINOR_FOR_PS)

    @property
    def ps_ns_per_tick(self):
        return 1e9 / float(self.ps_clk_hz)

    @property
    def helper_hz(self):
        """Measured helper frequency, from PS clocks per 2^20 helper cycles."""
        ticks = self.read(REG_HELPER)
        if not ticks:
            return 0.0
        return HELPER_TICK_CYCLES * float(self.ps_clk_hz) / ticks

    @property
    def counter(self):
        """The free-running helper counter, refreshed about every 102 us.

        Read LO, HI, LO: if a refresh lands between the two words the low
        word changes and the read is retried, so the 64-bit value is never
        torn across a refresh boundary.
        """
        for _ in range(self._RETRIES):
            lo0 = self.read(REG_LIVE_LO)
            hi = self.read(REG_LIVE_HI)
            lo1 = self.read(REG_LIVE_LO)
            if lo0 == lo1:
                return (hi << 32) | lo0
        raise RuntimeError('could not read a consistent helper counter')

    def counter_pair(self):
        """(helper_counter, ps_counter) latched at the same instant, the
        v1.1 pair register.  Read LO/HI of both with the helper LO re-read
        last, so a refresh in the middle is detected and retried."""
        for _ in range(self._RETRIES):
            lo0 = self.read(REG_LIVE_LO)
            hi = self.read(REG_LIVE_HI)
            plo = self.read(REG_LIVE_PS_LO)
            phi = self.read(REG_LIVE_PS_HI)
            lo1 = self.read(REG_LIVE_LO)
            if lo0 == lo1:
                return (hi << 32) | lo0, (phi << 32) | plo
        raise RuntimeError('could not read a consistent counter pair')

    def ps_to_helper_cycles(self, ps_ticks, pair=None, helper_hz=None):
        """Map a PS-domain timestamp onto the helper counter's scale, using
        the pair register and the measured helper frequency.  Error is the
        pair's own +/-1 PS tick plus (helper_hz error) x (distance from the
        pair), so it is good to a few helper cycles over a second."""
        if pair is None:
            pair = self.counter_pair()
        if helper_hz is None:
            helper_hz = self.helper_hz or F_HELPER
        h0, p0 = pair
        return h0 + (ps_ticks - p0) * float(helper_hz) / float(self.ps_clk_hz)

    # ---- control ---------------------------------------------------------
    def clear(self):
        """Zero the free-running counter and every edge count.

        Timestamps are not cleared -- they are only meaningful relative to
        each other anyway, and the counts say how many edges each one has
        seen since this call.
        """
        self.write(REG_CONTROL, 1)

    # ---- measurement -----------------------------------------------------
    def channel(self, slot):
        """(edge_count, timestamp) for one slot, read self-consistently.

        The count is read either side of the timestamp: if a beat edge lands
        in the middle of the three transactions the count changes and the
        read is retried.  Beats are 810 us apart and the three reads take a
        few microseconds, so a retry is rare and a second one is unheard of.
        """
        base = REG_CHAN0 + slot * CHAN_STRIDE
        for _ in range(self._RETRIES):
            c0 = self.read(base + OFF_COUNT)
            lo = self.read(base + OFF_TS_LO)
            hi = self.read(base + OFF_TS_HI)
            c1 = self.read(base + OFF_COUNT)
            if c0 == c1:
                return c0, (hi << 32) | lo
        raise RuntimeError('slot %d kept changing under the read' % slot)

    def ps_channel(self, slot):
        """(edge_count, ps_timestamp) for one pps slot in the PS domain."""
        base = REG_PSCHAN0 + slot * CHAN_STRIDE
        for _ in range(self._RETRIES):
            c0 = self.read(base + OFF_COUNT)
            lo = self.read(base + OFF_TS_LO)
            hi = self.read(base + OFF_TS_HI)
            c1 = self.read(base + OFF_COUNT)
            if c0 == c1:
                return c0, (hi << 32) | lo
        raise RuntimeError('PS slot %d kept changing under the read' % slot)

    def beat(self, n):
        """(edge_count, timestamp) for beat channel n."""
        return self.channel(n)

    def pps(self, n):
        """(edge_count, timestamp) for the pps return of beat channel n."""
        slot = PPS_SLOT[n]
        if slot is None:
            raise ValueError('%s (channel %d) has no pps output'
                             % (UNIT_NAMES[n], n))
        return self.channel(slot)

    def snapshot(self):
        """All beats and all pps at once.

        Returns a dict with 'beat_count', 'beat_ts', 'pps_count', 'pps_ts'
        (lists indexed by beat channel; pps entries are None where the unit
        has no pps) plus 'time' from the host clock and 'counter'.
        """
        bc, bt = [], []
        for n in range(N_BEAT):
            c, t = self.channel(n)
            bc.append(c)
            bt.append(t)
        pc, pt = [], []
        ppc, ppt = [], []
        ps = self.has_ps_timestamps
        for n in range(N_BEAT):
            slot = PPS_SLOT[n]
            if slot is None:
                pc.append(None)
                pt.append(None)
                ppc.append(None)
                ppt.append(None)
            else:
                c, t = self.channel(slot)
                pc.append(c)
                pt.append(t)
                if ps:
                    c2, t2 = self.ps_channel(slot)
                    ppc.append(c2)
                    ppt.append(t2)
                else:
                    ppc.append(None)
                    ppt.append(None)
        out = {'time': time.time(), 'counter': self.counter,
               'beat_count': bc, 'beat_ts': bt,
               'pps_count': pc, 'pps_ts': pt,
               'pps_ps_count': ppc, 'pps_ps_ts': ppt}
        if ps:
            out['pair'] = self.counter_pair()
        return out

    def pps_offsets_ns(self, reference=0, snap=None):
        """Each unit's pps edge time minus the reference unit's, in ns, from
        the PS-domain timestamps: a 10 ns time-interval counter across the
        whole inventory.  None where a unit has no pps or no edge yet."""
        if snap is None:
            snap = self.snapshot()
        ts = snap['pps_ps_ts']
        cnt = snap['pps_ps_count']
        if ts[reference] is None or not cnt[reference]:
            raise ValueError('reference channel %d has no pps timestamp' % reference)
        k = self.ps_ns_per_tick
        return [None if (t is None or not c) else (t - ts[reference]) * k
                for t, c in zip(ts, cnt)]

    def absolute_phases_ps(self, reference=None, snap=None):
        """phases_ps() with the 100 ns integer resolved from the pps, where
        both channels have one.  Returns a list of (phase_ps, n_cycles,
        residual_ps) or None.  See resolve_cycles() for the assumption."""
        if reference is None:
            reference = NULL_CHANNEL
        if snap is None:
            snap = self.snapshot()
        fine = self.phases_ps(reference, snap)
        ts = snap['pps_ps_ts']
        cnt = snap['pps_ps_count']
        k = self.ps_ns_per_tick * 1e3
        out = []
        for n in range(N_BEAT):
            if ts[n] is None or ts[reference] is None or not cnt[n] or not cnt[reference]:
                out.append(None)
            else:
                out.append(resolve_cycles(fine[n], (ts[n] - ts[reference]) * k))
        return out

    def phases_ps(self, reference=None, snap=None):
        """Phase of every GPSDO against the null channel, in picoseconds.

        The null channel is the helper compared with itself through an
        identical signal path, so subtracting it removes the helper's own
        phase noise and the Si5351's jitter and leaves the difference
        between the oscillators.  Pass reference=n to compare against some
        other channel instead.
        """
        if reference is None:
            reference = NULL_CHANNEL
        if snap is None:
            snap = self.snapshot()
        ref = snap['beat_ts'][reference]
        return [phase_ps(ts, ref) for ts in snap['beat_ts']]

    def monitor(self, period=0.1, count=None):
        """Yield snapshots forever (or `count` times), `period` seconds apart.

        Polling is enough: a beat edge carries the phase, and the edge count
        tells you how many you skipped, so a slow reader loses resolution in
        time but never gets a stale or ambiguous phase.
        """
        n = 0
        while count is None or n < count:
            yield self.snapshot()
            n += 1
            time.sleep(period)

    # ---- bring-up --------------------------------------------------------
    def selftest(self, settle=0.5, verbose=True):
        """Check the overlay is alive and every channel is receiving a beat.

        Returns a list of (name, ok, detail).  Run it first, every time:
        almost every confusing result from this instrument starts with a dead
        helper or a channel with nothing plugged into it.
        """
        results = []

        def note(name, ok, detail):
            results.append((name, bool(ok), detail))

        ident = self.id
        note('ID', ident == MAGIC_ID, '0x%08X' % ident)
        if ident != MAGIC_ID:
            if verbose:
                self._print(results)
            return results

        maj, minr, nb, npps = self.version
        note('VERSION', nb == N_BEAT and npps == N_PPS,
             'v%d.%d, %d beats, %d pps (driver expects %d/%d)%s'
             % (maj, minr, nb, npps, N_BEAT, N_PPS,
                '' if self.has_ps_timestamps else
                ' -- pre-1.1: no PS-domain pps timestamps'))

        note('helper running', self.alive, '')
        hz = self.helper_hz
        err = (hz - F_HELPER) / F_HELPER * 1e6 if hz else float('inf')
        note('helper frequency', hz and abs(err) < 100,
             '%.1f Hz (%.1f ppm from %.1f Hz)' % (hz, err, F_HELPER))

        self.clear()
        time.sleep(settle)
        expect = F_BEAT * settle
        for n in range(N_BEAT):
            c, _ = self.channel(n)
            ok = 0.5 * expect < c < 1.5 * expect
            note('beat %2d %s' % (n, UNIT_NAMES[n]), ok,
                 '%d edges in %.2f s (expect ~%.0f)' % (c, settle, expect))
        for n in range(N_BEAT):
            slot = PPS_SLOT[n]
            if slot is None:
                continue
            c, _ = self.channel(slot)
            note('pps  %2d %s' % (n, UNIT_NAMES[n]), True,
                 '%d edges in %.2f s' % (c, settle))

        if verbose:
            self._print(results)
        return results

    @staticmethod
    def _print(results):
        width = max(len(r[0]) for r in results)
        bad = 0
        for name, ok, detail in results:
            bad += not ok
            print('%s  %-*s  %s' % ('ok  ' if ok else 'FAIL', width, name, detail))
        print('--- %d checks, %d failures' % (len(results), bad))


# ---------------------------------------------------------------------------
# the PYNQ bindings
#
# Defined only when pynq is importable.  On a host machine the module still
# loads, so the phase arithmetic and the register semantics can be tested
# without a board -- DmtdRegisters works on anything with .read()/.write().
# ---------------------------------------------------------------------------
if _HAVE_PYNQ:
    class DmtdCapture(DmtdRegisters, DefaultIP):
        """Bound to the measurement core automatically when the overlay loads.

        PYNQ matches this against the IP's VLNV in the .hwh, so after
        Overlay('dmtd_top.bit') the core is simply ol.dmtd_capture_0.
        """

        bindto = ['xilinx.com:module_ref:dmtd_capture:1.0']

        def __init__(self, description):
            super().__init__(description=description)
            try:
                from pynq.ps import Clocks
                self.ps_clk_hz = Clocks.fclk0_mhz * 1e6
            except Exception:                     # pragma: no cover
                pass                              # keep the 100 MHz default

        def __repr__(self):
            try:
                return ('<DmtdCapture at 0x%08X, helper %s>'
                        % (self.mmio.base_addr,
                           ('%.3f MHz' % (self.helper_hz / 1e6)) if self.alive
                           else 'STOPPED'))
            except Exception:                     # pragma: no cover
                return '<DmtdCapture>'


    def attach(overlay, name='dmtd_capture_0'):
        """Return the DmtdCapture driver for `name` in `overlay`.

        USE THIS INSTEAD OF `overlay.dmtd_capture_0`, which does not work on
        PYNQ 3.0.1.

        The driver registers correctly -- `overlay.ip_dict[name]['driver']` is
        DmtdCapture, and pynq's bindto registry maps
        'xilinx.com:module_ref:dmtd_capture:1.0' to it.  But pynq's metadata
        path also invents an EMPTY hierarchy with the same name as the IP, and
        `_IPMap.__getattr__` tests `hierarchies` BEFORE `ip`:

            if key in self._description["hierarchies"]:   # empty, but present
                ...
            elif key in self._description["ip"]:          # never reached

        so `overlay.dmtd_capture_0` returns a DocumentedHierarchy with nothing
        in it.  Parsing the same .hwh with `HWH()` directly yields an empty
        hierarchy_dict, so the hierarchy is added somewhere in the embedded
        device metadata path rather than by the .hwh parser; deleting pynq's
        `_current_metadata.pkl` and `global_pl_state.json` does not change it,
        so it is not stale cache.  Seen with a `module_ref` IP; the packaged
        `axi_iic` in the same design is unaffected.

        Going through ip_dict sidesteps the whole thing and is what the
        attribute shortcut would have done anyway.
        """
        cache = getattr(overlay, '_dmtd_drivers', None)
        if cache is None:
            cache = {}
            try:
                overlay._dmtd_drivers = cache
            except Exception:            # pragma: no cover - read-only overlay
                pass
        if name not in cache:
            desc = overlay.ip_dict[name]
            cache[name] = desc.get('driver', DmtdCapture)(desc)
        return cache[name]


    class DmtdOverlay(Overlay):
        """Overlay('dmtd_top.bit') with the measurement core as .dmtd.

            ol = DmtdOverlay()
            ol.dmtd.selftest()
        """

        def __init__(self, bitfile='dmtd_top.bit', **kwargs):
            super().__init__(bitfile, **kwargs)

        @property
        def dmtd(self):
            """The measurement core.  Goes through ip_dict -- see attach()."""
            return attach(self)

        @property
        def iic(self):
            """The AXI IIC reaching the Si5351, the thermometers, the DAC and
            the 1-Wire bridge.

            pynq 3.0 binds its own `pynq.lib.iic.AxiIIC` driver to this, so it
            already has send/receive.  Device-level drivers for the parts on
            the bus are not written yet -- the Si5351 is the one that matters,
            because nothing beats until it is programmed."""
            return self.axi_iic_0
