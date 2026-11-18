"""
Unit tests for GPSDO DDMTD I2C drivers.
"""
import unittest
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from i2c_drivers import MockI2C, Si5351A, TMP1075, MCP4725, DS2482


class TestSi5351A(unittest.TestCase):
    def setUp(self):
        self.mock_i2c = MockI2C()
        self.si = Si5351A(self.mock_i2c)

    def test_pll_params(self):
        # 32 + 4142/1048575
        bytes_out = self.si.calc_pll_params(32, 4142, 1048575)
        self.assertEqual(len(bytes_out), 8)
        # Check P3 = 1048575 = 0x0FFFFF
        p3_reconstructed = (bytes_out[0] << 8) | bytes_out[1] | ((bytes_out[5] & 0xF0) << 12)
        self.assertEqual(p3_reconstructed, 1048575)
        # Check P1 = 128*32 - 512 = 3584 = 0x0E00
        p1_reconstructed = (bytes_out[2] << 16) | (bytes_out[3] << 8) | bytes_out[4]
        self.assertEqual(p1_reconstructed, 3584)

    def test_init_dmtd_clocks(self):
        self.si.init_dmtd_clocks()
        # Ensure writes were sent to addr 0x60
        writes = [x for x in self.mock_i2c.log if x[0] == 'W' and x[1] == 0x60]
        self.assertTrue(len(writes) > 5)
        # Verify OEB reg was set to 0xFC (CLK0 and CLK1 enabled)
        self.assertEqual(self.mock_i2c.devices[0x60][Si5351A.REG_OEB], [0xFC])


class TestTMP1075(unittest.TestCase):
    def setUp(self):
        self.mock_i2c = MockI2C()
        self.tmp = TMP1075(self.mock_i2c)

    def test_read_temp(self):
        # 25.0625 C -> raw count = 25 / 0.0625 = 401 = 0x191 -> raw = 0x1910
        # data bytes: [0x19, 0x10]
        self.mock_i2c.read = lambda addr, length: [0x19, 0x10]
        t = self.tmp.read_temp(0x48)
        self.assertAlmostEqual(t, 25.0625, places=4)

    def test_read_temp_negative(self):
        # -10.0 C -> count = -160 -> two's complement 12-bit = 4096 - 160 = 3936 = 0xF60
        # raw = 0xF600 -> bytes: [0xF6, 0x00]
        self.mock_i2c.read = lambda addr, length: [0xF6, 0x00]
        t = self.tmp.read_temp(0x48)
        self.assertAlmostEqual(t, -10.0, places=4)


class TestMCP4725(unittest.TestCase):
    def setUp(self):
        self.mock_i2c = MockI2C()
        self.dac = MCP4725(self.mock_i2c, vref=3.3)

    def test_write_fast(self):
        self.dac.write_dac_fast(2048)  # Mid-scale
        writes = [x for x in self.mock_i2c.log if x[1] == 0x61]
        self.assertEqual(writes[-1][2], [0x08, 0x00])

    def test_safe_zero_eeprom(self):
        self.dac.safe_zero_eeprom()
        writes = [x for x in self.mock_i2c.log if x[1] == 0x61]
        # Command 0x60 (write DAC and EEPROM), code 0: bytes [0x60, 0x00, 0x00]
        self.assertEqual(writes[-1][2], [0x60, 0x00, 0x00])


if __name__ == '__main__':
    unittest.main()
