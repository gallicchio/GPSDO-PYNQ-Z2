"""PYNQ driver for the GPSDO DDMTD overlay.

On the board:

    from pynq import Overlay
    ol = Overlay('dmtd_top.bit')
    ol.dmtd_capture_0.selftest()

On any machine, for the phase arithmetic and for tests:

    from driver import phase_ps, unwrap_ps
"""
from .dmtd_constants import *          # noqa: F401,F403
from .dmtd import *                    # noqa: F401,F403
from .dmtd import DmtdRegisters, phase_ps, wrap_cycles, unwrap_ps  # noqa: F401
from . import i2c_devices                     # noqa: F401
