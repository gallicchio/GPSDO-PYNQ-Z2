"""
Production-ready I2C drivers for the GPSDO-PYNQ-Z2 board peripherals.

Peripherals covered:
1. Si5351A-B-GT Clock Generator (I2C address 0x60):
   - Generates 10.0012344 MHz helper clock on CLK0
   - Generates 10.0000000 MHz reference/null clock on CLK1
   - Configures PLL A (fractional) and PLL B (integer)
2. TMP1075 Temperature Sensors (I2C addresses 0x48 - 0x4F):
   - Reads all 8 on-board temperature sensors with 0.0625 degC resolution
3. MCP4725 12-bit DAC (I2C address 0x61):
   - Controls heater pass-FET drive voltage
   - Programs EEPROM to default 0V at power-on to prevent heater runaway
4. DS2482-100 1-Wire Bridge (I2C address 0x18):
   - 1-Wire master interface
   - Reads DS18B20 external temperature probes
"""

import time
import struct

class I2CInterface:
    """Abstract interface or wrapper for PYNQ AxiIIC or SMBus."""
    def write(self, addr, data):
        raise NotImplementedError
    def read(self, addr, length):
        raise NotImplementedError
    def write_then_read(self, addr, write_data, read_length):
        raise NotImplementedError

class PynqAxiIIC(I2CInterface):
    """Driver wrapper for PYNQ AxiIIC IP."""
    def __init__(self, axi_iic_ip):
        self.iic = axi_iic_ip

    def write(self, addr, data):
        self.iic.send(addr, bytes(data), len(data))

    def read(self, addr, length):
        buf = bytearray(length)
        self.iic.receive(addr, buf, length)
        return list(buf)

    def write_then_read(self, addr, write_data, read_length):
        self.write(addr, write_data)
        return self.read(addr, read_length)

class MockI2C(I2CInterface):
    """In-memory mock I2C bus for host testing without hardware."""
    def __init__(self):
        self.devices = {}
        self.log = []

    def write(self, addr, data):
        self.log.append(('W', addr, list(data)))
        if addr not in self.devices:
            self.devices[addr] = {}
        dev = self.devices[addr]
        reg = data[0]
        dev[reg] = list(data[1:])

    def read(self, addr, length):
        self.log.append(('R', addr, length))
        return [0] * length

    def write_then_read(self, addr, write_data, read_length):
        self.write(addr, write_data)
        return self.read(addr, read_length)


# ===========================================================================
# 1. Si5351A Synthesizer Driver
# ===========================================================================
class Si5351A:
    """
    Silicon Labs Si5351A-B-GT Clock Generator.
    Address: 0x60 (MSOP-10 package has no A0 pin).
    """
    ADDR = 0x60

    REG_DEVICE_STATUS = 0
    REG_OEB = 3
    REG_CLK0_CTRL = 16
    REG_CLK1_CTRL = 17
    REG_CLK2_CTRL = 18
    REG_SYNTH_PLL_A = 26
    REG_SYNTH_PLL_B = 34
    REG_MS0_BASE = 42
    REG_MS1_BASE = 50
    REG_PLL_RESET = 177
    REG_XTAL_CL = 183

    def __init__(self, i2c, ref_clk_hz=25000000.0):
        self.i2c = i2c
        self.ref_clk_hz = ref_clk_hz

    def write_reg(self, reg, val):
        self.i2c.write(self.ADDR, [reg, val & 0xFF])

    def write_bulk(self, start_reg, values):
        self.i2c.write(self.ADDR, [start_reg] + [v & 0xFF for v in values])

    def calc_pll_params(self, mult, num, denom):
        """
        AN619 Section 3.2: PLL parameter generation.
        Feedback divider = mult + num/denom.
        """
        P1 = 128 * mult + int(128 * num / denom) - 512
        P2 = 128 * num - denom * int(128 * num / denom)
        P3 = denom
        return [
            (P3 >> 8) & 0xFF,
            P3 & 0xFF,
            (P1 >> 16) & 0x03,
            (P1 >> 8) & 0xFF,
            P1 & 0xFF,
            ((P3 >> 12) & 0xF0) | ((P2 >> 16) & 0x0F),
            (P2 >> 8) & 0xFF,
            P2 & 0xFF,
        ]

    def calc_ms_params(self, div, num=0, denom=1):
        """
        AN619 Section 3.2: MultiSynth parameter generation.
        In integer mode (num=0), div is an integer.
        """
        if num == 0:
            P1 = 128 * div - 512
            P2 = 0
            P3 = 1
        else:
            P1 = 128 * div + int(128 * num / denom) - 512
            P2 = 128 * num - denom * int(128 * num / denom)
            P3 = denom
        return [
            (P3 >> 8) & 0xFF,
            P3 & 0xFF,
            (P1 >> 16) & 0x03,
            (P1 >> 8) & 0xFF,
            P1 & 0xFF,
            ((P3 >> 12) & 0xF0) | ((P2 >> 16) & 0x0F),
            (P2 >> 8) & 0xFF,
            P2 & 0xFF,
        ]

    def init_dmtd_clocks(self):
        """
        Configure Si5351 for GPSDO DDMTD operation:
        - Input: 25.0 MHz TCXO on XA
        - PLL A: 25 MHz * (32 + 4142/1048575) = 800.098753 MHz
        - CLK0: MultiSynth 0 = 80 (Integer mode) -> 10.0012344 MHz (Helper clock)
        - PLL B: 25 MHz * 32 = 800.000000 MHz (Integer mode)
        - CLK1: MultiSynth 1 = 80 (Integer mode) -> 10.0000000 MHz (Null channel test clock)
        """
        self.write_reg(self.REG_OEB, 0xFF)
        self.write_reg(self.REG_CLK2_CTRL, 0x80)
        self.write_reg(self.REG_XTAL_CL, 0x52)

        # 1. Program PLL A (Fractional: 32 + 4142/1048575) -> 800.098753 MHz
        plla_bytes = self.calc_pll_params(32, 4142, 1048575)
        self.write_bulk(self.REG_SYNTH_PLL_A, plla_bytes)

        # 2. Program PLL B (Integer: 32) -> 800.000000 MHz for Null Channel reference
        pllb_bytes = self.calc_pll_params(32, 0, 1)
        self.write_bulk(self.REG_SYNTH_PLL_B, pllb_bytes)

        # 3. Program MultiSynth 0 (Integer: div 80) -> CLK0 = 10.0012344 MHz
        ms0_bytes = self.calc_ms_params(80, 0, 1)
        self.write_bulk(self.REG_MS0_BASE, ms0_bytes)

        # 4. Program MultiSynth 1 (Integer: div 80 from PLL B) -> CLK1 = 10.0000000 MHz
        ms1_bytes = self.calc_ms_params(80, 0, 1)
        self.write_bulk(self.REG_MS1_BASE, ms1_bytes)

        # 5. Configure CLK0 control: Powered on, integer mode, PLL A source, 8mA drive
        self.write_reg(self.REG_CLK0_CTRL, 0x4F)

        # 6. Configure CLK1 control: Powered on, integer mode, PLL B source, 8mA drive
        self.write_reg(self.REG_CLK1_CTRL, 0x6F)

        # 7. Soft reset both PLLs to align phase
        self.write_reg(self.REG_PLL_RESET, 0xAC)

        # 8. Enable CLK0 and CLK1 outputs (OEB bits 0 and 1 low)
        self.write_reg(self.REG_OEB, 0xFC)


# ===========================================================================
# 2. TMP1075 Temperature Sensors Driver
# ===========================================================================
class TMP1075:
    """
    Texas Instruments TMP1075 High-Accuracy Digital Temperature Sensor.
    8 devices on bus at addresses 0x48 to 0x4F.
    """
    REG_TEMP = 0x00
    REG_CONFIG = 0x01

    LOCATIONS = {
        0x48: "Corner NW",
        0x49: "Corner NE",
        0x4A: "Corner SW",
        0x4B: "Corner SE",
        0x4C: "Helper Fan-out Cluster",
        0x4D: "Beside 3.3V LDOs",
        0x4E: "Channel 00 (TM-4) Squarer",
        0x4F: "Channel 12 (Null) Squarer",
    }

    def __init__(self, i2c):
        self.i2c = i2c

    def read_temp(self, addr):
        """Read temperature in degrees Celsius from a specific sensor."""
        data = self.i2c.write_then_read(addr, [self.REG_TEMP], 2)
        raw = (data[0] << 8) | data[1]
        count = raw >> 4
        if count & 0x800:
            count -= 4096
        return count * 0.0625

    def read_all(self):
        """Read all 8 sensors, returning a dict of {addr: (location, temp_c)}."""
        results = {}
        for addr, loc in self.LOCATIONS.items():
            try:
                t = self.read_temp(addr)
                results[addr] = (loc, t)
            except Exception as e:
                results[addr] = (loc, None)
        return results


# ===========================================================================
# 3. MCP4725 DAC Driver (Heater Control)
# ===========================================================================
class MCP4725:
    """
    Microchip MCP4725 12-bit DAC with EEPROM.
    Address: 0x61 (A0 strapped high to +3V3_D to avoid 0x60 collision with Si5351).
    """
    ADDR = 0x61

    def __init__(self, i2c, vref=3.3):
        self.i2c = i2c
        self.vref = vref

    def write_dac_fast(self, code):
        """Fast mode write (does not write EEPROM)."""
        code = max(0, min(4095, int(code)))
        b1 = (code >> 8) & 0x0F
        b2 = code & 0xFF
        self.i2c.write(self.ADDR, [b1, b2])

    def write_dac_and_eeprom(self, code):
        """
        Write DAC register AND non-volatile EEPROM.
        Critical: Use at bring-up with code=0 so board powers up cold!
        """
        code = max(0, min(4095, int(code)))
        cmd = 0x60
        b1 = (code >> 4) & 0xFF
        b2 = (code & 0x0F) << 4
        self.i2c.write(self.ADDR, [cmd, b1, b2])

    def set_voltage(self, volts, update_eeprom=False):
        code = int(round((volts / self.vref) * 4095.0))
        if update_eeprom:
            self.write_dac_and_eeprom(code)
        else:
            self.write_dac_fast(code)

    def safe_zero_eeprom(self):
        """Ensure DAC powers up at 0V (heater fully OFF)."""
        self.write_dac_and_eeprom(0)


# ===========================================================================
# 4. DS2482-100 1-Wire Master Bridge Driver (DS18B20 Probes)
# ===========================================================================
class DS2482:
    """
    Analog Devices / Maxim DS2482-100 Single-Channel 1-Wire Master Bridge.
    Address: 0x18 (AD0=0, AD1=0).
    """
    ADDR = 0x18

    CMD_DRST = 0xF0     # Device Reset
    CMD_WCFG = 0xD2     # Write Configuration
    CMD_1WRS = 0xB4     # 1-Wire Reset
    CMD_1WWB = 0xA5     # 1-Wire Write Byte
    CMD_1WRB = 0x96     # 1-Wire Read Byte
    CMD_1WT  = 0x78     # 1-Wire Triplet

    STATUS_1WB = 0x01   # 1-Wire Busy
    STATUS_PPD = 0x02   # Presence Pulse Detected

    def __init__(self, i2c):
        self.i2c = i2c

    def reset_bridge(self):
        self.i2c.write(self.ADDR, [self.CMD_DRST])
        cfg = 0x00
        val = (cfg & 0x0F) | ((~cfg & 0x0F) << 4)
        self.i2c.write(self.ADDR, [self.CMD_WCFG, val])

    def wait_idle(self, timeout=0.05):
        t0 = time.time()
        while time.time() - t0 < timeout:
            status = self.i2c.read(self.ADDR, 1)[0]
            if not (status & self.STATUS_1WB):
                return status
            time.sleep(0.001)
        raise TimeoutError("DS2482 1-Wire bus busy timeout")

    def reset_1wire(self):
        self.i2c.write(self.ADDR, [self.CMD_1WRS])
        status = self.wait_idle()
        return bool(status & self.STATUS_PPD)

    def write_byte(self, b):
        self.i2c.write(self.ADDR, [self.CMD_1WWB, b & 0xFF])
        self.wait_idle()

    def read_byte(self):
        self.i2c.write(self.ADDR, [self.CMD_1WRB])
        self.wait_idle()
        self.i2c.write(self.ADDR, [0xE1, 0xE1])  # Set read pointer to read data register
        return self.i2c.read(self.ADDR, 1)[0]

    def read_probes_simple(self):
        if not self.reset_1wire():
            return None
        self.write_byte(0xCC)   # Skip ROM
        self.write_byte(0x44)   # Convert T
        time.sleep(0.8)         # 12-bit conversion delay
        if not self.reset_1wire():
            return None
        self.write_byte(0xCC)   # Skip ROM
        self.write_byte(0xBE)   # Read Scratchpad
        t_lo = self.read_byte()
        t_hi = self.read_byte()
        raw = (t_hi << 8) | t_lo
        if raw & 0x8000:
            raw -= 65536
        return raw * 0.0625
