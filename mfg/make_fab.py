#!/usr/bin/env python3
"""Gerbers, drill files, assembly drawings and the board's own parameters.

The parameters matter as much as the Gerbers.  Most of what a fab comes back
to ask about is not the artwork -- it is "what stackup?", "what finish?",
"is this 0.2 mm gap intentional?".  So this measures the board and writes the
answers down next to the files, rather than leaving them to be guessed.
"""
import math as _m
import os, re, shutil, subprocess, sys, textwrap, zipfile, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bomdata, parts_map                                          # noqa: E402
from sexp import parse, kids, kid, val                  # noqa: E402

NAME = "GPSDO-PYNQ-Z2"
PCB = os.path.join(ROOT, NAME + ".kicad_pcb")

# Everything JLCPCB needs for a 4-layer board, in their order.
GERBER_LAYERS = ("F.Cu,In1.Cu,In2.Cu,B.Cu,"
                 "F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,"
                 "F.Mask,B.Mask,Edge.Cuts")


def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("%s\n%s%s" % (" ".join(args[-3:]), r.stdout, r.stderr))
    return r.stdout


def measure():
    """Minimum track width, clearance-relevant drill sizes, layer count."""
    doc = parse(open(PCB, encoding="utf-8").read())[0]
    widths, drills, vias = [], [], []
    for s in kids(doc, "segment"):
        w = kid(s, "width")
        if w:
            widths.append(float(val(w[1])))
    for v in kids(doc, "via"):
        sz, dr = kid(v, "size"), kid(v, "drill")
        if sz and dr:
            vias.append((float(val(sz[1])), float(val(dr[1]))))
    for f in kids(doc, "footprint"):
        for p in kids(f, "pad"):
            d = kid(p, "drill")
            if d and len(d) > 1:
                try:
                    drills.append(float(val(d[1])))
                except ValueError:
                    pass
    nlayers = 0
    ls = kid(doc, "layers")
    if ls:
        nlayers = sum(1 for e in ls[1:]
                      if isinstance(e, (list, tuple)) and len(e) > 1
                      and str(val(e[1])).endswith(".Cu"))
    box = bomdata.board_box()
    # ---- how close any PLACED part gets to the board edge ----------------
    # Round 29.  JLCPCB's assembly line holds the panel by its edges, and a
    # part closer than their rail allowance means a break-away rail: a
    # different panel, a different price, and a conversation.  No KiCad DRC
    # rule looks at this -- `copper_edge_clearance` is about copper, not about
    # whether a nozzle can reach -- so measure it here and put the number
    # where the buyer will see it before they order.
    import math as _mm
    edge, edge_ref = None, ""
    for f in kids(doc, "footprint"):
        attrs = [val(a) for a in (kid(f, "attr") or [])[1:]]
        if "smd" not in attrs:
            continue                      # through hole: no nozzle reaches for it
        fref = ([val(pr[2]) for pr in kids(f, "property")
                 if val(pr[1]) == "Reference"] or [""])[0]
        at = kid(f, "at")
        fx, fy = float(val(at[1])), float(val(at[2]))
        fa = _mm.radians(-float(val(at[3]))) if len(at) > 3 else 0.0
        ca, sa = _mm.cos(fa), _mm.sin(fa)
        for pd in kids(f, "pad"):
            pa, ps = kid(pd, "at"), kid(pd, "size")
            if not pa or not ps:
                continue
            lx, ly = float(val(pa[1])), float(val(pa[2]))
            r = 0.5 * _mm.hypot(float(val(ps[1])), float(val(ps[2])))
            ax, ay = fx + lx * ca - ly * sa, fy + lx * sa + ly * ca
            d = min(ax - box[0], ay - box[1], box[2] - ax, box[3] - ay) - r
            if edge is None or d < edge:
                edge, edge_ref = d, fref
    return dict(
        size_mm=(round(box[2] - box[0], 2), round(box[3] - box[1], 2)),
        copper_layers=nlayers,
        min_track_mm=round(min(widths), 3) if widths else None,
        track_widths=sorted(set(round(w, 3) for w in widths)),
        via_sizes=sorted(set(vias)),
        min_via_drill_mm=round(min(d for _, d in vias), 3) if vias else None,
        pad_drills=sorted(set(round(d, 3) for d in drills)),
        min_pad_drill_mm=round(min(drills), 3) if drills else None,
        segments=len(widths), vias=len(vias),
        smt_to_edge_mm=round(edge, 2) if edge is not None else None,
        smt_to_edge_ref=edge_ref)


def export(outdir):
    cli = bomdata._kicad_cli()
    gerb = os.path.join(outdir, "gerbers")
    if os.path.isdir(gerb):
        shutil.rmtree(gerb)
    os.makedirs(gerb, exist_ok=True)
    run(cli + ["pcb", "export", "gerbers", "-o", gerb, "--layers", GERBER_LAYERS,
               "--no-protel-ext", "--subtract-soldermask", PCB])
    run(cli + ["pcb", "export", "drill", "-o", gerb, "--format", "excellon",
               "--drill-origin", "absolute", "--excellon-units", "mm",
               "--excellon-zeros-format", "decimal",
               "--generate-map", "--map-format", "gerberx2", PCB])
    zpath = os.path.join(outdir, "%s_gerbers.zip" % NAME)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(gerb)):
            z.write(os.path.join(gerb, fn), fn)
    # ---- assembly drawings, one per side ---------------------------------
    # Assembly drawings.  F.Fab carries the part outlines, the pin-1 marks and
    # the reference designators; the silkscreen is left OFF because on this
    # board it is mostly user-facing legend text and it buries the thing the
    # drawing exists to show.  No drawing sheet either -- with the border the
    # 207 x 180 board sat in the corner of an A2 page at a third scale.
    asm = []
    for side, fab, mirror in (("top", "F.Fab", False), ("bottom", "B.Fab", True)):
        p = os.path.join(outdir, "%s_assembly_%s.pdf" % (NAME, side))
        # Omitting --include-border-title is what leaves the drawing sheet out;
        # there is no separate flag.  The bottom view is mirrored, which is how
        # you look at the underside of a board with it in your hand.
        run(cli + ["pcb", "export", "pdf", "-o", p,
                   "--layers", "%s,Edge.Cuts" % fab, "--mode-single",
                   "--exclude-value"]
                  + (["--mirror"] if mirror else []) + [PCB])
        asm.append(p)
    return zpath, gerb, asm


def pin1_corner(ref):
    """Which corner of its own body pad 1 of `ref` sits in, on this board.

    ROUND 34.  "Check pin 1 in the preview" is only checkable if the notes say
    where pin 1 is SUPPOSED to be, and the footprints' own pin-1 marks are
    sometimes two 0.45 mm stubs (the FT5H) that are easy to read as belonging
    to the neighbouring part.  So derive it: north is the screw-terminal edge
    of the board, south is the Raspberry Pi socket edge.  Derived, so it
    cannot go stale, and stated physically so it does not depend on which way
    up anyone's viewer draws the thing."""
    src = open(PCB, encoding="utf-8").read()
    for b in src.split('(footprint "')[1:]:
        if '"%s"' % ref not in b:
            continue
        fat = re.search(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", b)
        if not fat:
            continue
        fx, fy = float(fat.group(1)), float(fat.group(2))
        fr = float(fat.group(3) or 0)
        a_ = _m.radians(-fr)
        ca, sa = _m.cos(a_), _m.sin(a_)
        pad = re.search(r'\(pad "1" \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)', b)
        if not pad:
            return ""
        px, py = float(pad.group(1)), float(pad.group(2))
        # ROUND 35: this was `fx + px*ca + py*sa, fy - px*sa + py*ca`, which
        # is the transpose -- it mirrors every part placed at a non-zero
        # rotation and agrees with the truth only at rot 0, so it read right
        # on eight of ten parts and put U3001's and X3001's pad 1 in the
        # opposite corner.  This is place.pads()' formula, the one the router
        # uses, which KiCad's own DRC has validated at 0 unconnected items.
        bx, by = fx + px * ca - py * sa, fy + px * sa + py * ca
        # file y grows DOWNWARD, so a bigger y is nearer the socket = south
        ns = "north" if by < fy - 0.05 else ("south" if by > fy + 0.05 else "")
        ew = "east" if bx > fx + 0.05 else ("west" if bx < fx - 0.05 else "")
        return "-".join(s for s in (ns, ew) if s) or "centre"
    return ""


# The packages where getting pin 1 wrong is a fault rather than a cosmetic
# complaint.  Everything else on this board is a two-terminal unpolarised
# passive, where which way round it goes is not a question.
POLARISED = ("SOT-23-5", "SOT-23-6", "SOT-223-3_TabPin2",
             "SOIC-8_3.9x4.9mm_P1.27mm", "MSOP-10_3x3mm_P0.5mm",
             "Oscillator_SMD_Fox_FT5H_5.0x3.2mm",
             "D_SMA", "D_SMB", "D_SOD-323")


def symmetric_parts():
    """Refs whose terminals are electrically interchangeable.

    ROUND 36.  Jason noticed D6001 looks the same either way round in the
    preview and asked whether it mattered.  It does not, and the netlist says
    so without anyone having to know the part: a bidirectional TVS carries
    pinfunctions A1/A2 -- two anodes, no cathode -- where a real diode carries
    K and A.  Derived rather than listed, so a part swap cannot make this
    stale.  Round 35 called all three diodes "cathode marked, pad 1", which
    was right for the SS34s and the Zener and wrong for this one."""
    src = open(os.path.join(HERE, "_netlist.net"), encoding="utf-8").read()
    fns = collections.defaultdict(set)
    for m in re.finditer(r'\(node \(ref "([^"]+)"\) \(pin "[^"]*"\)'
                         r'\s*\(pinfunction "([^"]*)"\)', src):
        fns[m.group(1)].add(m.group(2))
    return {r for r, f in fns.items()
            if len(f) > 1 and all(re.fullmatch(r"A\d+", x) for x in f)}


def pin1_checklist():
    """Where the placement preview's pin-1 dot must land, part by part.

    ROUND 35.  "Confirm pin 1 in the preview" was an instruction nobody could
    act on, because it never said what the right answer was -- which is how
    X3001 got argued about for two rounds.  This is the answer, derived from
    the board.

    Grouped by footprint AND by board rotation, because they differ within one
    BOM row: the 59 SOT-23-5s sit at four different rotations and so their pin
    1 points four different ways.  The rotation CORRECTION is per footprint,
    though, so confirming one part per footprint confirms the lot -- as long
    as it is checked against its own rotation's row."""
    rows = [r for r in bomdata.components()
            if r["cls"] == "smt" and r["fpshort"] in POLARISED]
    g = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        g[r["fpshort"]][(int(round(float(r["rot"]))), pin1_corner(r["ref"]))]\
            .append(r["ref"])
    out = []
    for fp in sorted(g):
        n = sum(len(v) for v in g[fp].values())
        out.append("    %s  (%d)" % (fp, n))
        for (rot, corner), refs in sorted(g[fp].items()):
            refs = sorted(refs, key=lambda s: (len(s), s))
            shown = ", ".join(refs[:5])
            if len(refs) > 5:
                shown += " ... +%d more" % (len(refs) - 5)
            out.append("      rot %4d -> pin 1 %-11s x%-3d %s"
                       % (rot, corner, len(refs), shown))
    sym = symmetric_parts()
    hit = sorted(r["ref"] for r in rows if r["ref"] in sym)
    if hit:
        out.append("    ORIENTATION-FREE, ignore the pin-1 dot on these: %s"
                   % ", ".join(hit))
        out.append("      their terminals are interchangeable (a bidirectional"
                   " TVS: pins A1/A2, no cathode), so no rotation of any"
                   " multiple of 180 can be wrong.")
    out.append("    %d polarised parts; the other %d are unpolarised "
               "two-terminal passives." % (len(rows) - len(hit),
                                           458 - len(rows) + len(hit)))
    return "\n".join(out)


def rotation_table():
    """The rotation corrections, from parts_map.py, as fab-note lines.

    Printed from the same dict the CPL is generated from, so the notes cannot
    describe a correction the file does not apply."""
    import make_bom
    rows = bomdata.components()
    placed = [r for r in rows if r["cls"] == "smt"
              or (r["cls"] == "tht" and r["side"] == "top")]
    n = collections.Counter(r["fpshort"] for r in placed
                            if r["lcsc"] not in parts_map.JLC_ROTATION_BY_PART)
    nb = collections.Counter(r["lcsc"] for r in placed)
    def wrap(s):
        return textwrap.fill(s, width=74, initial_indent=" " * 8,
                             subsequent_indent=" " * 8)

    out = []
    for fp, (corr, who, look) in sorted(parts_map.JLC_ROTATION.items()):
        # Rev B: a footprint this board no longer uses is left out -- its row
        # named rev A's MSOP-10 Si5351 as U3001, which is now the QFN-20.
        # The parts named are the ones rev A's preview was read off.
        if not n.get(fp, 0):
            continue
        out.append("    %-36s %+4d  x%-3d  read on rev A: %s"
                   % (fp, corr, n.get(fp, 0), who))
        ref = re.match(r"[A-Z]+\d+", who)
        c = pin1_corner(ref.group(0)) if ref else ""
        if c:
            out.append(wrap("on %s, pad 1 is at the %s corner of its own body"
                            % (ref.group(0), c)))
        out.append(wrap(look))
    for fp, (who, why) in sorted(parts_map.JLC_ROTATION_OK.items()):
        out.append("    %-36s    0  x%-3d  %s" % (fp, n.get(fp, 0), who))
        out.append(wrap(why))
    out.append("")
    out.append("  Rev B, PER PART (these win over the footprint rows above), PREDICTED")
    out.append("  from JLCPCB's own land pattern of each code; confirm each in the preview:")
    for code, (corr, how, look) in sorted(parts_map.JLC_ROTATION_BY_PART.items()):
        d = parts_map.JLC_DATUM.get(code)
        out.append("    %-9s %+4d  x%-3d  %s%s" % (code, corr, nb.get(code, 0), look,
                   ("; CPL point moved (%+.2f, %+.2f) mm to their origin" % d) if d else ""))
        out.append(wrap(how))
    return "\n".join(out)


def notes(outdir, m, boards=1):
    p = os.path.join(outdir, "FABRICATION_NOTES.txt")
    vias = ", ".join("%.2f/%.2f" % v for v in m["via_sizes"])
    with open(p, "w", encoding="utf-8") as f:
        f.write("""\
GPSDO DDMTD FRONT END, REV B  --  fabrication notes
====================================================

BOARD
  Outline ............ %(w).2f x %(h).2f mm, rectangular, no cutouts, no slots
  Copper layers ...... %(nl)d   (F.Cu / In1.Cu / In2.Cu / B.Cu)
  Suggested stackup .. 1.6 mm FR-4, 1 oz outer, 0.5 oz inner  (JLC04161H-7628)
  Surface finish ..... ENIG, 1 U" gold (see the order form below)
  Soldermask ......... green (Economic PCBA does 4 layers in green only);
                       silkscreen white
  Impedance control .. NOT required.  See the note below.

WHAT IS ON EACH LAYER
  F.Cu      components, most routing, and a GND pour
  In1.Cu    solid GND plane
  In2.Cu    the helper-clock distribution and the slow buses, between the
            In1 GND plane and the B.Cu +3V3_A plane
  B.Cu      the +3V3_A PLANE (rev B item 5; rev A had a second GND pour here);
            the Raspberry Pi socket mounts on this side

MINIMUMS ACTUALLY USED  (all well inside JLCPCB's 4-layer capability)
  Minimum track ...... %(mt)s mm
  Track widths used .. %(tw)s
  Via pad/drill ...... %(vias)s mm      (%(nv)d vias)
  Minimum via drill .. %(mvd)s mm
  Pad drill sizes .... %(pd)s
  Minimum pad drill .. %(mpd)s mm
  Closest SMT pad to the board edge .. %(edge)s mm  (%(edgeref)s)
      An ASSEMBLY number, not a fabrication one, and no KiCad rule checks it:
      `copper_edge_clearance` is about copper, not about whether a nozzle and
      a clamp can both reach.  If it is inside your rail allowance the panel
      needs a break-away rail -- PLEASE SAY SO RATHER THAN SHIFTING THE PART.
      Everything nearer the edge than this is through hole (the SMA jacks, the
      screw terminals, the barrel jack, the two bench posts and the 2x20
      socket), all fitted by JLCPCB, by hand or selective solder.

IMPEDANCE
  No controlled-impedance service is required.  The helper traces on In2.Cu
  are drawn as nominal 50 ohm stripline between the In1 GND plane and the
  B.Cu +3V3_A plane, but every one of them is source-terminated at its driver and none is
  longer than ~120 mm at 10 MHz, where the electrical length is a small
  fraction of a wavelength.  Build to the standard stackup.

ASSEMBLY  (rev B: JLCPCB fits the through-hole parts too)
  TOP SIDE: every surface-mount part, AND every through-hole part on the top:
  the 27 SMA jacks, the 13 three-pin 50R/PARK headers, the 2x10 debug header,
  the two bench pins, the barrel jack and the five screw terminals.  Each
  header is ordered at its own length (XFCN PZ254V), not as a strip.
  BOTTOM SIDE: one part, the Raspberry Pi 2x20 socket J4001 (through hole,
  ZHOURI 2.54-2*20, C2977589), IN the BOM and the CPL (Layer: Bottom).  Its
  pins come through to the top, among the top-side parts: solder them by
  hand or selectively, not on a wave.  The socket must sit flat and square
  on the board: it mates with the PYNQ-Z2's header pins.  It is unkeyed, so
  either way round fits; the CPL turns it as the preview shows.
  See GPSDO-PYNQ-Z2_bom.csv and GPSDO-PYNQ-Z2_cpl_jlcpcb_upload.csv.
  Parts NOT to be fitted are listed in excluded_from_assembly.csv and appear
  in neither file -- please do not add them back.

WHAT TO SET ON THE JLCPCB ORDER FORM, in the form's own order
(CLAUDE_PCB.md section 8, the form as of 2026-10-09; a field not listed
stays at its default)
  PCB
    Base Material ............ FR-4
    Layers ................... %(nl)d
    Dimensions ............... %(w).1f x %(h).1f mm
    PCB Qty .................. 5 (the minimum)
    Product Type ............. Industrial/Consumer electronics
  PCB Specifications
    Different Design ......... 1
    Delivery Format .......... Single PCB
    PCB Thickness ............ 1.6 mm
    PCB Color ................ Green  (Economic PCBA does 4 layers in green
                               only; any other colour forces Standard PCBA)
    Silkscreen ............... White
    Material Type ............ FR4 TG135 (default)
    Surface Finish ........... ENIG, 1 U" gold -- NOT the default OSP: QFN-20,
                               TSSOP-16 and SC-70-6 pads, through-hole parts
                               soldered after reflow, and test pads to probe
  High-spec Options
    Outer / Inner Copper ..... 1 oz / 0.5 oz (defaults)
    Specify Stackup .......... JLC04161H-7628 (the default 4-layer stackup)
    Via Covering ............. Tented
    Min via hole/diameter .... 0.3 mm / (0.4/0.45 mm), the default: this
                               board's vias are %(vias)s mm
    Board Outline Tolerance .. +/-0.2 mm (regular)
    Mark on PCB .............. Remove Mark
    Electrical Test .......... Flying Probe Fully Test (default)
  PCB Assembly
    PCBA Type ................ Standard (through-hole parts, and two sides)
    Assembly Side ............ Both Sides: J4001 is the only bottom part
    PCBA Qty ................. %(qty)s
    Tooling holes ............ Added by JLCPCB
    Confirm Parts Placement .. YES -- NOT OPTIONAL, see ROTATION below
  Then upload GPSDO-PYNQ-Z2_bom.csv and GPSDO-PYNQ-Z2_cpl_jlcpcb_upload.csv.

ROTATION  (round 33)
  KiCad's footprint zero-orientation and JLCPCB's feeder zero-orientation are
  not the same, and the offset is a property of JLCPCB's library.  Two
  placement files are supplied:
    %(name)s_cpl_kicad_native.csv ............... KiCad-native rotations
    %(name)s_cpl_jlcpcb_upload.csv . the same, corrected.  UPLOAD THIS ONE.
  Round 28 built the corrections from the JLCKicadTools table.  Round 33
  rebuilt them from YOUR OWN placement preview, which is the only authority,
  and two of the five were wrong -- one of them on 59 parts:
%(rot)s
  Still confirm them in the preview before approving.  Two footprints on this
  board have never been checked against a preview at all, both polarised:
    D2003 (5.6V 5W Zener, SMB)   cathode band
    D6001 (PESD5V0S1BA, SOD-323) cathode band
  If the preview disagrees, do NOT turn parts in JLCPCB's viewer: say which,
  and the generator's table changes (mfg/parts_map.py: JLC_ROTATION_BY_PART
  for a part, JLC_ROTATION for a footprint), so the next upload is right too.

PIN 1, PART BY PART  (round 35)
  Where the preview's pin-1 dot must land.  North is the screw-terminal edge
  of the board, south is the Raspberry Pi socket edge.  Every one of these is
  computed from the board, and the same arithmetic has been checked against
  KiCad's own pcbnew for all 458 placements.
%(pin1)s
  Every polarised footprint above carries a filled pin-1 triangle of its own
  EXCEPT the FT5H oscillator, which ships with none; round 35 prints a 0.8 mm
  dot beside its pin 1.  The SS34s, the Zener and the SMAJ18A mark the
  CATHODE, which is pad 1, as the closed end of the silkscreen outline.

FILES
  %(name)s_gerbers.zip ........ Gerber RS-274X + Excellon drill + drill map
  %(name)s_bom.csv ............ assembly BOM
  %(name)s_cpl_kicad_native.csv ............ assembly placement file, KiCad-native rotations
  %(name)s_cpl_jlcpcb_upload.csv  the same with JLCPCB rotation corrections
  %(name)s_assembly_top.pdf ... placement drawing, top
  %(name)s_assembly_bottom.pdf  placement drawing, bottom
  hand_solder_bom.csv ......... the 13 jumper shunts per board, shipped
                                loose: NOT for assembly
  excluded_from_assembly.csv .. DNP parts and bare test pads
  annotated_bom.md / .csv ..... prices, stock and notes (for the buyer, not
                                for the fab)
""" % dict(w=m["size_mm"][0], h=m["size_mm"][1], nl=m["copper_layers"],
           mt=m["min_track_mm"],
           tw=", ".join("%.2f" % t for t in m["track_widths"]),
           vias=vias, nv=m["vias"], mvd=m["min_via_drill_mm"],
           pd=", ".join("%.2f" % d for d in m["pad_drills"]),
           mpd=m["min_pad_drill_mm"], edge=m["smt_to_edge_mm"],
           edgeref=m["smt_to_edge_ref"], name=NAME, qty=boards,
           rot=rotation_table(), pin1=pin1_checklist()))
    return p


def main(outdir, boards=1):
    os.makedirs(outdir, exist_ok=True)
    m = measure()
    z, gerb, asm = export(outdir)
    n = notes(outdir, m, boards)
    print("  %-34s %d files" % (os.path.basename(z),
                                len(os.listdir(gerb))))
    for a in asm:
        print("  %-34s" % os.path.basename(a))
    print("  %-34s" % os.path.basename(n))
    print("  board %.1f x %.1f mm, %d layers, min track %.2f mm, "
          "min via drill %.2f mm, min pad drill %.2f mm"
          % (m["size_mm"][0], m["size_mm"][1], m["copper_layers"],
             m["min_track_mm"], m["min_via_drill_mm"], m["min_pad_drill_mm"]))
    return m


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "release"))
