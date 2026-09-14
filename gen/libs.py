"""Write the project's own symbol and footprint libraries.

Two symbols on this board exist in no stock KiCAD library -- the TPS7A2033 in
SOT-23-5 and the DS2482-100 -- and one footprint, the universal vertical SMA.
They are embedded in the sheets, which is enough to plot and netlist but leaves
KiCAD reporting "library not configured" and every footprint link unresolved.
Writing them to disk, with ${KIPRJMOD}-relative library tables so a fresh
checkout finds them, is what clears the last of the ERC report.
"""
import os
import kigen
from kigen import SYMS, ser, q

PROJECT_SYMS = ("GPSDO-PYNQ-Z2:TPS7A2033PDBVR", "GPSDO-PYNQ-Z2:DS2482S-100")


def _sym_lib(outdir):
    body = "\n".join(ser(SYMS._flatten(l)) for l in PROJECT_SYMS)
    txt = ('(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "gpsdo-pynq-z2")\n'
           '\t(generator_version "9.0")\n%s\n)\n' % body)
    path = os.path.join(outdir, "library", "GPSDO-PYNQ-Z2.kicad_sym")
    open(path, "w", encoding="utf-8").write(txt)
    return path


# The universal vertical SMA: four 1.7 mm ground holes on a 5.08 mm square and
# a 1.5 mm centre hole.  "Universal" because that pattern accepts every cheap
# vertical SMA jack we could actually buy -- the ground posts differ in
# diameter between vendors but not in position.
SMA = """(footprint "SMA_Vertical_THT_Universal"
\t(version 20240108)
\t(generator "gpsdo-pynq-z2")
\t(generator_version "9.0")
\t(layer "F.Cu")
\t(descr "Vertical SMA jack, through hole: 1.5 mm centre, four 1.7 mm ground holes on a 5.08 mm square")
\t(tags "SMA RF connector vertical THT")
\t(attr through_hole)
\t(property "Reference" "REF**"
\t\t(at 0 -6.35 0) (layer "F.SilkS") (uuid "aaaaaaaa-0000-4000-8000-000000000001")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(property "Value" "SMA"
\t\t(at 0 6.35 0) (layer "F.Fab") (uuid "aaaaaaaa-0000-4000-8000-000000000002")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
%(gfx)s
\t(pad "1" thru_hole circle (at 0 0) (size 2.6 2.6) (drill 1.5)
\t\t(layers "*.Cu" "*.Mask") (remove_unused_layers no)
\t\t(uuid "aaaaaaaa-0000-4000-8000-00000000000a"))
%(pads)s
)
"""


# Round 29.  Until now this board had SIX comment-layer notes saying "M3
# standoff" and not one drilled hole: `put("H1".."H6", ...)` looked the
# references up in the netlist, no schematic sheet has a mounting-hole symbol,
# and `put()` returns quietly when a reference is not there.  Six notes, zero
# holes, and the 3D render was right to show nothing.
#
# These two are placed directly rather than through the netlist, because a
# mounting hole is not a part: it has no pads, no net, no BOM line and nothing
# for an assembler to fit.  The COURTYARD is deliberately the standoff's
# keep-out (3.3 mm radius, an M3 washer plus a little), not the hole, so that
# build_pcb's existing courtyard-overlap check tests the clearance for free.
MOUNT_FP = """(footprint "%(name)s"
\t(version 20240108)
\t(generator "gpsdo-pynq-z2")
\t(generator_version "9.0")
\t(layer "F.Cu")
\t(descr "%(descr)s")
\t(tags "mounting hole M3 NPTH")
\t(attr exclude_from_pos_files exclude_from_bom)
\t(property "Reference" "REF**"
\t\t(at 0 -5.2 0) (layer "F.SilkS") (uuid "9a000000-0000-4000-8000-%(u)012d1")
\t\t(effects (font (size 0.8 0.8) (thickness 0.15))))
\t(property "Value" "%(name)s"
\t\t(at 0 5.2 0) (layer "F.Fab") (uuid "9a000000-0000-4000-8000-%(u)012d2")
\t\t(effects (font (size 0.8 0.8) (thickness 0.15))))
\t(fp_rect (start %(cx0)g %(cy0)g) (end %(cx1)g %(cy1)g)
\t\t(stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd")
\t\t(uuid "9a000000-0000-4000-8000-%(u)012d3"))
\t(fp_rect (start %(cx0)g %(cy0)g) (end %(cx1)g %(cy1)g)
\t\t(stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab")
\t\t(uuid "9a000000-0000-4000-8000-%(u)012d4"))
\t(pad "" np_thru_hole %(shape)s (at 0 0) (size %(w)g %(h)g) (drill %(drill)s)
\t\t(layers "F&B.Cu" "*.Mask")
\t\t(uuid "9a000000-0000-4000-8000-%(u)012d5"))
)
"""


def _mounting(d):
    """A round M3 hole and a 7 x 3.2 slot, both NPTH.

    The slot is for the one standoff this board SHARES with the PYNQ-Z2: the
    host's own top-right mounting hole.  It is a slot and not a hole because
    the registration between the two boards runs through a 2x20 header and a
    set of dimensions measured off photographs to about a millimetre, and a
    3.2 mm hole has no millimetre to give.  Round 11's mock-up already drew it
    as a slot and said so; nothing had ever built it.
    """
    import os as _os
    for name, w, h, drill, shape, cw, ch, descr in (
            ("MountingHole_M3_NPTH", 3.2, 3.2, "3.2", "circle", 3.3, 3.3,
             "M3 clearance hole, non-plated; courtyard is the standoff keep-out"),
            ("MountingSlot_M3_NPTH", 7.0, 3.2, "oval 7 3.2", "oval", 5.2, 3.3,
             "M3 slot 7 x 3.2 mm, non-plated, for the standoff shared with the host")):
        open(_os.path.join(d, name + ".kicad_mod"), "w", encoding="utf-8").write(
            MOUNT_FP % dict(name=name, descr=descr, u=abs(hash(name)) % 10**9,
                            w=w, h=h, drill=drill, shape=shape,
                            cx0=-cw, cy0=-ch, cx1=cw, cy1=ch))


def _fp_lib(outdir):
    d = os.path.join(outdir, "library", "GPSDO-PYNQ-Z2.pretty")
    if not os.path.isdir(d):
        os.makedirs(d)
    gfx = []
    # courtyard and a silk square that clears the ground posts
    for lyr, w, h, layer in (("F.CrtYd", 0.05, 4.75, "F.CrtYd"),
                             ("F.SilkS", 0.12, 4.6, "F.SilkS"),
                             ("F.Fab", 0.1, 4.75, "F.Fab")):
        gfx.append('\t(fp_rect (start %g %g) (end %g %g)\n'
                   '\t\t(stroke (width %g) (type solid)) (fill no) (layer "%s")\n'
                   '\t\t(uuid "bbbbbbbb-0000-4000-8000-%012d"))'
                   % (-h, -h, h, h, w, layer, len(gfx)))
    pads = []
    for i, (px, py) in enumerate(((-2.54, -2.54), (2.54, -2.54),
                                  (-2.54, 2.54), (2.54, 2.54))):
        pads.append('\t(pad "2" thru_hole circle (at %g %g) (size 2.8 2.8) (drill 1.7)\n'
                    '\t\t(layers "*.Cu" "*.Mask") (remove_unused_layers no)\n'
                    '\t\t(uuid "cccccccc-0000-4000-8000-%012d"))' % (px, py, i))
    open(os.path.join(d, "SMA_Vertical_THT_Universal.kicad_mod"), "w",
         encoding="utf-8").write(SMA % dict(gfx="\n".join(gfx), pads="\n".join(pads)))
    return d


# The RPi socket, drawn in OUR board frame with pin 1 at the footprint origin so
# it can be placed at rot 0 and no transform can silently mirror it.  Odd pins
# run in -x from pin 1; the even row is +2.54 in y.  Mounted on the UNDERSIDE.
def _socket(d):
    pads = []
    for n in range(1, 41):
        col = (n - 1) // 2
        px, py = -col * 2.54, (0.0 if n % 2 else 2.54)
        shape = "rect" if n == 1 else "circle"
        pads.append('\t(pad "%d" thru_hole %s (at %g %g) (size 1.7 1.7) (drill 1.0)\n'
                    '\t\t(layers "*.Cu" "*.Mask") (remove_unused_layers no)\n'
                    '\t\t(uuid "dddddddd-0000-4000-8000-%012d"))' % (n, shape, px, py, n))
    x0, x1 = -19 * 2.54 - 1.4, 1.4
    y0, y1 = -1.4, 2.54 + 1.4
    gfx = []
    for layer, w in (("B.SilkS", 0.12), ("B.CrtYd", 0.05), ("B.Fab", 0.1)):
        gfx.append('\t(fp_rect (start %g %g) (end %g %g)\n'
                   '\t\t(stroke (width %g) (type solid)) (fill no) (layer "%s")\n'
                   '\t\t(uuid "eeeeeeee-0000-4000-8000-%012d"))'
                   % (x0, y0, x1, y1, w, layer, len(gfx)))
    txt = ('(footprint "RPiHeader_2x20_Socket_Underside"\n'
           '\t(version 20240108)\n\t(generator "gpsdo-pynq-z2")\n'
           '\t(generator_version "9.0")\n\t(layer "B.Cu")\n'
           '\t(descr "2x20 2.54 mm socket, underside, pin 1 at the origin, odd row in -x")\n'
           '\t(tags "raspberry pi header socket")\n\t(attr through_hole)\n'
           '\t(property "Reference" "REF**"\n\t\t(at 0 -4.5 0) (layer "B.SilkS")\n'
           '\t\t(uuid "dddddddd-0000-4000-8000-000000000f01")\n'
           '\t\t(effects (font (size 1 1) (thickness 0.15)) (justify mirror)))\n'
           '\t(property "Value" "2x20 socket"\n\t\t(at 0 7 0) (layer "B.Fab")\n'
           '\t\t(uuid "dddddddd-0000-4000-8000-000000000f02")\n'
           '\t\t(effects (font (size 1 1) (thickness 0.15)) (justify mirror)))\n'
           + "\n".join(gfx) + "\n" + "\n".join(pads) + "\n)\n")
    open(os.path.join(d, "RPiHeader_2x20_Socket_Underside.kicad_mod"), "w",
         encoding="utf-8").write(txt)


def _tables(outdir):
    # ${KIPRJMOD} keeps these relative: a fresh git checkout resolves them
    # without anyone editing a path.
    open(os.path.join(outdir, "sym-lib-table"), "w", encoding="utf-8").write(
        '(sym_lib_table\n\t(version 7)\n'
        '\t(lib (name "GPSDO-PYNQ-Z2")(type "KiCad")'
        '(uri "${KIPRJMOD}/library/GPSDO-PYNQ-Z2.kicad_sym")(options "")'
        '(descr "symbols drawn for this board"))\n)\n')
    open(os.path.join(outdir, "fp-lib-table"), "w", encoding="utf-8").write(
        '(fp_lib_table\n\t(version 7)\n'
        '\t(lib (name "GPSDO-PYNQ-Z2")(type "KiCad")'
        '(uri "${KIPRJMOD}/library/GPSDO-PYNQ-Z2.pretty")(options "")'
        '(descr "footprints drawn for this board"))\n)\n')


def write(outdir):
    lib = os.path.join(outdir, "library")
    if not os.path.isdir(lib):
        os.makedirs(lib)
    _sym_lib(outdir)
    _d = _fp_lib(outdir)
    _socket(_d)
    _mounting(_d)
    _tables(outdir)
    return "library/, sym-lib-table, fp-lib-table"
