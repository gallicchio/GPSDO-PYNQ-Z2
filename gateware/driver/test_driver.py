"""Tests for the parts of the driver that do not need a board.

    python3 -m unittest discover -s gateware/driver -v

The phase arithmetic and the self-consistent-read logic are where a quiet
mistake would corrupt every measurement without ever raising anything, so they
are tested against a fake device that can be made to misbehave on purpose.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from driver import (                                    # noqa: E402
    DmtdRegisters, phase_ps, wrap_cycles, unwrap_ps,
    F_HELPER, F_BEAT, N_GAIN, T_RES_PS, WRAP_PS, HELPER_CYCLES_PER_BEAT,
    N_BEAT, N_PPS, NULL_CHANNEL, PPS_SLOT, MAGIC_ID,
    REG_ID, REG_VERSION, REG_CONTROL, REG_HELPER, REG_LIVE_LO, REG_LIVE_HI,
    REG_ALIVE, REG_CHAN0, CHAN_STRIDE, OFF_TS_LO, OFF_TS_HI, OFF_COUNT,
    REG_LIVE_PS_LO, REG_LIVE_PS_HI, REG_PSCHAN0,
)
from driver.dmtd import HELPER_TICK_CYCLES, resolve_cycles   # noqa: E402


class FakeDevice(DmtdRegisters):
    """A dmtd_capture made of a dict, which can tear reads on demand."""

    def __init__(self, helper_hz=F_HELPER, ps_hz=100e6, minor=1):
        self.regs = {
            REG_ID: MAGIC_ID,
            REG_VERSION: (1 << 24) | (minor << 16) | (N_BEAT << 8) | N_PPS,
            REG_CONTROL: 0,
            REG_ALIVE: 1,
            REG_HELPER: int(round(HELPER_TICK_CYCLES * ps_hz / helper_hz)),
            REG_LIVE_LO: 0, REG_LIVE_HI: 0,
            REG_LIVE_PS_LO: 0, REG_LIVE_PS_HI: 0,
        }
        self.ps_clk_hz = ps_hz
        self.tear = 0            # number of reads still to be corrupted
        self.writes = []
        for slot in range(32):
            for base in (REG_CHAN0, REG_PSCHAN0):
                b = base + slot * CHAN_STRIDE
                self.regs[b + OFF_TS_LO] = 0
                self.regs[b + OFF_TS_HI] = 0
                self.regs[b + OFF_COUNT] = 0

    def set_ps_channel(self, slot, ts, count):
        b = REG_PSCHAN0 + slot * CHAN_STRIDE
        self.regs[b + OFF_TS_LO] = ts & 0xFFFFFFFF
        self.regs[b + OFF_TS_HI] = (ts >> 32) & 0xFFFFFFFF
        self.regs[b + OFF_COUNT] = count

    def set_pair(self, h, p):
        self.set_counter(h)
        self.regs[REG_LIVE_PS_LO] = p & 0xFFFFFFFF
        self.regs[REG_LIVE_PS_HI] = (p >> 32) & 0xFFFFFFFF

    def set_channel(self, slot, ts, count):
        b = REG_CHAN0 + slot * CHAN_STRIDE
        self.regs[b + OFF_TS_LO] = ts & 0xFFFFFFFF
        self.regs[b + OFF_TS_HI] = (ts >> 32) & 0xFFFFFFFF
        self.regs[b + OFF_COUNT] = count

    def set_counter(self, v):
        self.regs[REG_LIVE_LO] = v & 0xFFFFFFFF
        self.regs[REG_LIVE_HI] = (v >> 32) & 0xFFFFFFFF

    def read(self, off):
        v = self.regs[off]
        if self.tear:
            # Emulate the helper domain updating between two of our reads:
            # bump the count and the low word, exactly as real hardware would.
            self.tear -= 1
            for slot in range(32):
                b = REG_CHAN0 + slot * CHAN_STRIDE
                self.regs[b + OFF_COUNT] += 1
                self.regs[b + OFF_TS_LO] += 8101
            self.regs[REG_LIVE_LO] += 1024
        return v

    def write(self, off, val):
        self.writes.append((off, val))
        self.regs[off] = val


class TestPhaseArithmetic(unittest.TestCase):

    def test_one_helper_cycle_is_the_resolution(self):
        self.assertAlmostEqual(phase_ps(1, 0), T_RES_PS, places=9)

    def test_a_whole_beat_period_is_no_phase_at_all(self):
        # A full beat period of displacement is a full 10 MHz cycle, which is
        # indistinguishable from zero.
        self.assertAlmostEqual(phase_ps(HELPER_CYCLES_PER_BEAT, 0), 0.0,
                               places=6)

    def test_half_a_beat_period_is_the_wrap_point(self):
        half = HELPER_CYCLES_PER_BEAT / 2.0
        self.assertAlmostEqual(abs(phase_ps(half - 1e-9, 0)), WRAP_PS / 2,
                               places=3)

    def test_the_scale_factor_closes(self):
        # THE identity: a whole beat period of displacement is a whole input
        # cycle, because shifting an input by one period is unobservable.  The
        # two sides are derived independently -- HELPER_CYCLES_PER_BEAT from
        # F_HELPER/F_BEAT, T_RES_PS from T_helper/N_GAIN -- so this genuinely
        # cross-checks them rather than restating one in terms of the other.
        self.assertAlmostEqual(HELPER_CYCLES_PER_BEAT * T_RES_PS, WRAP_PS,
                               places=6)

    def test_the_beat_period_is_not_the_gain(self):
        # These differ by exactly one and are trivially confused; using N_GAIN
        # as the beat period is a 123 ppm scale error on every measurement,
        # which looks like nothing and is not noise.  design.py made exactly
        # this mistake.
        self.assertAlmostEqual(HELPER_CYCLES_PER_BEAT, N_GAIN + 1, places=6)
        self.assertNotAlmostEqual(HELPER_CYCLES_PER_BEAT, N_GAIN, places=3)
        self.assertAlmostEqual(HELPER_CYCLES_PER_BEAT, F_HELPER / F_BEAT,
                               places=6)

    def test_resolution_is_a_helper_period_divided_by_the_gain(self):
        # Stated the other way round, from the physics: the beat edge moves
        # N_GAIN times faster than the input phase, and it is sampled by the
        # helper, so one helper period of beat movement is one helper period
        # divided by N_GAIN of input phase.
        self.assertAlmostEqual(T_RES_PS, 1e12 / F_HELPER / N_GAIN, places=9)
        # and NOT the signal period divided by the gain
        self.assertNotAlmostEqual(T_RES_PS, 1e12 / 10e6 / N_GAIN, places=4)

    def test_wrap_is_symmetric(self):
        p = HELPER_CYCLES_PER_BEAT
        self.assertAlmostEqual(wrap_cycles(10), 10, places=9)
        self.assertAlmostEqual(wrap_cycles(10 + p), 10, places=6)
        self.assertAlmostEqual(wrap_cycles(10 - p), 10, places=6)
        self.assertAlmostEqual(wrap_cycles(-10), -10, places=9)

    def test_unwrap_recovers_a_ramp(self):
        # 3 ns per sample for 200 samples is 600 ns: six wraps.
        true = [3000.0 * i for i in range(200)]
        wrapped = [(x + WRAP_PS / 2) % WRAP_PS - WRAP_PS / 2 for x in true]
        out = unwrap_ps(wrapped)
        drift = [out[i] - (true[i] - true[0] + wrapped[0])
                 for i in range(len(true))]
        self.assertLess(max(abs(d) for d in drift), 1e-6)

    def test_unwrap_leaves_a_short_series_alone(self):
        self.assertEqual(list(unwrap_ps([42.0])), [42.0])


class TestRegisterSemantics(unittest.TestCase):

    def setUp(self):
        self.d = FakeDevice()

    def test_identity(self):
        self.assertEqual(self.d.id, MAGIC_ID)
        self.assertEqual(self.d.version, (1, 1, N_BEAT, N_PPS))
        self.assertTrue(self.d.alive)

    def test_helper_frequency(self):
        self.assertAlmostEqual(self.d.helper_hz, F_HELPER, delta=1.0)

    def test_a_stopped_helper_reads_zero_not_infinity(self):
        self.d.regs[REG_HELPER] = 0
        self.d.regs[REG_ALIVE] = 0
        self.assertEqual(self.d.helper_hz, 0.0)
        self.assertFalse(self.d.alive)

    def test_clear_writes_control_bit_zero(self):
        self.d.clear()
        self.assertEqual(self.d.writes, [(REG_CONTROL, 1)])

    def test_sixty_four_bit_values_are_reassembled(self):
        big = (12345 << 32) | 0xDEADBEEF
        self.d.set_channel(3, big, 7)
        self.assertEqual(self.d.channel(3), (7, big))
        self.d.set_counter(big)
        self.assertEqual(self.d.counter, big)

    def test_a_torn_channel_read_is_retried_not_returned(self):
        self.d.set_channel(3, 1000, 5)
        self.d.tear = 2                      # corrupt the first two reads
        count, ts = self.d.channel(3)
        # It must return a pair that belong together, not the mixture.
        b = REG_CHAN0 + 3 * CHAN_STRIDE
        self.assertEqual(count, self.d.regs[b + OFF_COUNT])
        self.assertEqual(ts & 0xFFFFFFFF, self.d.regs[b + OFF_TS_LO])

    def test_a_torn_counter_read_is_retried(self):
        self.d.set_counter(1 << 20)
        self.d.tear = 1
        v = self.d.counter
        self.assertEqual(v & 0xFFFFFFFF, self.d.regs[REG_LIVE_LO])

    def test_an_endlessly_changing_channel_raises(self):
        self.d.tear = 10 ** 6
        with self.assertRaises(RuntimeError):
            self.d.channel(0)

    def test_snapshot_covers_every_channel(self):
        for n in range(N_BEAT):
            self.d.set_channel(n, 100 * n, n)
        snap = self.d.snapshot()
        self.assertEqual(len(snap['beat_ts']), N_BEAT)
        self.assertEqual(snap['beat_ts'][5], 500)
        # the null channel has no pps, and that shows up as None
        self.assertIsNone(PPS_SLOT[NULL_CHANNEL])
        self.assertIsNone(snap['pps_ts'][NULL_CHANNEL])
        self.assertEqual(sum(1 for x in snap['pps_ts'] if x is not None), N_PPS)

    def test_phases_are_measured_against_the_null_channel(self):
        for n in range(N_BEAT):
            self.d.set_channel(n, 0, 1)
        self.d.set_channel(NULL_CHANNEL, 0, 1)
        self.d.set_channel(4, 81, 1)          # 81 helper cycles ahead
        ph = self.d.phases_ps()
        self.assertAlmostEqual(ph[NULL_CHANNEL], 0.0, places=9)
        self.assertAlmostEqual(ph[4], 81 * T_RES_PS, places=6)
        self.assertAlmostEqual(ph[0], 0.0, places=9)

    def test_pps_of_a_unit_without_one_is_an_error_not_a_wrong_number(self):
        with self.assertRaises(ValueError):
            self.d.pps(NULL_CHANNEL)

    def test_selftest_passes_on_a_healthy_fake(self):
        for n in range(32):
            self.d.set_channel(n, 0, int(F_BEAT * 0.01))
        res = self.d.selftest(settle=0.0, verbose=False)
        # settle=0 makes the edge-count checks meaningless, so only look at
        # the ones that do not depend on elapsed time
        by_name = {n: ok for n, ok, _ in res}
        self.assertTrue(by_name['ID'])
        self.assertTrue(by_name['VERSION'])
        self.assertTrue(by_name['helper running'])
        self.assertTrue(by_name['helper frequency'])

    def test_selftest_notices_the_wrong_bitstream(self):
        self.d.regs[REG_ID] = 0
        res = self.d.selftest(settle=0.0, verbose=False)
        self.assertEqual(len(res), 1)
        self.assertFalse(res[0][1])

    def test_selftest_notices_a_dead_helper(self):
        self.d.regs[REG_ALIVE] = 0
        self.d.regs[REG_HELPER] = 0
        res = dict((n, ok) for n, ok, _ in
                   self.d.selftest(settle=0.0, verbose=False))
        self.assertFalse(res['helper running'])
        self.assertFalse(res['helper frequency'])

    def test_selftest_without_a_front_end_does_not_call_beats_failures(self):
        """ROUND 30.  The squarers and the flip-flops that make a beat are on
        the front-end board.  Run against a bare PYNQ with only a Si5351 wired
        to the header, every beat reads ~0 edges -- which is the right answer,
        not fourteen failures."""
        res = self.d.selftest(settle=0.0, verbose=False, front_end=False)
        by = {n: ok for n, ok, _ in res}
        self.assertTrue(by['helper frequency'])
        beats = [ok for n, ok in by.items() if n.startswith('beat')]
        self.assertEqual(len(beats), N_BEAT)
        self.assertTrue(all(ok is None for ok in beats))
        pps = [ok for n, ok in by.items() if n.startswith('pps')]
        self.assertTrue(all(ok is None for ok in pps))
        # ...and none of them counts as a failure
        self.assertEqual(self.d.failures(res), [])

    def test_failures_ignores_the_not_testable_ones(self):
        res = [('a', True, ''), ('b', False, ''), ('c', None, '')]
        self.assertEqual([r[0] for r in self.d.failures(res)], ['b'])

    def test_settle_helper_waits_out_a_straddling_window(self):
        """ROUND 30.  The estimator latches the window that has just finished,
        so the one spanning the moment the synthesiser starts reads LOW by
        however much of it had no clock in it.  On silicon that was 8.15 MHz
        for a 10.0012 MHz helper.  settle_helper polls until two consecutive
        windows agree."""
        good = int(round(HELPER_TICK_CYCLES * 100e6 / F_HELPER))
        straddled = int(good * 1.227)          # the window round 30 actually saw
        seq = [straddled, good, good, good]
        self.d.regs[REG_HELPER] = seq[0]

        calls = {'n': 0}
        real_read = self.d.read

        def read(off):
            if off == REG_HELPER:
                i = min(calls['n'], len(seq) - 1)
                calls['n'] += 1
                return seq[i]
            return real_read(off)

        self.d.read = read
        hz = self.d.settle_helper(timeout=2.0)
        self.assertAlmostEqual(hz, F_HELPER, delta=F_HELPER * 1e-4)
        self.assertGreaterEqual(calls['n'], 3)   # it did not believe the first

    def test_settle_helper_gives_up_on_a_dead_helper(self):
        self.d.regs[REG_HELPER] = 0
        self.assertEqual(self.d.settle_helper(timeout=0.3), 0.0)

    def test_selftest_notices_a_helper_on_the_wrong_frequency(self):
        # 10.000000 MHz instead of 10.0012344: the Si5351 programmed wrong,
        # which would silently give a 12000x wrong scale factor.
        self.d.regs[REG_HELPER] = int(round(HELPER_TICK_CYCLES * 100e6 / 10e6))
        res = dict((n, ok) for n, ok, _ in
                   self.d.selftest(settle=0.0, verbose=False))
        self.assertFalse(res['helper frequency'])


class TestPpsPsTimestamps(unittest.TestCase):
    """Gateware 1.1: the PS-domain pps stamps, the pair, and the integer."""

    def test_pre_1_1_gateware_reports_no_ps_timestamps(self):
        d = FakeDevice(minor=0)
        self.assertFalse(d.has_ps_timestamps)
        snap = d.snapshot()
        self.assertTrue(all(t is None for t in snap['pps_ps_ts']))
        self.assertNotIn('pair', snap)

    def test_pps_offsets_are_ten_ns_per_tick(self):
        d = FakeDevice()
        d.set_ps_channel(PPS_SLOT[0], 1000, 5)
        d.set_ps_channel(PPS_SLOT[1], 1000 + 37, 5)      # 370 ns later
        d.set_ps_channel(PPS_SLOT[3], 1000 - 2, 5)       # 20 ns earlier
        off = d.pps_offsets_ns(reference=0)
        self.assertAlmostEqual(off[1], 370.0)
        self.assertAlmostEqual(off[3], -20.0)
        self.assertIsNone(off[2])                        # no edge counted yet
        self.assertIsNone(off[NULL_CHANNEL])             # unit 13 has no pps

    def test_pair_maps_ps_onto_helper(self):
        d = FakeDevice()
        d.set_pair(h=1_000_000, p=5_000_000)
        # 9998.8 PS ticks later is 1000 helper cycles later
        h = d.ps_to_helper_cycles(5_000_000 + 9998.8, helper_hz=F_HELPER)
        self.assertAlmostEqual(h, 1_001_000.0, delta=0.01)

    def test_resolve_cycles(self):
        # fine says +30 ns (mod 100), coarse says +2.33 us: 23 cycles, 30 ns
        ph, n, res = resolve_cycles(30_000.0, 2_330_000.0)
        self.assertEqual(n, 23)
        self.assertAlmostEqual(ph, 2_330_000.0)
        self.assertAlmostEqual(res, 0.0)
        # coarse is 10 ns quantised and 40 ns off: still the same integer
        ph, n, res = resolve_cycles(30_000.0, 2_370_000.0)
        self.assertEqual(n, 23)
        self.assertAlmostEqual(res, 40_000.0)
        # negative
        ph, n, res = resolve_cycles(-45_000.0, -145_000.0)
        self.assertEqual(n, -1)
        self.assertAlmostEqual(ph, -145_000.0)

    def test_absolute_phases_combine_beat_and_pps(self):
        d = FakeDevice()
        # beats: channel 1 is 8102.1/4 helper cycles behind the null -> +25 ns
        quarter = HELPER_CYCLES_PER_BEAT / 4.0
        d.set_channel(NULL_CHANNEL, 500_000, 1)
        d.set_channel(1, 500_000 + int(round(quarter)), 1)
        d.set_channel(0, 500_000, 1)
        # pps: channel 1's pps 3.02 us after channel 0's; null has none
        d.set_ps_channel(PPS_SLOT[0], 700_000, 1)
        d.set_ps_channel(PPS_SLOT[1], 700_000 + 302, 1)
        out = d.absolute_phases_ps(reference=0)
        self.assertIsNone(out[NULL_CHANNEL])
        ph, n, res = out[1]
        self.assertEqual(n, 30)                           # 3.02 us = 30 cycles + 20 ns
        self.assertAlmostEqual(ph, 3_000_000.0 + 25_000.0, delta=T_RES_PS)


if __name__ == '__main__':
    unittest.main(verbosity=2)
