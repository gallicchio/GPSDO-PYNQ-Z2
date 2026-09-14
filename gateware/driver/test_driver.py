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
)
from driver.dmtd import HELPER_TICK_CYCLES               # noqa: E402


class FakeDevice(DmtdRegisters):
    """A dmtd_capture made of a dict, which can tear reads on demand."""

    def __init__(self, helper_hz=F_HELPER, ps_hz=100e6):
        self.regs = {
            REG_ID: MAGIC_ID,
            REG_VERSION: (1 << 24) | (0 << 16) | (N_BEAT << 8) | N_PPS,
            REG_CONTROL: 0,
            REG_ALIVE: 1,
            REG_HELPER: int(round(HELPER_TICK_CYCLES * ps_hz / helper_hz)),
            REG_LIVE_LO: 0, REG_LIVE_HI: 0,
        }
        self.ps_clk_hz = ps_hz
        self.tear = 0            # number of reads still to be corrupted
        self.writes = []
        for slot in range(32):
            b = REG_CHAN0 + slot * CHAN_STRIDE
            self.regs[b + OFF_TS_LO] = 0
            self.regs[b + OFF_TS_HI] = 0
            self.regs[b + OFF_COUNT] = 0

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
        self.assertEqual(self.d.version, (1, 0, N_BEAT, N_PPS))
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

    def test_selftest_notices_a_helper_on_the_wrong_frequency(self):
        # 10.000000 MHz instead of 10.0012344: the Si5351 programmed wrong,
        # which would silently give a 12000x wrong scale factor.
        self.d.regs[REG_HELPER] = int(round(HELPER_TICK_CYCLES * 100e6 / 10e6))
        res = dict((n, ok) for n, ok, _ in
                   self.d.selftest(settle=0.0, verbose=False))
        self.assertFalse(res['helper frequency'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
