"""The four I2C parts on the front-end board, and the one sequence that brings
them up safely.

    Si5351A   0x60   the helper (CLK0, PLLA) and the null source (CLK1, PLLB)
    TMP1075   0x48-0x4F   eight board thermometers, address = position
    MCP4725   0x61   the heater DAC -- and the reason for the ORDER below
    DS2482    0x18   I2C-to-1-Wire bridge for the five DS18B20 probes

Written in round 28, from the datasheets and AN619 in ../../datasheets/, and
tested on a host against register-image checks (test_i2c_devices.py).  It has
NOT yet been run against a real Si5351A: the first fabricated board is where
that happens, which is why every device here has a readback that bringup.py
prints rather than trusts.

WHY THE DAC COMES FIRST.  The MCP4725 ships with its EEPROM at MID-SCALE
(datasheet Table 5-3: PD = 00, D11 = 1), so a virgin board puts 1.65 V on the
three heater-FET gates the moment it is powered.  `Heater.make_safe()` writes
the EEPROM to 0 with PD = 01 once; after that the part powers up off forever.
`bringup.py` does this before it touches anything else, and the 15 V jack must
stay unplugged until it has run once on a given board.

WHY THE HEATER IS ON/OFF, NOT PROPORTIONAL.  The three pass FETs share one
gate voltage and their Vth is 1.0-3.0 V, so at an intermediate DAC code which
bank conducts is a lottery and a half-on FET runs away to full-on (see the
power sheet).  `Heater` therefore exposes only `on()` and `off()` plus a slow
duty-cycle helper; it refuses intermediate codes unless you ask for them by
name.

BUS ABSTRACTION.  Everything talks to a `Bus` with three methods, so the same
code runs on the PYNQ (AxiIIC), on a laptop through a USB-I2C dongle on the
debug header (smbus2), or against `MockBus` in the tests.
"""
import math
import time
from fractions import Fraction

__all__ = ['Bus', 'MockBus', 'PynqBus', 'SmbusBus',
           'Si5351', 'Si5351Config', 'TMP1075', 'MCP4725', 'Heater',
           'DS2482', 'DS18B20', 'scan', 'EXPECTED_DEVICES',
           'plan_pll', 'ms_params', 'trim_fraction', 'crc8_maxim']

# The bus as the board is built: address -> what should answer there.
EXPECTED_DEVICES = {0x18: 'DS2482-100 1-Wire bridge',
                    0x60: 'Si5351A helper synthesiser',
                    0x61: 'MCP4725 heater DAC (A0 high)'}
for _i in range(8):
    EXPECTED_DEVICES[0x48 + _i] = 'TMP1075 #%d' % _i


# ===========================================================================
# the bus
# ===========================================================================
class Bus(object):
    """Three primitives are enough for every part on this board."""

    def write(self, addr, data):
        raise NotImplementedError

    def read(self, addr, n):
        raise NotImplementedError

    def write_read(self, addr, data, n):
        """Write `data`, repeated START, read n bytes.  The register-read idiom."""
        raise NotImplementedError

    def probe(self, addr):
        """True if something ACKs at `addr`.  Sends one harmless byte (0x00,
        which every part here takes as 'pointer = 0') because a zero-length
        transfer is not portable across the backends."""
        try:
            self.write(addr, bytes([0x00]))
            return True
        except Exception:
            return False


class PynqBus(Bus):
    """pynq.lib.iic.AxiIIC -- the axi_iic in the overlay, bound by pynq.

    ROUND 30, on real silicon.  `AxiIIC.receive()` passes its `data` argument
    straight to `XIic_Recv`, whose prototype is

        unsigned XIic_Recv(unsigned long, unsigned char, unsigned char *,
                           unsigned, unsigned char);

    cffi will convert a `bytes` for that `unsigned char *` -- which is why
    `send()` works with one and why the bus SCAN passed -- but it refuses a
    `bytearray`, because a bytearray is mutable and cffi has no way to pin it:

        TypeError: initializer for ctype 'unsigned char *' must be a cdata
                   pointer, not bytearray

    So a receive needs a real cffi buffer.  The class has the FFI that owns
    the prototype (`AxiIIC._ffi`, created by its own `_initialise_lib()` and
    therefore non-None by the time we are handed an instance), so allocate
    from that one rather than making a second FFI whose `unsigned char[]` is
    a different type object.
    """

    def __init__(self, axi_iic):
        self.iic = axi_iic
        self._ffi = getattr(type(axi_iic), "_ffi", None)
        if self._ffi is None:                      # pragma: no cover
            import cffi
            self._ffi = cffi.FFI()

    def _rx(self, n):
        return self._ffi.new("unsigned char[]", n)

    def _bytes(self, buf, n):
        return bytes(self._ffi.buffer(buf, n))

    def write(self, addr, data):
        data = bytes(data)
        self.iic.send(addr, data, len(data))

    def read(self, addr, n):
        buf = self._rx(n)
        self.iic.receive(addr, buf, n)
        return self._bytes(buf, n)

    def write_read(self, addr, data, n):
        data = bytes(data)
        self.iic.send(addr, data, len(data), self.iic.REPEAT_START)
        buf = self._rx(n)
        self.iic.receive(addr, buf, n)
        return self._bytes(buf, n)


class SmbusBus(Bus):
    """smbus2 on a Linux i2c-dev, for a USB-I2C dongle on the debug header."""

    def __init__(self, busno=1):
        import smbus2
        self._m = smbus2
        self.b = smbus2.SMBus(busno)

    def write(self, addr, data):
        self.b.i2c_rdwr(self._m.i2c_msg.write(addr, bytes(data)))

    def read(self, addr, n):
        m = self._m.i2c_msg.read(addr, n)
        self.b.i2c_rdwr(m)
        return bytes(m)

    def write_read(self, addr, data, n):
        w = self._m.i2c_msg.write(addr, bytes(data))
        r = self._m.i2c_msg.read(addr, n)
        self.b.i2c_rdwr(w, r)
        return bytes(r)


class MockBus(Bus):
    """A bus of register files, for tests.  Each device is a dict of
    register -> value with a pointer, which is how all four real parts behave
    to first order (the DS2482 and MCP4725 are special-cased just enough)."""

    def __init__(self, present=None):
        self.present = set(EXPECTED_DEVICES if present is None else present)
        self.regs = {a: {} for a in self.present}
        self.ptr = {a: 0 for a in self.present}
        self.log = []

    def _dev(self, addr):
        if addr not in self.present:
            raise RuntimeError('NAK at 0x%02X' % addr)
        return self.regs[addr]

    def write(self, addr, data):
        data = bytes(data)
        self.log.append(('W', addr, data))
        if addr == 0x00:                     # general call
            return
        d = self._dev(addr)
        if addr == 0x61:                     # MCP4725: command byte, not pointer
            d['cmd'] = data
            return
        if addr == 0x18:                     # DS2482: command, operand
            d.setdefault('cmds', []).append(data)
            return
        if not data:
            return
        self.ptr[addr] = data[0]
        for i, b in enumerate(data[1:]):
            d[(data[0] + i) & 0xFF] = b

    def read(self, addr, n):
        self.log.append(('R', addr, n))
        d = self._dev(addr)
        if addr == 0x61:
            return bytes(d.get('readback', bytes(5)))[:n]
        if addr == 0x18:
            return bytes(d.get('readback', bytes(n)))[:n]
        p = self.ptr[addr]
        if addr in range(0x48, 0x50):        # TMP1075: 16-bit registers
            v = d.get(p, 0)
            return bytes([(v >> 8) & 0xFF, v & 0xFF])[:n]
        return bytes(d.get((p + i) & 0xFF, 0) for i in range(n))

    def write_read(self, addr, data, n):
        self.write(addr, data)
        return self.read(addr, n)


def scan(bus, lo=0x08, hi=0x77):
    """Addresses that ACK, as a sorted list."""
    return [a for a in range(lo, hi + 1) if bus.probe(a)]


# ===========================================================================
# Si5351A -- AN619 register map
# ===========================================================================
REG_STATUS      = 0
REG_OEB         = 3
REG_PLL_SRC     = 15
REG_CLK_CTRL    = 16       # 16 + n
REG_MSNA        = 26       # PLLA feedback, 8 registers
REG_MSNB        = 34       # PLLB feedback, 8 registers
REG_MS0         = 42       # output MultiSynth 0, 8 registers
REG_MS1         = 50
REG_MS2         = 58
REG_SS_EN       = 149
REG_PLL_RESET   = 177
REG_XTAL_CL     = 183

CLK_PDN   = 0x80
CLK_INT   = 0x40
CLK_PLLB  = 0x20
CLK_INV   = 0x10
CLK_SRC_MS = 0x0C
CLK_IDRV_2MA, CLK_IDRV_4MA, CLK_IDRV_6MA, CLK_IDRV_8MA = 0x00, 0x01, 0x02, 0x03

# THE HELPER OUTPUT RUNS AT 2 mA, NOT 8.  ROUND 39, the first board.  With
# CLK0 at 8 mA, fractional PLLA slipped a whole 25 MHz reference cycle ~650
# times a second -- every slip a 40 ns step in the helper, i.e. ~324 us of
# every beat -- and the helper averaged ~19 ppm fast.  PLLA in INTEGER mode,
# and PLLB, never slipped, and the slip rate rose as the internal XA load fell
# (XTAL_CL 10/8/6 pF: 650/2000/3200 per second), so the reading is that the
# outputs' own switching reaches the reference path (VDD and VDDO share one
# bead-fed node on this board) and only a PLL whose phase detector is not
# synchronous with that disturbance -- a fractional one -- cycle-slips on it.
# Round 39 settled on 4 mA with HO open.  ROUND 40, HO cabled into a 50 ohm
# input: at 4 mA PLLA slipped 900-1400 times a second whenever CLK1 ran at
# 4 mA or more, and at 8 mA 930-2200 whatever CLK1 did -- but at 2 mA, 0 in
# every CLK1 setting, 10 fresh starts in 10 with CLK1 at 8 mA, and none in
# long runs.  The Si5351's own sticky LOL bits never saw any of it.  CLK1
# stays at 8 mA to drive the null channel's 50 ohm cable; PLLB never slipped.
# bringup.py counts slips after programming.  This is a register setting,
# rewritten at every power-up; the board's parts do not set it.
IDRV_HELPER = CLK_IDRV_2MA
IDRV_NULL = CLK_IDRV_8MA

XTAL_CL_6PF, XTAL_CL_8PF, XTAL_CL_10PF = 0x40, 0x80, 0xC0
XTAL_CL_RESERVED_BITS = 0x12          # AN619 reg 183 bits 5:0 "should be 010010b"


def ms_params(a, b, c):
    """AN619 3.2 / 4.1.2: (P1, P2, P3) for the ratio a + b/c."""
    if not (0 <= b < c) or c < 1 or c > 1048575:
        raise ValueError('bad fraction %d/%d' % (b, c))
    f = (128 * b) // c
    p1 = 128 * a + f - 512
    p2 = 128 * b - c * f
    p3 = c
    if not (0 <= p1 < (1 << 18)):
        raise ValueError('P1 out of range: a=%d' % a)
    return p1, p2, p3


def ms_registers(base, p1, p2, p3, rdiv=0):
    """The eight bytes AN619 lays a MultiSynth's parameters into."""
    return {
        base + 0: (p3 >> 8) & 0xFF,
        base + 1: p3 & 0xFF,
        base + 2: ((rdiv & 7) << 4) | ((p1 >> 16) & 0x03),
        base + 3: (p1 >> 8) & 0xFF,
        base + 4: p1 & 0xFF,
        base + 5: ((p3 >> 12) & 0xF0) | ((p2 >> 16) & 0x0F),
        base + 6: (p2 >> 8) & 0xFF,
        base + 7: p2 & 0xFF,
    }


def decode_ms(regs, base):
    """Inverse of ms_registers: the ratio a + b/c as a Fraction, from bytes."""
    p3 = ((regs[base + 5] & 0xF0) << 12) | (regs[base + 0] << 8) | regs[base + 1]
    p1 = ((regs[base + 2] & 0x03) << 16) | (regs[base + 3] << 8) | regs[base + 4]
    p2 = ((regs[base + 5] & 0x0F) << 16) | (regs[base + 6] << 8) | regs[base + 7]
    # P1 = 128a + floor(128b/c) - 512, P2 = 128b - c*floor(128b/c), P3 = c
    #   => 128(a + b/c) = P1 + 512 + P2/P3
    return (Fraction(p1 + 512) + Fraction(p2, p3)) / 128


def plan_pll(f_xtal, f_out, div, max_den=1048575):
    """The exact PLL ratio a + b/c that gives f_out from f_xtal through an
    integer output divider `div`, as (a, b, c, f_vco).

    Uses the best rational approximation with c <= 2^20 - 1.  For this
    board's numbers (25 MHz, 10 001 234.4 Hz, 80) that is 32 + 1543/390625
    EXACTLY, which is better than the 32 + 4142/1048575 the schematic quotes
    (that one is 10 ppb high, which is nothing, but exact is free).
    """
    ratio = Fraction(f_out).limit_denominator(10 ** 9) * div / Fraction(f_xtal)
    ratio = ratio.limit_denominator(max_den)
    a = ratio.numerator // ratio.denominator
    b = ratio.numerator - a * ratio.denominator
    c = ratio.denominator
    if not (15 <= a <= 90):
        raise ValueError('PLL ratio %s outside 15..90' % ratio)
    f_vco = f_xtal * (a + b / c)
    if not (600e6 <= f_vco <= 900e6):
        raise ValueError('VCO %.0f Hz outside 600-900 MHz' % f_vco)
    return a, b, c, f_vco


def trim_fraction(a, b, c, f_measured, f_wanted, max_den=1048575):
    """Scale the PLL ratio so an output measured at f_measured lands on
    f_wanted.  The TCXO's true frequency drops out: the correction is a pure
    ratio.  Returns (a, b, c)."""
    r = (Fraction(a) + Fraction(b, c)) * Fraction(f_wanted).limit_denominator(10 ** 9) \
        / Fraction(f_measured).limit_denominator(10 ** 9)
    r = r.limit_denominator(max_den)
    a2 = r.numerator // r.denominator
    return a2, r.numerator - a2 * r.denominator, r.denominator


class Si5351Config(object):
    """A register image for the board's two clocks.

    CLK0 = the helper, from PLLA with a fractional feedback ratio and an
           INTEGER MultiSynth (div), R = 1.
    CLK1 = the null source at exactly f_xtal * mult / div from PLLB, all
           integer: 25 MHz x 32 = 800 MHz / 80 = 10.000000 MHz.
    The two PLLs lock to the same XA input, so the beat between CLK0 and CLK1
    is exact in frequency; they are two PLLs, so their noise is not common.

    CLK2 = off, which is what the front-end board wants: nothing is routed to
    it there.  ROUND 30 adds `clk2='helper'`, a second copy of CLK0 off the
    same PLLA and the same MultiSynth ratio, for the bench: with a scope or an
    ADALM2000 on CLK1 and CLK2 you can watch the beat this whole instrument is
    built on -- 10.0012344 against 10.000000 MHz, 1234.4 Hz apart -- before any
    board exists.  It costs the real board nothing because it is not the
    default and CLK2 has no track on it.
    """

    CLK2_CHOICES = ('off', 'helper', 'null')

    def __init__(self, f_xtal=25e6, f_helper=10_001_234.4, f_null=10e6,
                 div=80, pll_ratio=None, xtal_cl=XTAL_CL_10PF, clk2='off'):
        self.f_xtal, self.f_helper, self.f_null, self.div = f_xtal, f_helper, f_null, div
        if pll_ratio is None:
            self.a, self.b, self.c, self.f_vco_a = plan_pll(f_xtal, f_helper, div)
        else:
            self.a, self.b, self.c = pll_ratio
            self.f_vco_a = f_xtal * (self.a + self.b / self.c)
        # PLLB: integer multiplier for the null clock
        mult = Fraction(f_null).limit_denominator(10 ** 6) * div / Fraction(f_xtal).limit_denominator(10 ** 6)
        if mult.denominator != 1 or mult.numerator % 2:
            raise ValueError('null clock needs an even integer PLLB ratio, got %s' % mult)
        self.mult_b = int(mult)
        self.f_vco_b = f_xtal * self.mult_b
        if not (600e6 <= self.f_vco_b <= 900e6):
            raise ValueError('PLLB VCO %.0f outside 600-900 MHz' % self.f_vco_b)
        if div % 2 or not (6 <= div <= 254):
            raise ValueError('output divider must be an even integer 6..254')
        if clk2 not in self.CLK2_CHOICES:
            raise ValueError('clk2 must be one of %s, got %r'
                             % (self.CLK2_CHOICES, clk2))
        self.clk2 = clk2
        self.xtal_cl = xtal_cl

    def registers(self):
        """register -> byte, everything the part needs after power-up."""
        r = {}
        r[REG_PLL_SRC] = 0x00                          # both PLLs from XTAL, CLKIN_DIV = 1
        r[REG_XTAL_CL] = self.xtal_cl | XTAL_CL_RESERVED_BITS
        r.update(ms_registers(REG_MSNA, *ms_params(self.a, self.b, self.c)))
        r.update(ms_registers(REG_MSNB, *ms_params(self.mult_b, 0, 1)))
        r.update(ms_registers(REG_MS0, *ms_params(self.div, 0, 1), rdiv=0))
        r.update(ms_registers(REG_MS1, *ms_params(self.div, 0, 1), rdiv=0))
        # Drive strengths: see IDRV_HELPER above -- 8 mA on the helper made
        # PLLA cycle-slip on the first board.
        r[REG_CLK_CTRL + 0] = CLK_INT | CLK_SRC_MS | IDRV_HELPER               # PLLA
        r[REG_CLK_CTRL + 1] = CLK_INT | CLK_PLLB | CLK_SRC_MS | IDRV_NULL      # PLLB
        if self.clk2 == 'off':
            r[REG_CLK_CTRL + 2] = CLK_PDN                                      # not routed
        else:
            # Same MultiSynth ratio as CLK0/CLK1; only the PLL differs.  The
            # MultiSynth is an integer divider either way, so CLK_INT is right
            # for both -- the fraction that makes the helper is in PLLA's
            # feedback, not here.
            r.update(ms_registers(REG_MS2, *ms_params(self.div, 0, 1), rdiv=0))
            r[REG_CLK_CTRL + 2] = (CLK_INT | CLK_SRC_MS
                                   | (CLK_PLLB | IDRV_NULL if self.clk2 == 'null'
                                      else IDRV_HELPER))
        r[REG_SS_EN] = 0x00                            # spread spectrum off
        return r

    def expected(self):
        """(f_clk0, f_clk1) the image produces, for the log."""
        return self.f_vco_a / self.div, self.f_vco_b / self.div

    def expected_clk2(self):
        """What CLK2 puts out, or None when it is powered down."""
        if self.clk2 == 'off':
            return None
        return (self.f_vco_b if self.clk2 == 'null' else self.f_vco_a) / self.div

    def oeb(self):
        """The output-enable byte: 0 enables, 1 disables, bit n = CLKn."""
        return 0xFC & ~(0x04 if self.clk2 != 'off' else 0) & 0xFF


class Si5351(object):
    ADDR = 0x60

    def __init__(self, bus, addr=ADDR):
        self.bus, self.addr = bus, addr

    def write_reg(self, reg, val):
        self.bus.write(self.addr, bytes([reg & 0xFF, val & 0xFF]))

    def read_reg(self, reg):
        return self.bus.write_read(self.addr, bytes([reg & 0xFF]), 1)[0]

    def read_regs(self, reg, n):
        return self.bus.write_read(self.addr, bytes([reg & 0xFF]), n)

    @property
    def status(self):
        """dict of the register-0 flags."""
        s = self.read_reg(REG_STATUS)
        return dict(sys_init=bool(s & 0x80), lol_b=bool(s & 0x40),
                    lol_a=bool(s & 0x20), los_clkin=bool(s & 0x10),
                    los_xtal=bool(s & 0x08), revid=s & 0x03, raw=s)

    def wait_ready(self, timeout=1.0):
        """SYS_INIT clears when the part has finished its own start-up."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not (self.read_reg(REG_STATUS) & 0x80):
                return True
            time.sleep(0.01)
        return False

    def program(self, cfg):
        """AN619 figure 12, in order: outputs off, drivers down, new image,
        PLL soft reset, outputs on.  Returns the register image written."""
        img = cfg.registers()
        self.write_reg(REG_OEB, 0xFF)                       # 1. disable all outputs
        for n in range(8):                                   # 2. power down every driver
            self.write_reg(REG_CLK_CTRL + n, CLK_PDN)
        for reg in sorted(img):                              # 4. the new configuration
            self.write_reg(reg, img[reg])
        self.write_reg(REG_PLL_RESET, 0xAC)                  # 5. AN619's value: PLLA+PLLB reset
        self.write_reg(REG_OEB, cfg.oeb())                   # 6. outputs on
        return img

    def verify(self, cfg):
        """Read the image back; return {reg: (wrote, read)} for mismatches."""
        img = cfg.registers()
        bad = {}
        for reg in sorted(img):
            got = self.read_reg(reg)
            want = img[reg]
            if reg == REG_XTAL_CL:                           # only bits 7:6 read back reliably
                got, want = got & 0xC0, want & 0xC0
            if got != want:
                bad[reg] = (want, got)
        return bad

    def lock_status(self):
        s = self.status
        return (not s['lol_a']) and (not s['lol_b']) and not s['los_xtal']

    # Register 1 latches each status flag until it is written back to 0, so a
    # loss of lock between two reads is not lost -- which is what a multi-day
    # log wants (round 41).  Round 40's caveat stands: these bits NEVER saw the
    # cycle slips; only the core's pair register does (DmtdRegisters.
    # helper_slips()).  Log both.
    REG_STICKY = 1

    def sticky(self):
        """dict of the latched status flags since the last clear_sticky()."""
        s = self.read_reg(self.REG_STICKY)
        return dict(sys_init=bool(s & 0x80), lol_b=bool(s & 0x40),
                    lol_a=bool(s & 0x20), los_clkin=bool(s & 0x10),
                    los_xtal=bool(s & 0x08), raw=s)

    def clear_sticky(self):
        self.write_reg(self.REG_STICKY, 0x00)


# ===========================================================================
# TMP1075 -- pointer 0 temperature (12 bit, left justified), 1 config
# ===========================================================================
class TMP1075(object):
    REG_TEMP, REG_CFG, REG_TLOW, REG_THIGH, REG_DIEID = 0x00, 0x01, 0x02, 0x03, 0x0F
    LSB_C = 0.0625

    def __init__(self, bus, addr):
        self.bus, self.addr = bus, addr

    @staticmethod
    def decode(hi, lo):
        v = (hi << 8) | lo
        if v & 0x8000:
            v -= 0x10000
        return (v >> 4) * TMP1075.LSB_C

    def read_c(self):
        hi, lo = self.bus.write_read(self.addr, bytes([self.REG_TEMP]), 2)
        return self.decode(hi, lo)

    def config(self):
        hi, lo = self.bus.write_read(self.addr, bytes([self.REG_CFG]), 2)
        return (hi << 8) | lo

    def set_continuous(self):
        """Default after reset is continuous conversion at 27.5 ms; write it
        anyway so a part left in shutdown by a previous session converts."""
        self.bus.write(self.addr, bytes([self.REG_CFG, 0x00, 0xFF]))


def read_all_thermometers(bus, base=0x48, n=8):
    """[(addr, degC or None)] for the eight board sensors."""
    out = []
    for i in range(n):
        a = base + i
        try:
            out.append((a, TMP1075(bus, a).read_c()))
        except Exception:
            out.append((a, None))
    return out


# ===========================================================================
# MCP4725 -- 12-bit DAC with EEPROM
# ===========================================================================
class MCP4725(object):
    ADDR = 0x61                  # A0 high on this board; 0x60 is the Si5351
    PD_NONE, PD_1K, PD_100K, PD_500K = 0, 1, 2, 3
    CMD_WRITE_DAC, CMD_WRITE_DAC_EEPROM = 0x40, 0x60
    VREF = 3.3

    def __init__(self, bus, addr=ADDR):
        self.bus, self.addr = bus, addr

    @staticmethod
    def frame(cmd, code, pd=0):
        """Datasheet 6.1.2: [C2 C1 C0 x x PD1 PD0 x][D11..D4][D3..D0 x x x x]."""
        code = int(code) & 0xFFF
        return bytes([cmd | ((pd & 3) << 1), (code >> 4) & 0xFF, (code & 0x0F) << 4])

    def write_dac(self, code, pd=0):
        self.bus.write(self.addr, self.frame(self.CMD_WRITE_DAC, code, pd))

    def write_dac_and_eeprom(self, code, pd=0, wait=True):
        self.bus.write(self.addr, self.frame(self.CMD_WRITE_DAC_EEPROM, code, pd))
        if wait:                             # EEPROM write is 25-50 ms; RDY/BSY says when
            t0 = time.time()
            while time.time() - t0 < 0.5:
                if self.read()['ready']:
                    return True
                time.sleep(0.01)
            return False
        return True

    def read(self):
        """Datasheet 6.2: 5 bytes = status/DAC(3) + EEPROM(2)."""
        b = self.bus.read(self.addr, 5)
        return dict(ready=bool(b[0] & 0x80), por=bool(b[0] & 0x40),
                    pd=(b[0] >> 1) & 3, code=(b[1] << 4) | (b[2] >> 4),
                    eeprom_pd=(b[3] >> 5) & 3,
                    eeprom_code=((b[3] & 0x0F) << 8) | b[4])

    def general_call_reset(self):
        """Every MCP4725 on the bus reloads its EEPROM.  Address 0x00, 0x06."""
        self.bus.write(0x00, bytes([0x06]))

    def volts(self, code):
        return self.VREF * code / 4096.0


class Heater(object):
    """The heater as it should be driven on this board: fully on or off.

    See the module docstring.  `duty_cycle()` is the slow-PWM loop helper:
    it returns the on-time for the next period given a demand in 0..1, and
    it is the caller's loop that sleeps -- this class never blocks for
    minutes."""
    FULL = 0xFFF
    MIN_PERIOD_S = 30.0

    def __init__(self, dac):
        self.dac = dac

    def make_safe(self):
        """EEPROM := 0 with the 1k power-down, so the part powers up OFF.
        Idempotent; returns the readback dict."""
        rb = self.dac.read()
        if not (rb['eeprom_code'] == 0 and rb['eeprom_pd'] == MCP4725.PD_1K):
            self.dac.write_dac_and_eeprom(0, pd=MCP4725.PD_1K)
            rb = self.dac.read()
        self.dac.write_dac(0, pd=MCP4725.PD_1K)          # and off right now
        return rb

    def off(self):
        self.dac.write_dac(0, pd=MCP4725.PD_1K)

    def on(self):
        """Every DMN6068SE (Vth <= 3.0 V) is fully on at Vgs = 3.3 V, so all
        three banks conduct their 214 mA and each FET dissipates ~3 mW."""
        self.dac.write_dac(self.FULL, pd=MCP4725.PD_NONE)

    def set_raw(self, code):
        """Intermediate codes are deliberately NOT what the loop uses; they
        are here for characterisation of the sharing problem only."""
        self.dac.write_dac(int(code), pd=MCP4725.PD_NONE)

    @staticmethod
    def duty_cycle(demand, period_s=MIN_PERIOD_S):
        """(on_seconds, off_seconds) for one period at `demand` in 0..1."""
        if period_s < Heater.MIN_PERIOD_S:
            raise ValueError('period below %.0f s puts edges in the measurement band'
                             % Heater.MIN_PERIOD_S)
        d = min(1.0, max(0.0, float(demand)))
        return d * period_s, (1.0 - d) * period_s


# ===========================================================================
# DS2482-100 -- I2C to 1-Wire bridge
# ===========================================================================
class DS2482(object):
    ADDR = 0x18
    CMD_RESET, CMD_SET_PTR, CMD_WRITE_CFG = 0xF0, 0xE1, 0xD2
    CMD_1W_RESET, CMD_1W_BIT, CMD_1W_WRITE, CMD_1W_READ, CMD_1W_TRIPLET = 0xB4, 0x87, 0xA5, 0x96, 0x78
    PTR_STATUS, PTR_DATA, PTR_CONFIG = 0xF0, 0xE1, 0xC3
    ST_1WB, ST_PPD, ST_SD, ST_LL, ST_RST, ST_SBR, ST_TSB, ST_DIR = [1 << i for i in range(8)]

    def __init__(self, bus, addr=ADDR):
        self.bus, self.addr = bus, addr

    def reset(self):
        st = self.bus.write_read(self.addr, bytes([self.CMD_RESET]), 1)[0]
        return bool(st & self.ST_RST)

    def write_config(self, apu=True, spu=False, ows=False):
        """Standard speed only on this board (see the probes sheet: the bus
        capacitance rules overdrive out).  Upper nibble is the complement."""
        cfg = (1 if apu else 0) | (4 if spu else 0) | (8 if ows else 0)
        byte = ((~cfg & 0x0F) << 4) | cfg
        rb = self.bus.write_read(self.addr, bytes([self.CMD_WRITE_CFG, byte]), 1)[0]
        return rb == cfg

    def status(self):
        return self.bus.write_read(self.addr, bytes([self.CMD_SET_PTR, self.PTR_STATUS]), 1)[0]

    def _wait(self, timeout=0.05):
        t0 = time.time()
        st = self.status()
        while st & self.ST_1WB:
            if time.time() - t0 > timeout:
                raise RuntimeError('DS2482 1-Wire busy timeout')
            st = self.bus.read(self.addr, 1)[0]
        return st

    def ow_reset(self):
        """True if a presence pulse was seen."""
        self.bus.write(self.addr, bytes([self.CMD_1W_RESET]))
        return bool(self._wait() & self.ST_PPD)

    def ow_write(self, byte):
        self.bus.write(self.addr, bytes([self.CMD_1W_WRITE, byte & 0xFF]))
        self._wait()

    def ow_read(self):
        self.bus.write(self.addr, bytes([self.CMD_1W_READ]))
        self._wait()
        return self.bus.write_read(self.addr, bytes([self.CMD_SET_PTR, self.PTR_DATA]), 1)[0]

    def ow_triplet(self, direction):
        self.bus.write(self.addr, bytes([self.CMD_1W_TRIPLET, 0x80 if direction else 0x00]))
        st = self._wait()
        return bool(st & self.ST_SBR), bool(st & self.ST_TSB), bool(st & self.ST_DIR)


def crc8_maxim(data):
    """Dallas/Maxim CRC-8, x^8 + x^5 + x^4 + 1, LSB first (0x8C reflected)."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8C if crc & 1 else crc >> 1
    return crc


class DS18B20(object):
    """Five probes on the DS2482's star.  ROM search is the standard Maxim
    algorithm expressed with the bridge's triplet command."""
    FAMILY = 0x28
    CMD_SEARCH_ROM, CMD_READ_ROM, CMD_MATCH_ROM, CMD_SKIP_ROM = 0xF0, 0x33, 0x55, 0xCC
    CMD_CONVERT_T, CMD_READ_SCRATCH = 0x44, 0xBE
    T_CONV_12BIT = 0.75

    def __init__(self, bridge):
        self.br = bridge

    def search(self, max_devices=16):
        """List of 64-bit ROM codes (as ints), CRC-checked."""
        found = []
        last_discrepancy = 0
        last_device = False
        rom = 0
        while not last_device and len(found) < max_devices:
            if not self.br.ow_reset():
                break
            self.br.ow_write(self.CMD_SEARCH_ROM)
            last_zero = 0
            new_rom = 0
            for bit in range(64):
                if bit < last_discrepancy - 1:
                    direction = (rom >> bit) & 1
                elif bit == last_discrepancy - 1:
                    direction = 1
                else:
                    direction = 0
                sbr, tsb, taken = self.br.ow_triplet(direction)
                if sbr and tsb:
                    return found                      # no device answered
                if not sbr and not tsb and not taken:
                    last_zero = bit + 1
                if taken:
                    new_rom |= (1 << bit)
            rom = new_rom
            last_discrepancy = last_zero
            if last_discrepancy == 0:
                last_device = True
            b = rom.to_bytes(8, 'little')
            if crc8_maxim(b[:7]) == b[7]:
                found.append(rom)
        return found

    def _select(self, rom):
        if not self.br.ow_reset():
            raise RuntimeError('no presence pulse')
        if rom is None:
            self.br.ow_write(self.CMD_SKIP_ROM)
        else:
            self.br.ow_write(self.CMD_MATCH_ROM)
            for b in int(rom).to_bytes(8, 'little'):
                self.br.ow_write(b)

    def convert_all(self, wait=True):
        self._select(None)
        self.br.ow_write(self.CMD_CONVERT_T)
        if wait:
            time.sleep(self.T_CONV_12BIT)

    def read_c(self, rom):
        self._select(rom)
        self.br.ow_write(self.CMD_READ_SCRATCH)
        sp = bytes(self.br.ow_read() for _ in range(9))
        if crc8_maxim(sp[:8]) != sp[8]:
            raise RuntimeError('scratchpad CRC bad for %016X' % rom)
        return self.decode_scratchpad(sp)

    @staticmethod
    def decode_scratchpad(sp):
        raw = sp[0] | (sp[1] << 8)
        if raw & 0x8000:
            raw -= 0x10000
        return raw / 16.0
