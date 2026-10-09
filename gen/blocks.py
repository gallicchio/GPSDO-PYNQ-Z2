"""Reusable drawing blocks, so every channel is identical by construction."""
import design as D

GRID = 1.27


class RefGen:
    """
    Reference designator allocator.

    KiCAD requires references of the form <letters><digits>; anything else (say
    "R01_T") counts as UNANNOTATED, and an unannotated schematic silently
    produces a degenerate netlist -- KiCAD warns "schematic has annotation
    errors" and then merges or drops nets.  That single mistake cost a long
    debugging session, so references are allocated here and nowhere else.

    Each unit gets its own hundred-block: unit 1 -> R101, R102, ...;
    unit 13 -> R1301, R1302, ...  Power symbols get #PWR<block><nn>, which keeps
    them out of the BOM.
    """

    def __init__(self, unit):
        self.block = unit
        self.n = {}

    def __call__(self, prefix):
        self.n[prefix] = self.n.get(prefix, 0) + 1
        return "%s%d%02d" % (prefix, self.block, self.n[prefix])

    def pwr(self):
        return self("#PWR")

    def filt(self):
        """Rev B item 12: a gate's supply resistor, where rev A had a bead (FBnn).
        Numbered from 51 in the block, so that every part rev A had keeps its
        number (R6001-R6011 under the 1-Wire terminals, say) instead of moving up
        one for each bead ahead of it."""
        self.n["_filt"] = self.n.get("_filt", 0) + 1
        return "R%d%02d" % (self.block, 50 + self.n["_filt"])


def gnd(s, x, y, drop=6.35, ref=None, R=None):
    """GND symbol `drop` below (x,y), wired up to it.  drop=0 places the symbol
    directly on the point, which is what dense connector sheets want: a riser
    would cross the neighbouring pins' stubs and silently join them."""
    if drop:
        s.wire(x, y, x, y + drop)
    s.sym("power:GND", x, y + drop, 0, ref=ref or (R.pwr() if R else "#PWR001"), value="GND",
          hide_ref=True, in_bom=False, on_board=False, val_dxy=(0, 3.81))


def rail(s, x, y, net, rise=6.35, ref=None, R=None, down=False):
    """Power symbol `rise` above (x,y), wired down to it.  Power comes from the
    top -- except where the only clear side is downward.

    Round 21 added `down` for exactly one pin: the MCP4725's A0 strap.  Its A0,
    SDA and SCL pins are all on the symbol's left side at 2.54 mm pitch with
    A0 the lowest, so a riser going UP from A0 lands on the SCL wire and
    SHORTS I2C_SCL to +3V3_D.  That is what happened on the first attempt at
    the 0x61 fix, and it survived ERC, check_netlist and check_paths -- see
    check_netlist's REQUIRED_NETS, added the same round to catch it.
    """
    dy = -rise if down else rise
    if rise:
        s.wire(x, y, x, y - dy)
    lib = "power:+3V3" if net.startswith("+3V3") else (
          "power:+5V" if net.startswith("+5V") else "power:+12V")
    s.sym(lib, x, y - dy, 180 if down else 0,
          ref=ref or (R.pwr() if R else "#PWR002"), value=net,
          hide_ref=True, in_bom=False, on_board=False,
          val_dxy=(0, 3.81) if down else (0, -3.81))


def r_h(s, x, y, ref, val, dnp=False, below=False, **kw):
    """Horizontal resistor centered at (x,y).  Pins land at x-3.81 and x+3.81."""
    p = D.P["R0805"]
    dy = (5.08, 8.89) if below else (-8.89, -5.08)
    return s.sym(p["lib"], x, y, 90, ref=ref, value=val,
                 footprint=kw.pop("footprint", p["fp"]), dnp=dnp,
                 ref_dxy=(0, dy[0]), val_dxy=(0, dy[1]), **kw)


def r_v(s, x, y, ref, val, dnp=False, left=False, **kw):
    """Vertical resistor centered at (x,y).  Pins land at y-3.81 and y+3.81.

    Labels go immediately beside the body, never offset far enough to land under
    whatever is above or below it.
    """
    p = D.P["R0805"]
    dx = -3.81 if left else 3.81
    j = "right" if left else "left"
    return s.sym(p["lib"], x, y, 0, ref=ref, value=val,
                 footprint=kw.pop("footprint", p["fp"]), dnp=dnp,
                 ref_dxy=(dx, -1.27), val_dxy=(dx, 2.54), justify=j, **kw)


def c_h(s, x, y, ref, val, dnp=False, **kw):
    p = D.P["C0805"]
    return s.sym(p["lib"], x, y, 90, ref=ref, value=val,
                 footprint=kw.pop("footprint", p["fp"]), dnp=dnp,
                 ref_dxy=(0, -8.89), val_dxy=(0, -5.08), **kw)


def c_v(s, x, y, ref, val, dnp=False, **kw):
    p = D.P["C0805"]
    return s.sym(p["lib"], x, y, 0, ref=ref, value=val,
                 footprint=kw.pop("footprint", p["fp"]), dnp=dnp,
                 ref_dxy=(3.81, -1.27), val_dxy=(3.81, 2.54), **kw)


def testpoint(s, x, y, ref, name):
    """Test point stub going up from a signal node.

    The stub tees off the middle of a wire, so it needs an explicit junction:
    KiCAD treats a wire endpoint landing on another wire's midpoint as a
    crossing, not a connection, unless a junction dot says otherwise.
    """
    p = D.P["TP"]
    s.junction(x, y)
    s.wire(x, y, x, y - 5.08)
    s.sym(p["lib"], x, y - 5.08, 0, ref=ref, value=name, footprint=p["fp"],
          ref_dxy=(1.905, -1.27), val_dxy=(1.905, 1.27))


def decouple(s, x_vcc, y_vcc, rail_net, R, note="", tall=True,
             values=("100n", "10n")):
    """
    Per-gate supply: a 4.7 ohm resistor in this gate's own Vcc feed off the
    shared rail, then 100 nF X7R + 10 nF C0G right at the pin.

    Rev B, item 12: rev A had a 600R@100MHz bead here, and the bead with its
    110 nF was the tank every unplugged squarer oscillated in (557-583 kHz).
    Bridging FB401 stopped unit 4 (30/30, round 45), and 4.7 ohm in its place
    kept it quiet (O2, round 45.20).  4.7 ohm with 110 nF is a 0.31 MHz RC
    corner with no resonance.  Drawn above the gate so
    power always comes from the top, and drawn TALL so that the capacitors'
    ground symbols sit clear above the gate body instead of landing on its pins.

    One shared rail (so threshold drift is common mode and cancels in the
    differences) plus per-gate local decoupling, which is what every gate on
    this board gets.

    `values` overrides the pair.  The Si5351 asks for 0.1 to 1.0 uF per supply
    pin (datasheet section 7.1), and it has two of them, so it passes
    ("100n", "100n") and the layout puts one at pin 1 and one at pin 7.
    """
    fb_ref, c1_ref, c2_ref = R.filt(), R("C"), R("C")
    y_node = y_vcc - (22.86 if tall else 10.16)   # decoupled node, above the gate
    y_fb = y_node - 6.35
    r_v(s, x_vcc, y_fb, fb_ref, D.P["RFILT"]["val"])
    s.wire(x_vcc, y_fb + 3.81, x_vcc, y_vcc)          # bead -> node -> Vcc pin
    rail(s, x_vcc, y_fb - 3.81, rail_net, rise=6.35, R=R)
    s.junction(x_vcc, y_node)
    prev = x_vcc
    for i, (ref, val) in enumerate(((c1_ref, values[0]), (c2_ref, values[1]))):
        xc = x_vcc + 8.89 + i * 11.43
        s.wire(prev, y_node, xc, y_node)
        c_v(s, xc, y_node + 5.08, ref, val)
        s.wire(xc, y_node, xc, y_node + 1.27)
        gnd(s, xc, y_node + 8.89, drop=5.08, R=R)
        if i == 0:
            s.junction(xc, y_node)
        prev = xc


def ufl_tap(s, x, y, rref, jref, label, R, rval="1k", up=False):
    """Rev B item 19: a monitor tap off the node at (x, y), hanging down (or
    up): the series resistor first, its body at the node, then the U.FL with
    its shield to ground.  1k: /21 into a 50 ohm scope, x1 into 1 Mohm; an
    unplugged tap costs the node < 0.02 % and a fixed < 50 ps (REVB item 19)."""
    sgn = -1 if up else 1
    s.wire(x, y, x, y + sgn * 2.54)
    r_v(s, x, y + sgn * 6.35, rref, rval, left=True)
    p = D.P["UFL"]
    j = s.sym(p["lib"], x, y + sgn * 15.24, 90 if up else 270, ref=jref, value=label,
              footprint=p["fp"], lcsc=p["lcsc"], ref_dxy=(3.81, -1.27), val_dxy=(3.81, 1.27))
    gnd(s, *j.pin(2), drop=3.81, R=R)
    return j
