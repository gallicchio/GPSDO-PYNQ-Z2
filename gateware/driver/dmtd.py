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

# A beat slot's edge rate is a beat if it is within this fraction of F_BEAT.
# The TCXO's +/-2.5 ppm moves the beat +/-25 Hz (2 %), so 10 % is generous
# without admitting anything else this board is known to produce.
BEAT_TOL = 0.10

__all__ = ['DmtdRegisters', 'phase_ps', 'wrap_cycles', 'unwrap_ps',
           'beat_period_cycles', 'resolve_cycles', 'classify_beat_rate',
           'count_slips']
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


def count_slips(helper, ps, ps_clk_hz=100e6, ref_period_s=40e-9):
    """Whole-reference-cycle steps in a series of (helper counter, PS counter)
    pairs, as (slips, other_steps).

    ROUND 39.  The pair register latches both counters together every 1024
    helper cycles, so with two clean crystal clocks every interval between
    pairs is the same length in PS ticks to +/-1 tick of synchroniser jitter.
    A synthesiser PLL that slips one 25 MHz reference cycle makes an interval
    40 ns -- 4 ticks at 100 MHz -- long or short; that is what the first board
    did ~650 times a second with CLK0 at 8 mA.  An interval off by anything
    else (a whole 100 ns helper period, say: an extra edge at the FPGA pin)
    is counted in other_steps.
    """
    q = ref_period_s * ps_clk_hz                     # ticks per slip, 4.0
    iv = [(b - a, d - c) for a, b, c, d in zip(helper, helper[1:], ps, ps[1:])
          if b > a]
    if not iv:
        return 0, 0
    # PS ticks per helper cycle.  The median of the per-interval ratios is
    # robust but biased by up to a tick (each interval is a whole number of
    # ticks), and a tick of bias is enough to make a 10-tick step look like
    # three slips -- so refine it as the MEAN over the intervals the median
    # calls clean.  Clean intervals then sit within +/-1 tick of zero.
    ratios = sorted(p / float(h) for h, p in iv)
    r0 = ratios[len(ratios) // 2]
    ok = [(h, p) for h, p in iv if abs(p - h * r0) <= 2]
    r = sum(p for _, p in ok) / float(sum(h for h, _ in ok)) if ok else r0
    slips = other = 0
    for h, p in iv:
        dev = p - h * r
        if abs(dev) < 1.5:
            continue
        k = int(round(dev / q))
        if k and abs(dev - k * q) <= 1.0:
            slips += abs(k)
        else:
            other += 1
    return slips, other


def classify_beat_rate(rate_hz, f_beat=F_BEAT):
    """What an edge rate on a beat slot means, as (kind, text).

    kind is 'beat', 'chatter', 'slow', 'quiet' or 'fast'.  ROUND 39, the
    first board, helper running and NOTHING on any SMA: some squarers sat
    still, some toggled at 551-586 kHz (once 1.0 MHz), each at its own steady
    rate, and a few chattered at 25-7000 edges a second -- and which did what
    changed every time the Si5351 was reprogrammed.  Moving the helper by
    +/-1 % did not move the fast rates, so they are not aliases of anything
    near 10 MHz: the unplugged squarer itself oscillates.  None of that is a
    fault of the channel.

    The rate counts RISING edges, and the core has no deglitcher yet, so a
    beat edge that chatters counts several: round 39's function generators
    read 4-6 rising edges per beat period.  A rate a few times F_BEAT is
    therefore 'chatter' -- a real beat, or an unplugged squarer chattering,
    and the count cannot tell which; the timestamps can.  Only 'beat' is a
    clean pass; 'quiet', 'fast' and 'slow' are definitely not a beat.
    """
    if rate_hz <= 0:
        return 'quiet', ('no edges: nothing plugged in (a quiet squarer), or '
                         'no helper at its flip-flops')
    if abs(rate_hz - f_beat) <= BEAT_TOL * f_beat:
        return 'beat', 'a clean beat'
    if rate_hz > 20 * f_beat:
        return 'fast', ('far above any beat: with nothing plugged in, the '
                        'unplugged squarer oscillating by itself (round 39: '
                        '0.55-1.0 MHz); with a source plugged in, the source '
                        'is not being squared')
    if rate_hz > (1 - BEAT_TOL) * f_beat:
        return 'chatter', ('%.1f rising edges per beat period: a beat whose '
                           'edges chatter (the core does not deglitch yet), '
                           'or an unplugged squarer chattering -- the count '
                           'cannot tell; the timestamps can'
                           % (rate_hz / f_beat))
    return 'slow', ('fewer edges than a beat: an intermittent source, or an '
                    'unplugged squarer chattering (round 39: 25-7000 per s)')


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
        """Measured helper frequency, from PS clocks per 2^20 helper cycles.

        ONE WINDOW OLD, ALWAYS.  The estimator counts PS clocks across
        2^20 helper cycles and latches the result, so this register holds the
        frequency of the window that has just finished -- about 105 ms at
        10 MHz.  Read it too soon after the synthesiser starts or changes and
        you get the window that STRADDLES the change, which is long by
        however much of it had no clock in it, and therefore reports a
        frequency that is low by the same fraction.  See settle_helper().
        """
        ticks = self.read(REG_HELPER)
        if not ticks:
            return 0.0
        return HELPER_TICK_CYCLES * float(self.ps_clk_hz) / ticks

    @property
    def helper_window_s(self):
        """How long one estimator window takes, at the frequency it is
        currently reporting.  Used to size the wait in settle_helper()."""
        hz = self.helper_hz
        return HELPER_TICK_CYCLES / hz if hz else 0.0

    def settle_helper(self, timeout=2.0, tol_ppm=20.0, agree=2):
        """Wait until the helper estimator reports the same frequency twice
        running, and return it.  0.0 if the clock never starts.

        ROUND 30, on real silicon.  `bringup.py` programmed the Si5351 and,
        a few tens of milliseconds later, asked the selftest to check the
        helper.  The estimator's latched value was still the window that
        spanned the moment CLK0 started: it read **8150729.9 Hz** for a helper
        that three independent methods put at 10001217 Hz, and the selftest
        called that a failure.  Nothing was wrong with the clock, the
        gateware, or the arithmetic; the reader was simply one window early.

        Polling until two consecutive windows agree is the fix that does not
        need to know when the clock changed, and it costs one window when the
        clock is already steady.
        """
        deadline = time.time() + timeout
        prev, same = None, 0
        while True:
            hz = self.helper_hz
            if hz and prev and abs(hz - prev) <= prev * tol_ppm * 1e-6:
                same += 1
                if same >= agree - 1:
                    return hz
            else:
                same = 0
            prev = hz
            if time.time() >= deadline:
                return hz
            # A little over one window, so the next read is a different one.
            time.sleep(min(0.15, max(0.02, 1.15 * (self.helper_window_s or 0.11))))

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

    def helper_slips(self, seconds=1.0):
        """(slips_per_second, slips, other_steps, seconds) for the helper,
        from the pair register read as fast as the bus allows -- see
        count_slips().  A clean helper reads 0; the first board with CLK0 at
        8 mA read ~650 per second.  None on gateware without the pair
        register (before 1.1)."""
        if not self.has_ps_timestamps:
            return None
        H, P, last = [], [], None
        t_new = time.time()
        t_end = t_new + seconds
        while True:
            now = time.time()
            # The pair refreshes every ~102 us; 50 ms without a new one means
            # the helper has stopped, and there is nothing to count.
            if now >= t_end or now - t_new > 0.05:
                break
            lo0 = self.read(REG_LIVE_LO)
            hi = self.read(REG_LIVE_HI)
            plo = self.read(REG_LIVE_PS_LO)
            phi = self.read(REG_LIVE_PS_HI)
            lo1 = self.read(REG_LIVE_LO)
            if lo0 != lo1 or lo0 == last:
                continue
            last, t_new = lo0, now
            H.append((hi << 32) | lo0)
            P.append((phi << 32) | plo)
        if len(H) < 3:
            return None
        span = (P[-1] - P[0]) / float(self.ps_clk_hz)
        slips, other = count_slips(H, P, self.ps_clk_hz)
        return (slips / span if span > 0 else 0.0), slips, other, span

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

    def edge_count(self, slot):
        """Edges seen on one slot since the last clear(), from ONE read.

        A single 32-bit read cannot tear, so this works however fast the slot
        is toggling, which channel() does not: its retry needs the count to
        hold still across four reads.  ROUND 39, first board, nothing plugged
        in: five unplugged squarers were oscillating at ~0.57 MHz, channel()
        gave up on the first of them, and the selftest died with a traceback.
        """
        return self.read(REG_CHAN0 + slot * CHAN_STRIDE + OFF_COUNT)

    def _read_or_none(self, slot, ps=False):
        """channel(slot) -- or ps_channel(slot) -- except that a slot toggling
        too fast to be read consistently comes back as (count, None) instead
        of raising, so one unplugged channel cannot take a whole snapshot down
        with it.  The count is still a single, untorn read."""
        try:
            return self.ps_channel(slot) if ps else self.channel(slot)
        except RuntimeError:
            base = REG_PSCHAN0 if ps else REG_CHAN0
            return self.read(base + slot * CHAN_STRIDE + OFF_COUNT), None

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

        A timestamp is None where the slot was toggling too fast to read
        consistently -- in practice an unplugged squarer oscillating (round
        39) -- and its count is still given.
        """
        bc, bt = [], []
        for n in range(N_BEAT):
            c, t = self._read_or_none(n)
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
                c, t = self._read_or_none(slot)
                pc.append(c)
                pt.append(t)
                if ps:
                    c2, t2 = self._read_or_none(slot, ps=True)
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
            if (fine[n] is None or ts[n] is None or ts[reference] is None
                    or not cnt[n] or not cnt[reference]):
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

        None where a channel's timestamp could not be read (see snapshot());
        all None if that channel is the reference.
        """
        if reference is None:
            reference = NULL_CHANNEL
        if snap is None:
            snap = self.snapshot()
        ref = snap['beat_ts'][reference]
        return [None if (ts is None or ref is None) else phase_ps(ts, ref)
                for ts in snap['beat_ts']]

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
    def selftest(self, settle=0.5, verbose=True, front_end=True, inputs=None):
        """Check the overlay is alive and every channel is receiving a beat.

        Returns a list of (name, ok, detail) where `ok` is True, False, or
        None for "not testable here".  Run it first, every time: almost every
        confusing result from this instrument starts with a dead helper or a
        channel with nothing plugged into it.

        front_end=False says there is no front-end board on the header -- the
        squarers and the flip-flops that make a beat are ON that board, so
        with it absent the thirteen beat checks cannot pass and are not
        failures.  Round 30 ran this against a bare PYNQ with a Si5351 wired
        to five header pins and got "29 checks, 14 failures", of which
        thirteen were the front end not existing yet.  A count that includes
        the things that cannot be tested is a count nobody reads.

        inputs is the beat channels (0..12) that have a 10 MHz source plugged
        in; None, the default, means all thirteen -- the instrument in
        service.  A channel in `inputs` that is quiet, oscillating or too slow
        for a beat is a failure; one whose rate says 'chatter' is reported but
        not failed, because a real beat chatters too until the core deglitches
        (classify_beat_rate).  A channel not in `inputs` is measured and
        described but never counted, because nothing was asked of it.
        bringup.py passes --inputs, which defaults to none.
        """
        results = []

        def note(name, ok, detail):
            results.append((name, None if ok is None else bool(ok), detail))

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
        # settle_helper(), not helper_hz: see its docstring.  With a steady
        # clock this costs one estimator window; with one that has just been
        # programmed it is the difference between 10.0012 MHz and a spurious
        # 8.15 MHz.
        hz = self.settle_helper() if self.alive else self.helper_hz
        err = (hz - F_HELPER) / F_HELPER * 1e6 if hz else float('inf')
        note('helper frequency', bool(hz) and abs(err) < 100,
             '%.1f Hz (%.1f ppm from %.1f Hz)' % (hz, err, F_HELPER))
        # ROUND 39: a synthesiser that cycle-slips still reads "10.0012 MHz"
        # to within a few tens of ppm, so the frequency check cannot see it.
        sl = self.helper_slips(1.0) if self.alive else None
        if sl is not None:
            rate, n, other, span = sl
            why = ''
            if rate >= 2.0:
                why = (' -- the Si5351 is cycle-slipping: the helper jumps '
                       '40 ns each time (round 39)')
            elif other > 1:
                why = (' -- the helper gains or loses time in steps that are '
                       'not reference cycles: look for extra edges at the pin')
            note('helper slips', rate < 2.0 and other <= 1,
                 '%d whole-reference-cycle (40 ns) steps and %d other steps in '
                 '%.1f s%s' % (n, other, span, why))

        want = set(range(N_BEAT)) if inputs is None else set(inputs)
        self.clear()
        time.sleep(settle)
        # edge_count(), not channel(): only the count is needed here, and an
        # unplugged squarer can toggle too fast for channel()'s retry loop.
        for n in range(N_BEAT):
            c = self.edge_count(n)
            name = 'beat %2d %s' % (n, UNIT_NAMES[n])
            if not front_end:
                note(name, None, '%d edges in %.2f s  -- no front-end board'
                     % (c, settle))
                continue
            if settle <= 0:
                note(name, None, '%d edges: not a rate, settle = 0' % c)
                continue
            rate = c / float(settle)
            kind, what = classify_beat_rate(rate)
            if kind == 'beat':
                ok = True
            elif kind == 'chatter' or n not in want:
                ok = None               # possibly a beat: not a verdict
            else:
                ok = False
            note(name, ok, '%d edges in %.2f s, %.1f Hz: %s%s'
                 % (c, settle, rate, what,
                    '' if (kind == 'beat' or n in want)
                    else '  [no source expected]'))
        for n in range(N_BEAT):
            slot = PPS_SLOT[n]
            if slot is None:
                continue
            c = self.edge_count(slot)
            name = 'pps  %2d %s' % (n, UNIT_NAMES[n])
            if not front_end:
                note(name, None, '%d edges in %.2f s  -- no front-end board'
                     % (c, settle))
            elif c > settle + 2:
                note(name, False, '%d edges in %.2f s: far too many for a 1 pps '
                     '-- chatter, or a clock on a pps input' % (c, settle))
            else:
                note(name, True if c else None, '%d edges in %.2f s%s'
                     % (c, settle, '' if c else ': no pps seen'))

        if verbose:
            self._print(results)
        return results

    @staticmethod
    def failures(results):
        """The entries that actually failed.  `ok is None` means the check
        could not be made here and is not one of them."""
        return [r for r in results if r[1] is False]

    @staticmethod
    def _print(results):
        width = max(len(r[0]) for r in results)
        bad = skipped = 0
        for name, ok, detail in results:
            bad += ok is False
            skipped += ok is None
            tag = 'ok  ' if ok else ('skip' if ok is None else 'FAIL')
            print('%s  %-*s  %s' % (tag, width, name, detail))
        print('--- %d checks, %d failures%s'
              % (len(results) - skipped, bad,
                 ', %d not testable here' % skipped if skipped else ''))


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
            already has send/receive.  The device-level drivers are in
            i2c_devices.py (round 28): wrap this in `PynqBus` and use
            `Si5351`, `TMP1075`, `Heater`/`MCP4725`, `DS2482`/`DS18B20`.
            gateware/board/bringup.py is the sequence, in the safe order."""
            return self.axi_iic_0

        @property
        def bus(self):
            """The same controller as an i2c_devices.Bus."""
            from .i2c_devices import PynqBus
            return PynqBus(self.axi_iic_0)
