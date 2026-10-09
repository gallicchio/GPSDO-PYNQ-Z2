"""
kigen -- a very small KiCAD 9 schematic writer.

Targets the KiCAD 9 schematic s-expression format (version 20250114).  KiCAD 10
opens these files without complaint; the reverse is not true, which is why 9 is
the target.  See the Toolchain note at the top of ../README.md.

Everything is generated rather than drawn, so the header pin table in the design
document, the constraint file and the netlist all come from one source of truth
and cannot drift apart.

Coordinate conventions
----------------------
Schematic coordinates are millimeters, X right, Y DOWN, on a 1.27 mm grid.
Library symbol geometry is Y UP.  A library pin at (px, py) on a symbol placed
at (X, Y) with rotation `rot` (degrees, counter-clockwise as drawn) lands at

    x = X + px*cos(a) + py*sin(a)
    y = Y + px*sin(a) - py*cos(a)

with mirroring applied to (px, py) before rotation.  This transform was verified
against KiCAD's own multichannel demo: 78 of its 93 placed pins land exactly on a
wire endpoint under it (the remainder are pins that legitimately have no wire).
"""
import hashlib, math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, head, kids, kid, val, num

import kicad_env
SYMDIR = kicad_env.SYMBOLS          # KiCad 10 (REVB item 14); see gen/kicad_env.py
SCH_VERSION = "20250114"
GRID = 1.27

PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0),
         "A2": (594.0, 420.0), "A1": (841.0, 594.0)}


def uuid_for(*parts):
    """Deterministic UUID, so regenerating the project produces a clean git diff."""
    h = hashlib.sha1(("|".join(str(p) for p in parts)).encode()).hexdigest()
    return "%s-%s-%s-%s-%s" % (h[0:8], h[8:12], h[12:16], h[16:20], h[20:32])


def q(s):
    """Quote for a KiCAD s-expression.  Newlines must be escaped, not literal --
    a raw newline inside a quoted string makes KiCAD refuse to load the file."""
    return '"%s"' % (str(s).replace("\\", "\\\\").replace('"', '\\"')
                     .replace("\n", "\\n").replace("\r", ""))


def wrap(text, width=52):
    """Wrap note text to a newspaper column.  Wide boxes are hard to read; the
    Art of Electronics convention is a narrow column beside the thing it
    describes."""
    import textwrap
    out = []
    for para in str(text).split("\n"):
        out.extend(textwrap.wrap(para, width) if para.strip() else [""])
    return "\n".join(out)


def snap(v):
    """Snap a coordinate to the 1.27 mm schematic grid."""
    return round(round(float(v) / GRID) * GRID, 4)


def g(v):
    """Snap to the 1.27 mm grid and format for output."""
    return "%.4f" % snap(v)


# ---------------------------------------------------------------------------
# Stock symbol library access
# ---------------------------------------------------------------------------
class SymCache:
    def __init__(self):
        self._libs = {}
        self._sym = {}

    def _lib(self, libname):
        if libname not in self._libs:
            path = os.path.join(SYMDIR, libname + ".kicad_sym")
            symdir = os.path.join(SYMDIR, libname + ".kicad_symdir")
            files = ([os.path.join(symdir, f) for f in sorted(os.listdir(symdir))
                      if f.endswith(".kicad_sym")] if os.path.isdir(symdir)    # KiCad 10
                     else [path] if os.path.exists(path) else [])              # KiCad 9
            if not files:
                raise KeyError("no such symbol library: " + libname)
            syms = {}
            for f in files:
                doc = parse(open(f, encoding="utf-8").read())[0]
                syms.update({val(s): s for s in kids(doc, "symbol")})
            self._libs[libname] = syms
        return self._libs[libname]

    def get(self, lib_id):
        """Return (raw_text_block, pins) for 'Lib:Name'."""
        if lib_id in self._sym:
            return self._sym[lib_id]
        libname, name = lib_id.split(":", 1)
        lib = self._lib(libname)
        if name not in lib:
            raise KeyError("symbol %s not in %s" % (name, libname))
        node = lib[name]
        pins = []
        for sub in kids(node, "symbol"):
            for p in kids(sub, "pin"):
                at = kid(p, "at")
                pins.append(dict(num=val(kid(p, "number")),
                                 name=val(kid(p, "name")),
                                 x=num(at, 1), y=num(at, 2),
                                 angle=num(at, 3),
                                 etype=val(p, 1)))
        # also pull in any "extends" parent
        ext = kid(node, "extends")
        if ext:
            parent = val(ext)
            _, ppins = self.get("%s:%s" % (libname, parent))
            pins = ppins + pins
        self._sym[lib_id] = (node, pins)
        return self._sym[lib_id]

    def alias(self, base_lib_id, new_lib_id, pin_names=None, pin_types=None, value=None):
        """
        Derive a project-local symbol from a stock one, optionally relabelling
        pins.  Used where the pinout is right but the stock symbol's pin NAMES
        would mislead on the plotted sheet -- e.g. the TPS7A2033 in SOT-23-5
        has exactly the LP5907's pin numbering, so the LP5907 symbol is the
        right shape, but the part number on the sheet has to be the one you
        actually buy.  (Round 21: an earlier version of this comment claimed
        pin 4 was NR/SS rather than NC.  It is not -- see SBVS338H section 4.)
        """
        import copy
        node = copy.deepcopy(self._flatten(base_lib_id))
        _, pins = self.get(base_lib_id)
        node[1] = ("str", new_lib_id.split(":", 1)[1])
        for sub in kids(node, "symbol"):
            sub[1] = ("str", val(sub).replace(base_lib_id.split(":", 1)[1],
                                              new_lib_id.split(":", 1)[1], 1))
            for pin in kids(sub, "pin"):
                n = val(kid(pin, "number"))
                if pin_names and n in pin_names:
                    kid(pin, "name")[1] = ("str", pin_names[n])
                if pin_types and n in pin_types:
                    pin[1] = ("atom", pin_types[n])
        pins = [dict(pp) for pp in pins]
        for pp in pins:
            if pin_names and pp["num"] in pin_names:
                pp["name"] = pin_names[pp["num"]]
            if pin_types and pp["num"] in pin_types:
                pp["etype"] = pin_types[pp["num"]]
        self._sym[new_lib_id] = (node, pins)
        return new_lib_id

    def define(self, lib_id, pins, half_w=7.62, half_h=7.62,
               datasheet="", description="", ref="U"):
        """
        Build a symbol from scratch, for a part no stock KiCad library carries.

        `pins` is a list of (number, name, etype, side, offset), where side is
        one of l/r/t/b and offset is the distance along that side from center,
        positive up on the sides and positive right on top and bottom.  Drawn
        the Art of Electronics way: signals in on the left, out on the right,
        supply up, ground down -- which no stock 8-pin symbol does, because
        stock symbols follow the package's pin order rather than the circuit's
        signal flow.
        """
        geom = {"l": lambda o: (-half_w - 2.54, o, 0),
                "r": lambda o: (half_w + 2.54, o, 180),
                "t": lambda o: (o, half_h + 2.54, 270),
                "b": lambda o: (o, -half_h - 2.54, 90)}
        name = lib_id.split(":", 1)[1]
        out = ['(symbol "%s"' % name,
               "(exclude_from_sim no)(in_bom yes)(on_board yes)",
               '(property "Reference" "%s" (at %g %g 0)'
               '(effects (font (size 1.27 1.27))))' % (ref, -half_w, half_h + 1.27),
               '(property "Value" "%s" (at %g %g 0)'
               '(effects (font (size 1.27 1.27))))' % (name, half_w, half_h + 1.27),
               '(property "Footprint" "" (at 0 0 0)'
               '(effects (font (size 1.27 1.27)) (hide yes)))',
               '(property "Datasheet" "%s" (at 0 0 0)'
               '(effects (font (size 1.27 1.27)) (hide yes)))' % datasheet,
               '(property "Description" "%s" (at 0 0 0)'
               '(effects (font (size 1.27 1.27)) (hide yes)))' % description,
               '(symbol "%s_0_1" (rectangle (start %g %g) (end %g %g)'
               "(stroke (width 0.254)(type default))(fill (type background))))"
               % (name, -half_w, half_h, half_w, -half_h),
               '(symbol "%s_1_1"' % name]
        plist = []
        for numb, pname, etype, side, off in pins:
            px, py, ang = geom[side](off)
            out.append("(pin %s line (at %g %g %g)(length 2.54)"
                       '(name "%s" (effects (font (size 1.27 1.27))))'
                       '(number "%s" (effects (font (size 1.27 1.27)))))'
                       % (etype, px, py, ang, pname, numb))
            plist.append(dict(num=str(numb), name=pname, x=px, y=py,
                              angle=float(ang), etype=etype))
        out.append("))")
        node = parse("\n".join(out))[0]
        self._sym[lib_id] = (node, plist)
        return lib_id

    def _flatten(self, lib_id):
        """Resolve `extends` so the symbol is self-contained.  A schematic's
        lib_symbols block has to stand alone: KiCAD refuses to load a file whose
        symbol extends a parent that is not embedded alongside it."""
        libname, name = lib_id.split(":", 1)
        node, _ = self.get(lib_id)
        ext = kid(node, "extends")
        if not ext:
            return node
        pnode, _ = self.get("%s:%s" % (libname, val(ext)))

        def props(nd):
            return {val(c): c for c in kids(nd, "property")}
        merged = props(pnode)
        merged.update(props(node))               # child's properties win
        flags = [c for c in pnode[2:] if isinstance(c, list)
                 and head(c) not in ("property", "symbol", "extends")]
        renamed = []
        for sub in [c for c in pnode if isinstance(c, list) and head(c) == "symbol"]:
            sub = list(sub)
            sub[1] = ("str", val(sub).replace(val(ext), name, 1))
            renamed.append(sub)
        return [node[0], node[1]] + flags + list(merged.values()) + renamed

    def emit(self, lib_id):
        """Re-emit the library symbol for the schematic's lib_symbols block."""
        libname, name = lib_id.split(":", 1)
        txt = ser(self._flatten(lib_id))
        return txt.replace('(symbol "%s"' % name, '(symbol "%s"' % lib_id, 1)


def ser(node, indent=0):
    """Serialise a parsed s-expression back to text."""
    pad = "\t" * indent
    if isinstance(node, tuple):
        return q(node[1]) if node[0] == "str" else node[1]
    parts = []
    simple = all(not isinstance(c, list) for c in node)
    if simple:
        return "(" + " ".join(ser(c) for c in node) + ")"
    out = [pad + "(" + ser(node[0])]
    inline = []
    for c in node[1:]:
        if isinstance(c, list):
            if inline:
                out[-1] += " " + " ".join(inline); inline = []
            out.append(ser(c, indent + 1))
        else:
            inline.append(ser(c))
    if inline:
        out[-1] += " " + " ".join(inline)
    out.append(pad + ")")
    return "\n".join(out)


SYMS = SymCache()


def pin_xy(lib_id, ref_at, pin_number, mirror=None):
    """Absolute schematic (x, y) of a pin of a placed symbol."""
    X, Y, rot = ref_at
    _, pins = SYMS.get(lib_id)
    for p in pins:
        if p["num"] == str(pin_number):
            px, py = p["x"], p["y"]
            if mirror == "y":
                px = -px
            elif mirror == "x":
                py = -py
            # KiCAD's placement rotation is clockwise in schematic coordinates
            # (which are Y-down), so the angle enters negated.  Verified against
            # an exported netlist: a BAV99 at rot 90 puts pin 2, not pin 1, at
            # the top.
            a = math.radians(-rot)
            x = X + px * math.cos(a) + py * math.sin(a)
            y = Y + px * math.sin(a) - py * math.cos(a)
            return (snap(x), snap(y))
    raise KeyError("pin %s not on %s" % (pin_number, lib_id))


# ---------------------------------------------------------------------------
# Schematic sheet builder
# ---------------------------------------------------------------------------
class Sch:
    """One schematic page."""

    def __init__(self, project, filename, paper="A3", title="", rev="A",
                 company="", comments=(), sheet_uuid=None):
        self.project = project
        self.filename = filename
        self.paper = paper
        self.title = title
        self.rev = rev
        self.company = company
        self.comments = list(comments)
        self.uuid = sheet_uuid or uuid_for(project, filename)
        # Instance path for symbols on this sheet.  For the root that is just
        # "/<root uuid>"; for a child it must be "/<root uuid>/<sheet box uuid>",
        # where the second UUID is the sheet BOX in the parent, not the child
        # file's own uuid.  Getting this wrong makes KiCAD attribute the child's
        # contents to the root sheet in ERC.
        self.inst_path = "/" + self.uuid
        self.body = []          # emitted element text
        self._segs = []         # wire segments, for automatic junction insertion
        self._manual_j = set()  # junctions requested explicitly
        self._final = False
        self.libs = set()       # lib_ids used
        self._n = 0             # uuid salt
        self.refs = {}          # prefix -> next number

    # -- helpers -----------------------------------------------------------
    def _u(self, *k):
        self._n += 1
        return uuid_for(self.filename, self._n, *k)

    def _eff(self, size=1.27, justify=None, hide=False, bold=False, italic=False):
        s = "\n\t\t\t(font\n\t\t\t\t(size %.4f %.4f)" % (size, size)
        if bold:
            s += "\n\t\t\t\t(bold yes)"
        if italic:
            s += "\n\t\t\t\t(italic yes)"
        s += "\n\t\t\t)"
        if justify:
            s += "\n\t\t\t(justify %s)" % justify
        if hide:
            s += "\n\t\t\t(hide yes)"
        return "\t\t(effects%s\n\t\t)" % s

    # -- primitives --------------------------------------------------------
    def wire(self, x0, y0, x1, y1):
        """Record a wire.  Wires are emitted at render time, after the junction
        pass has had a chance to split them -- see finalize()."""
        x0, y0, x1, y1 = snap(x0), snap(y0), snap(x1), snap(y1)
        if (x0, y0) != (x1, y1):
            self._segs.append((x0, y0, x1, y1))
        return self

    def poly(self, pts, style="default", width=0):
        s = " ".join("(xy %s %s)" % (g(x), g(y)) for x, y in pts)
        self.body.append(
            "\t(polyline\n\t\t(pts\n\t\t\t%s\n\t\t)\n"
            "\t\t(stroke\n\t\t\t(width %.4f)\n\t\t\t(type %s)\n\t\t)\n"
            "\t\t(uuid %s)\n\t)" % (s, width, style, q(self._u("p", pts[0]))))
        return self

    def wires(self, *pts):
        for i in range(len(pts) - 1):
            self.wire(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        return self

    def junction(self, x, y):
        """Request a junction.  Emitted, and the wire split, in finalize()."""
        self._manual_j.add((snap(x), snap(y)))
        return self

    def nc(self, x, y):
        self.body.append("\t(no_connect\n\t\t(at %s %s)\n\t\t(uuid %s)\n\t)"
                         % (g(x), g(y), q(self._u("nc", x, y))))
        return self

    def label(self, x, y, name, rot=0, justify="left bottom", size=1.27):
        self.body.append(
            "\t(label %s\n\t\t(at %s %s %d)\n%s\n\t\t(uuid %s)\n\t)"
            % (q(name), g(x), g(y), rot, self._eff(size, justify), q(self._u("l", name, x, y))))
        return self

    def glabel(self, x, y, name, shape="bidirectional", rot=0, justify="left", size=1.27):
        self.body.append(
            "\t(global_label %s\n\t\t(shape %s)\n\t\t(at %s %s %d)\n"
            "\t\t(fields_autoplaced yes)\n%s\n\t\t(uuid %s)\n"
            "\t\t(property \"Intersheetrefs\" \"${INTERSHEET_REFS}\"\n"
            "\t\t\t(at %s %s %d)\n%s\n\t\t)\n\t)"
            % (q(name), shape, g(x), g(y), rot, self._eff(size, justify),
               q(self._u("gl", name, x, y)), g(x + 10), g(y), rot,
               self._eff(1.27, "left")))
        return self

    def text(self, x, y, s, size=1.27, bold=False, italic=False, justify="left bottom", rot=0):
        self.body.append(
            "\t(text %s\n\t\t(exclude_from_sim no)\n\t\t(at %s %s %d)\n%s\n\t\t(uuid %s)\n\t)"
            % (q(s), g(x), g(y), rot, self._eff(size, justify, bold=bold, italic=italic),
               q(self._u("t", s[:20], x, y))))
        return self

    def note(self, x, y, w, h, s, size=1.27, color=(255, 255, 194), cols=None):
        """A filled comment box.  If `cols` is given the text is wrapped to that
        many characters and the box height is computed from the result, so a
        note is always a narrow readable column rather than a wide slab."""
        if cols:
            s = wrap(s, cols)
            h = 1.905 + (s.count("\n") + 1) * size * 1.95
        self.body.append(
            "\t(text_box %s\n\t\t(exclude_from_sim no)\n\t\t(at %s %s 0)\n"
            "\t\t(size %s %s)\n\t\t(margins 0.9525 0.9525 0.9525 0.9525)\n"
            "\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n"
            "\t\t(fill\n\t\t\t(type color)\n\t\t\t(color %d %d %d 1)\n\t\t)\n"
            "%s\n\t\t(uuid %s)\n\t)"
            % (q(s), g(x), g(y), g(w), g(h), color[0], color[1], color[2],
               self._eff(size, "left top"), q(self._u("tb", s[:20], x, y))))
        return self

    def arrow(self, x0, y0, x1, y1, head=1.6):
        """A thin annotation leader with an arrowhead at (x1, y1).  Used to point
        a level box at the exact node it describes."""
        self.poly([(x0, y0), (x1, y1)], width=0.15)
        dx, dy = x1 - x0, y1 - y0
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / n, dy / n
        for sgn in (1, -1):
            px, py = -uy * sgn * 0.5, ux * sgn * 0.5
            self.poly([(x1, y1), (x1 - ux * head + px * head, y1 - uy * head + py * head)],
                      width=0.15)
        return self

    def rect(self, x, y, w, h, style="dash"):
        self.poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)], style=style)
        return self

    # -- symbols -----------------------------------------------------------
    def sym(self, lib_id, x, y, rot=0, ref=None, value="", footprint="",
            mirror=None, dnp=False, in_bom=True, on_board=True, fields=None,
            ref_dxy=(0, -2.54), val_dxy=(0, 2.54), hide_value=False,
            hide_ref=False, lcsc=None, desc=None, justify="left", fang=None):
        # Snap the placement to the grid BEFORE anything computes pin positions
        # from it, otherwise the symbol lands on the grid but pin_xy() returns
        # unsnapped coordinates and the wires miss the pins by a fraction of a
        # millimeter -- which KiCAD renders as connected and ERCs as not.
        x = snap(x); y = snap(y)
        self.libs.add(lib_id)
        u = self._u("s", ref or lib_id, x, y)
        props = []

        # KiCAD adds the symbol's rotation to a field's own angle when it draws
        # it, so a field on a rot-90 symbol with angle 0 comes out sideways.
        # Store the complement to keep every reference and value horizontal.
        # At rot 180 KiCAD flips the field rather than rotating it, so the
        # complement is not enough and the text comes out upside down; callers
        # pass fang=0 there.
        fang = (-rot) % 360 if fang is None else fang

        def prop(name, v, dx, dy, hide=False, size=1.27):
            props.append("\t\t(property %s %s\n\t\t\t(at %s %s %d)\n%s\n\t\t)"
                         % (q(name), q(v), g(x + dx), g(y + dy), fang,
                            self._eff(size, justify, hide=hide).replace("\t\t(", "\t\t\t(", 1)
                            .replace("\n\t\t", "\n\t\t\t")))
        prop("Reference", ref or "#U", ref_dxy[0], ref_dxy[1], hide=hide_ref)
        prop("Value", value, val_dxy[0], val_dxy[1], hide=hide_value)
        prop("Footprint", footprint, 0, 0, hide=True)
        prop("Datasheet", "~", 0, 0, hide=True)
        prop("Description", desc or "", 0, 0, hide=True)
        if lcsc:
            prop("LCSC", lcsc, 0, 0, hide=True)
        for k, v in (fields or {}).items():
            prop(k, v, 0, 0, hide=True)

        _, pins = SYMS.get(lib_id)
        pintxt = "".join("\t\t(pin %s\n\t\t\t(uuid %s)\n\t\t)\n"
                         % (q(p["num"]), q(self._u("pin", ref, p["num"]))) for p in pins)
        mir = "\n\t\t(mirror %s)" % mirror if mirror else ""
        self.body.append(
            "\t(symbol\n\t\t(lib_id %s)\n\t\t(at %s %s %d)%s\n\t\t(unit 1)\n"
            "\t\t(exclude_from_sim no)\n\t\t(in_bom %s)\n\t\t(on_board %s)\n\t\t(dnp %s)\n"
            "\t\t(uuid %s)\n%s\n%s"
            "\t\t(instances\n\t\t\t(project %s\n\t\t\t\t(path %s\n"
            "\t\t\t\t\t(reference %s)\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)"
            % (q(lib_id), g(x), g(y), rot, mir,
               "yes" if in_bom else "no", "yes" if on_board else "no",
               "yes" if dnp else "no", q(u), "\n".join(props), pintxt,
               q(self.project), q(self.inst_path), q(ref or "#U")))
        return _Placed(self, lib_id, (x, y, rot), mirror, ref)

    # -- child sheet box ---------------------------------------------------
    def sheet(self, x, y, w, h, name, filename, page):
        # The sheet BOX must not share a uuid with the child file's own uuid,
        # or KiCAD cannot tell the hierarchy apart and attributes the child's
        # contents to the parent sheet path.
        u = uuid_for(self.project, "sheetbox", filename)
        self.body.append(
            "\t(sheet\n\t\t(at %s %s)\n\t\t(size %s %s)\n"
            "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
            "\t\t(stroke\n\t\t\t(width 0.1524)\n\t\t\t(type solid)\n\t\t)\n"
            "\t\t(fill\n\t\t\t(color 0 0 0 0.0000)\n\t\t)\n\t\t(uuid %s)\n"
            "\t\t(property \"Sheetname\" %s\n\t\t\t(at %s %s 0)\n"
            "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.524 1.524)\n\t\t\t\t)\n"
            "\t\t\t\t(justify left bottom)\n\t\t\t)\n\t\t)\n"
            "\t\t(property \"Sheetfile\" %s\n\t\t\t(at %s %s 0)\n"
            "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.524 1.524)\n\t\t\t\t)\n"
            "\t\t\t\t(justify left top)\n\t\t\t)\n\t\t)\n"
            "\t\t(instances\n\t\t\t(project %s\n\t\t\t\t(path %s\n"
            "\t\t\t\t\t(page %s)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)"
            % (g(x), g(y), g(w), g(h), q(u), q(name), g(x), g(y - 0.7625),
               q(filename), g(x), g(y + h + 1.06), q(self.project),
               q("/" + self.uuid), q(str(page))))
        return u

    # -- output ------------------------------------------------------------
    def finalize(self):
        """
        Work out where junctions belong, SPLIT the wires there, and emit both.

        The splitting is the part that matters and it is not optional: a junction
        dot dropped in the interior of an unbroken wire does not join anything in
        KiCAD -- it actively breaks the wire's connectivity.  A junction must sit
        where wire ENDPOINTS meet, so any segment whose interior contains a
        junction point has to be cut there first.  A true crossing, where neither
        wire has an endpoint at the intersection, is deliberately left alone, so
        the DNP clamp's rail leg can cross the signal wire without joining it.
        """
        if self._final:
            return
        self._final = True
        from collections import Counter

        def interior(seg, p):
            x0, y0, x1, y1 = seg
            px, py = p
            if x0 == x1 == px:
                return min(y0, y1) < py < max(y0, y1)
            if y0 == y1 == py:
                return min(x0, x1) < px < max(x0, x1)
            return False

        pts = set(self._manual_j)
        ends = Counter()
        for x0, y0, x1, y1 in self._segs:
            ends[(x0, y0)] += 1
            ends[(x1, y1)] += 1
        for p, c in ends.items():
            if c >= 3:
                pts.add(p)
        for p in list(ends):
            if any(interior(sg, p) for sg in self._segs):
                pts.add(p)

        # split segments at every junction point that falls inside them
        segs = list(self._segs)
        changed = True
        while changed:
            changed = False
            out = []
            for sg in segs:
                cut = next((p for p in pts if interior(sg, p)), None)
                if cut:
                    x0, y0, x1, y1 = sg
                    out.append((x0, y0, cut[0], cut[1]))
                    out.append((cut[0], cut[1], x1, y1))
                    changed = True
                else:
                    out.append(sg)
            segs = out

        for x0, y0, x1, y1 in segs:
            self.body.append(
                "\t(wire\n\t\t(pts\n\t\t\t(xy %s %s) (xy %s %s)\n\t\t)\n"
                "\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n"
                "\t\t(uuid %s)\n\t)" % (g(x0), g(y0), g(x1), g(y1),
                                        q(self._u("w", x0, y0, x1, y1))))
        for (px, py) in sorted(pts):
            self.body.append(
                "\t(junction\n\t\t(at %s %s)\n\t\t(diameter 0)\n\t\t(color 0 0 0 0)\n"
                "\t\t(uuid %s)\n\t)" % (g(px), g(py), q(self._u("j", px, py))))
        return len(pts)

    # kept for callers written against the old name
    auto_junctions = finalize

    def render(self, sheet_instances=None):
        self.finalize()
    def render(self, sheet_instances=None):
        libtxt = "\n".join(SYMS.emit(l) for l in sorted(self.libs))
        libtxt = "\n".join("\t\t" + ln if ln.strip() else ln for ln in libtxt.split("\n"))
        tb = ["\t\t(title %s)" % q(self.title), "\t\t(rev %s)" % q(self.rev)]
        if self.company:
            tb.append("\t\t(company %s)" % q(self.company))
        for i, c in enumerate(self.comments[:9], start=1):
            tb.append("\t\t(comment %d %s)" % (i, q(c)))
        si = sheet_instances or '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)'
        return ("(kicad_sch\n\t(version %s)\n\t(generator \"gpsdo-pynq-z2-gen\")\n"
                "\t(generator_version \"9.0\")\n\t(uuid %s)\n\t(paper %s)\n"
                "\t(title_block\n%s\n\t)\n"
                "\t(lib_symbols\n%s\n\t)\n%s\n%s\n\t(embedded_fonts no)\n)\n"
                % (SCH_VERSION, q(self.uuid), q(self.paper), "\n".join(tb),
                   libtxt, "\n".join(self.body), si))

    def save(self, outdir, sheet_instances=None):
        path = os.path.join(outdir, self.filename)
        open(path, "w", encoding="utf-8").write(self.render(sheet_instances))
        return path


class _Placed:
    """Handle to a placed symbol, for wiring to its pins."""
    def __init__(self, sch, lib_id, at, mirror, ref):
        self.sch, self.lib_id, self.at, self.mirror, self.ref = sch, lib_id, at, mirror, ref

    def pin(self, n):
        return pin_xy(self.lib_id, self.at, n, self.mirror)

    def __repr__(self):
        return "<%s %s at %s>" % (self.ref, self.lib_id, self.at)
