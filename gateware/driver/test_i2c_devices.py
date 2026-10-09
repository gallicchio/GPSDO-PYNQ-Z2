"""Host tests for the I2C device drivers: register images against the
datasheet formulas, and the bring-up order against a mock bus.

    python3 -m unittest discover -s gateware/driver -v
"""
import os
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from driver.i2c_devices import (                        # noqa: E402
    MockBus, Si5351, Si5351Config, TMP1075, MCP4725, Heater, DS2482, DS18B20,
    plan_pll, ms_params, ms_registers, decode_ms, trim_fraction, crc8_maxim,
    scan, EXPECTED_DEVICES, REG_MSNA, REG_MSNB, REG_MS0, REG_MS1,
    REG_CLK_CTRL, REG_OEB, REG_PLL_RESET, REG_XTAL_CL, REG_PLL_SRC,
    CLK_PDN, CLK_PLLB, CLK_IDRV_2MA, REG_MS2,
)
from driver import F_HELPER, F_BEAT                     # noqa: E402


class TestSi5351Image(unittest.TestCase):

    def test_pll_ratio_is_exact_for_the_board(self):
        a, b, c, fvco = plan_pll(25e6, F_HELPER, 80)
        self.assertEqual((a, b, c), (32, 1543, 390625))
        self.assertAlmostEqual(fvco / 80, F_HELPER, places=6)

    def test_the_schematics_fraction_is_close_but_not_exact(self):
        f = 25e6 * (32 + 4142 / 1048575) / 80
        self.assertLess(abs(f - F_HELPER), 0.02)        # 10 ppb, which nobody would notice
        self.assertNotEqual(f, F_HELPER)

    def test_ms_params_match_an619(self):
        # AN619 3.2: P1 = 128a + floor(128b/c) - 512, P2 = 128b - c*floor(128b/c), P3 = c
        a, b, c = 32, 1543, 390625
        p1, p2, p3 = ms_params(a, b, c)
        f = (128 * b) // c
        self.assertEqual(p1, 128 * a + f - 512)
        self.assertEqual(p2, 128 * b - c * f)
        self.assertEqual(p3, c)
        # integer divider 80: P1 = 128*80 - 512 = 9728, P2 = 0, P3 = 1
        self.assertEqual(ms_params(80, 0, 1), (9728, 0, 1))

    def test_register_layout_round_trips(self):
        for a, b, c in ((32, 1543, 390625), (32, 0, 1), (80, 0, 1), (35, 1, 3)):
            regs = ms_registers(100, *ms_params(a, b, c))
            self.assertEqual(decode_ms(regs, 100), Fraction(a) + Fraction(b, c))

    def test_config_registers(self):
        cfg = Si5351Config()
        r = cfg.registers()
        self.assertEqual(decode_ms(r, REG_MSNA), Fraction(32) + Fraction(1543, 390625))
        self.assertEqual(decode_ms(r, REG_MSNB), Fraction(32))
        self.assertEqual(decode_ms(r, REG_MS0), Fraction(80))
        self.assertEqual(decode_ms(r, REG_MS1), Fraction(80))
        # ROUNDS 39-40: the helper at 2 mA -- at 8 mA, and at 4 mA once HO
        # drives a 50 ohm cable, fractional PLLA cycle-slipped hundreds of
        # times a second on the first board; the null source stays 8 mA.
        self.assertEqual(r[REG_CLK_CTRL + 0], 0x4C)     # INT, PLLA, MS source, 2 mA
        self.assertEqual(r[REG_CLK_CTRL + 1], 0x6F)     # INT, PLLB, MS source, 8 mA
        self.assertEqual(r[REG_CLK_CTRL + 2], 0x80)     # CLK2 powered down
        self.assertEqual(r[REG_PLL_SRC], 0x00)          # XTAL for both PLLs
        self.assertEqual(r[REG_XTAL_CL], 0xC0 | 0x12)   # 10 pF + reserved 010010b
        self.assertEqual(r[REG_MS0 + 2] >> 4, 0)         # R0 = 1
        f0, f1 = cfg.expected()
        self.assertAlmostEqual(f0, F_HELPER, places=6)
        self.assertAlmostEqual(f1, 10e6, places=6)
        self.assertAlmostEqual(f0 - f1, F_BEAT, places=6)

    def test_null_clock_must_be_integer(self):
        with self.assertRaises(ValueError):
            Si5351Config(f_null=10_000_100.0)

    def test_program_order(self):
        bus = MockBus()
        chip = Si5351(bus)
        cfg = Si5351Config()
        chip.program(cfg)
        writes = [(a, d) for op, a, d in bus.log if op == 'W' and a == 0x60]
        regs_in_order = [d[0] for a, d in writes]
        # AN619 figure 12: OEB=0xFF first, drivers down, image, reset, OEB last
        self.assertEqual(writes[0][1], bytes([REG_OEB, 0xFF]))
        self.assertEqual(writes[1][1], bytes([REG_CLK_CTRL, 0x80]))
        self.assertEqual(writes[-2][1], bytes([REG_PLL_RESET, 0xAC]))
        self.assertEqual(writes[-1][1], bytes([REG_OEB, 0xFC]))
        self.assertLess(regs_in_order.index(REG_MSNA), regs_in_order.index(REG_PLL_RESET))
        # and the mock's register file now holds the image
        self.assertEqual(chip.verify(cfg), {})

    def test_trim_moves_the_fraction_by_the_measured_ratio(self):
        a, b, c = 32, 1543, 390625
        # helper measured 0.5 Hz high: the new ratio must be lower by 0.5/f
        a2, b2, c2 = trim_fraction(a, b, c, F_HELPER + 0.5, F_HELPER)
        r_old = Fraction(a) + Fraction(b, c)
        r_new = Fraction(a2) + Fraction(b2, c2)
        self.assertAlmostEqual(float(r_new / r_old), F_HELPER / (F_HELPER + 0.5), places=12)
        self.assertLessEqual(c2, 1048575)


class TestTMP1075(unittest.TestCase):

    def test_decode(self):
        # datasheet table: 0010h = +0.0625, FFF0h = -0.0625, 1900h = +25
        self.assertAlmostEqual(TMP1075.decode(0x00, 0x10), 0.0625)
        self.assertAlmostEqual(TMP1075.decode(0xFF, 0xF0), -0.0625)
        self.assertAlmostEqual(TMP1075.decode(0x19, 0x00), 25.0)
        self.assertAlmostEqual(TMP1075.decode(0x7F, 0xF0), 127.9375)

    def test_read_uses_pointer_zero(self):
        bus = MockBus()
        bus.regs[0x4A][0] = 0x1900
        self.assertAlmostEqual(TMP1075(bus, 0x4A).read_c(), 25.0)
        self.assertEqual(bus.log[0], ('W', 0x4A, b'\x00'))


class TestMCP4725(unittest.TestCase):

    def test_frame(self):
        # datasheet 6.1.2: C2C1C0=011 write DAC+EEPROM, PD in bits 2:1, then D11..D4, D3..D0<<4
        self.assertEqual(MCP4725.frame(MCP4725.CMD_WRITE_DAC_EEPROM, 0, pd=1), bytes([0x62, 0x00, 0x00]))
        self.assertEqual(MCP4725.frame(MCP4725.CMD_WRITE_DAC, 0xFFF, pd=0), bytes([0x40, 0xFF, 0xF0]))
        self.assertEqual(MCP4725.frame(MCP4725.CMD_WRITE_DAC, 0x800, pd=0), bytes([0x40, 0x80, 0x00]))

    def test_read_decodes_factory_default(self):
        bus = MockBus()
        # as shipped: EEPROM PD=00, D11=1 -> mid scale; DAC register follows it
        bus.regs[0x61]['readback'] = bytes([0x80, 0x80, 0x00, 0x08, 0x00])
        rb = MCP4725(bus).read()
        self.assertEqual(rb['eeprom_code'], 0x800)
        self.assertEqual(rb['eeprom_pd'], 0)
        self.assertEqual(rb['code'], 0x800)
        self.assertTrue(rb['ready'])

    def test_make_safe_writes_eeprom_zero_with_pulldown(self):
        bus = MockBus()
        bus.regs[0x61]['readback'] = bytes([0x80, 0x80, 0x00, 0x08, 0x00])
        h = Heater(MCP4725(bus))
        h.make_safe()
        w = [d for op, a, d in bus.log if op == 'W' and a == 0x61]
        self.assertIn(bytes([0x62, 0x00, 0x00]), w)          # EEPROM := 0, PD=01
        self.assertEqual(w[-1], bytes([0x42, 0x00, 0x00]))   # and DAC off now

    def test_heater_refuses_fast_pwm(self):
        with self.assertRaises(ValueError):
            Heater.duty_cycle(0.5, period_s=1.0)
        self.assertEqual(Heater.duty_cycle(0.25, 40.0), (10.0, 30.0))

    def test_general_call_reset(self):
        bus = MockBus()
        MCP4725(bus).general_call_reset()
        self.assertEqual(bus.log[-1], ('W', 0x00, b'\x06'))


class TestDS2482(unittest.TestCase):

    def test_config_byte_has_complement_in_upper_nibble(self):
        bus = MockBus()
        bus.regs[0x18]['readback'] = bytes([0x01])
        self.assertTrue(DS2482(bus).write_config(apu=True))
        self.assertEqual(bus.log[0], ('W', 0x18, bytes([0xD2, 0xE1])))

    def test_crc8(self):
        # CRC of the 7 leading bytes of a ROM must equal its 8th byte.  Built
        # from the definition (poly x^8+x^5+x^4+1, LSB first) with an
        # independent table implementation.
        table = []
        for i in range(256):
            c = i
            for _ in range(8):
                c = (c >> 1) ^ 0x8C if c & 1 else c >> 1
            table.append(c)

        def by_table(data):
            crc = 0
            for b in data:
                crc = table[crc ^ b]
            return crc
        for rom in (bytes([0x28, 0xFF, 0x64, 0x1E, 0x0F, 0x9C, 0xA1]),
                    bytes(range(7)), bytes([0x28] + [0] * 6)):
            self.assertEqual(crc8_maxim(rom), by_table(rom))
        self.assertEqual(crc8_maxim(b''), 0)

    def test_scratchpad_decode(self):
        self.assertAlmostEqual(DS18B20.decode_scratchpad(bytes([0x91, 0x01]) + bytes(7)), 25.0625)
        self.assertAlmostEqual(DS18B20.decode_scratchpad(bytes([0x5E, 0xFF]) + bytes(7)), -10.125)


class TestScan(unittest.TestCase):

    def test_scan_finds_exactly_the_board(self):
        self.assertEqual(scan(MockBus()), sorted(EXPECTED_DEVICES))

    def test_scan_of_an_empty_bus(self):
        self.assertEqual(scan(MockBus(present=[])), [])


if __name__ == '__main__':
    unittest.main()

class TestSi5351Sticky(unittest.TestCase):
    """ROUND 41: the latched status flags, for a multi-day log."""

    def test_sticky_decodes_register_1_and_clear_writes_zero(self):
        bus = MockBus()
        chip = Si5351(bus)
        bus.regs[Si5351.ADDR][1] = 0x20 | 0x10          # LOL_A, LOS_CLKIN
        st = chip.sticky()
        self.assertTrue(st['lol_a'])
        self.assertFalse(st['lol_b'])
        self.assertTrue(st['los_clkin'])
        chip.clear_sticky()
        self.assertEqual(bus.regs[Si5351.ADDR][1], 0x00)
        self.assertFalse(chip.sticky()['lol_a'])


class TestClk2Witness(unittest.TestCase):
    """ROUND 30.  CLK2 is not routed on the front-end board, so it stays off
    there -- but on the bench it is the only way to see the beat without a
    board, and the ADALM2000 is already on it."""

    def test_off_is_the_default_and_powers_the_driver_down(self):
        cfg = Si5351Config()
        self.assertEqual(cfg.clk2, 'off')
        self.assertIsNone(cfg.expected_clk2())
        self.assertEqual(cfg.registers()[REG_CLK_CTRL + 2], CLK_PDN)
        self.assertEqual(cfg.oeb(), 0xFC)          # CLK0, CLK1 enabled only

    def test_helper_copies_clk0_off_plla(self):
        cfg = Si5351Config(clk2='helper')
        f0, f1 = cfg.expected()
        self.assertAlmostEqual(cfg.expected_clk2(), f0, places=3)
        ctrl = cfg.registers()[REG_CLK_CTRL + 2]
        self.assertFalse(ctrl & CLK_PDN)
        self.assertFalse(ctrl & CLK_PLLB)          # PLLA, like CLK0
        self.assertEqual(cfg.oeb(), 0xF8)          # CLK0, CLK1, CLK2 enabled
        # ...and the beat the instrument is built on is what you would see
        self.assertAlmostEqual(abs(cfg.expected_clk2() - f1), F_BEAT, places=3)

    def test_null_copies_clk1_off_pllb(self):
        cfg = Si5351Config(clk2='null')
        self.assertEqual(cfg.expected_clk2(), cfg.expected()[1])
        self.assertTrue(cfg.registers()[REG_CLK_CTRL + 2] & CLK_PLLB)

    def test_rev_b_image(self):
        """Rev B (items 9, 10): PLLs from CLKIN, HO on CLK2 at 2 mA, CLK1 off."""
        a, b = Si5351Config(), Si5351Config(rev='B')
        rb = b.registers()
        self.assertEqual(rb[REG_PLL_SRC], 0x0C)
        self.assertEqual(a.registers()[REG_PLL_SRC], 0x00)
        self.assertEqual(rb[REG_CLK_CTRL + 1], CLK_PDN)
        self.assertEqual(rb[REG_CLK_CTRL + 2] & 0x03, CLK_IDRV_2MA)
        self.assertTrue(rb[REG_CLK_CTRL + 2] & CLK_PLLB)
        self.assertEqual(rb[REG_CLK_CTRL + 0], a.registers()[REG_CLK_CTRL + 0])
        for reg in range(REG_MSNA, REG_MS0 + 8):          # same PLL and helper plan
            self.assertEqual(rb[reg], a.registers()[reg])
        for k in range(8):                                # HO's MultiSynth = CLK1's on rev A
            self.assertEqual(rb[REG_MS2 + k], a.registers()[REG_MS1 + k])
        self.assertNotIn(REG_MS1, rb)
        self.assertEqual(b.oeb(), 0xFA)
        self.assertEqual(b.expected(), a.expected())
        self.assertAlmostEqual(b.expected_clk2(), 10e6, places=3)
        with self.assertRaises(ValueError):
            Si5351Config(rev='B', clk2='helper')
        with self.assertRaises(ValueError):
            Si5351Config(rev='C')

    def test_clk2_ms_registers_only_appear_when_it_is_on(self):
        from driver.i2c_devices import REG_MS2
        self.assertNotIn(REG_MS2, Si5351Config().registers())
        self.assertIn(REG_MS2, Si5351Config(clk2='helper').registers())

    def test_a_bad_choice_is_refused(self):
        with self.assertRaises(ValueError):
            Si5351Config(clk2='clk2')

    def test_program_enables_exactly_the_outputs_the_config_asks_for(self):
        from driver.i2c_devices import REG_OEB
        for choice, want in (('off', 0xFC), ('helper', 0xF8)):
            bus = MockBus()
            chip = Si5351(bus)
            chip.program(Si5351Config(clk2=choice))
            self.assertEqual(bus.regs[Si5351.ADDR][REG_OEB], want, choice)

