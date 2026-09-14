#!/usr/bin/env python3
"""Gerbers, drill files, assembly drawings and the board's own parameters.

The parameters matter as much as the Gerbers.  Most of what a fab comes back
to ask about is not the artwork -- it is "what stackup?", "what finish?",
"is this 0.2 mm gap intentional?".  So this measures the board and writes the
answers down next to the files, rather than leaving them to be guessed.
"""
import os, re, shutil, subprocess, sys, zipfile, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bomdata                                          # noqa: E402
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
    return dict(
        size_mm=(round(box[2] - box[0], 2), round(box[3] - box[1], 2)),
        copper_layers=nlayers,
        min_track_mm=round(min(widths), 3) if widths else None,
        track_widths=sorted(set(round(w, 3) for w in widths)),
        via_sizes=sorted(set(vias)),
        min_via_drill_mm=round(min(d for _, d in vias), 3) if vias else None,
        pad_drills=sorted(set(round(d, 3) for d in drills)),
        min_pad_drill_mm=round(min(drills), 3) if drills else None,
        segments=len(widths), vias=len(vias))


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


def notes(outdir, m, boards=1):
    p = os.path.join(outdir, "FABRICATION_NOTES.txt")
    vias = ", ".join("%.2f/%.2f" % v for v in m["via_sizes"])
    with open(p, "w", encoding="utf-8") as f:
        f.write("""\
GPSDO DDMTD FRONT END  --  fabrication notes
============================================

BOARD
  Outline ............ %(w).2f x %(h).2f mm, rectangular, no cutouts, no slots
  Copper layers ...... %(nl)d   (F.Cu / In1.Cu / In2.Cu / B.Cu)
  Suggested stackup .. 1.6 mm FR-4, 1 oz outer, 0.5 oz inner  (JLC04161H-7628)
  Surface finish ..... ENIG preferred (lead-free HASL acceptable)
  Soldermask ......... any colour; silkscreen white
  Impedance control .. NOT required.  See the note below.

WHAT IS ON EACH LAYER
  F.Cu      components, most routing, and a GND pour
  In1.Cu    solid GND plane
  In2.Cu    the helper-clock distribution, as stripline between In1 and B.Cu
  B.Cu      solid GND plane; the Raspberry Pi socket mounts on this side

MINIMUMS ACTUALLY USED  (all well inside JLCPCB's 4-layer capability)
  Minimum track ...... %(mt)s mm
  Track widths used .. %(tw)s
  Via pad/drill ...... %(vias)s mm      (%(nv)d vias)
  Minimum via drill .. %(mvd)s mm
  Pad drill sizes .... %(pd)s
  Minimum pad drill .. %(mpd)s mm

IMPEDANCE
  No controlled-impedance service is required.  The helper traces on In2.Cu
  are drawn as nominal 50 ohm stripline against the two adjacent ground
  planes, but every one of them is source-terminated at its driver and none is
  longer than ~120 mm at 10 MHz, where the electrical length is a small
  fraction of a wavelength.  Build to the standard stackup.

ASSEMBLY
  Surface mount, TOP SIDE ONLY.  Nothing on the bottom is to be placed:
  the only bottom-side part is the Raspberry Pi socket, which is through hole
  and is hand soldered afterwards.
  See GPSDO-PYNQ-Z2_bom.csv and GPSDO-PYNQ-Z2_cpl.csv.
  Parts NOT to be fitted are listed in excluded_from_assembly.csv and appear
  in neither file -- please do not add them back.

WHAT TO SET ON THE JLCPCB ORDER FORM
  Base material ............ FR-4
  Layers ................... 4
  Dimensions ............... %(w).0f x %(h).0f mm, 1 piece, single design
  PCB thickness ............ 1.6 mm
  Impedance control ........ No
  Via covering ............. Tented
  Min via hole size/diameter 0.3 mm / 0.6 mm  (matches this design exactly)
  Board outline tolerance .. regular (+/-0.2 mm)
  Surface finish ........... ENIG  (lead-free HASL is acceptable)
  Remove order number ...... "Specify a location" or "No" -- there is room in
                             the lower-left margin below the title block
  PCB assembly ............. Yes, TOP side, %(qty)s boards
  Tooling holes ............ Added by JLCPCB
  Confirm parts placement .. Yes  -- NOT OPTIONAL, see ROTATION below

ROTATION  (round 28)
  KiCad's footprint zero-orientation and JLCPCB's feeder zero-orientation
  differ per package, and no two published correction tables agree on the
  SOT-23 family, which is 62 of this board's 457 placements.  So two
  placement files are supplied:
    %(name)s_cpl.csv ............... KiCad-native rotations
    %(name)s_cpl_jlc_corrected.csv . the same, with the JLCKicadTools table
                                     applied: SOT-23-x -90, SOT-223 +180,
                                     SOIC-8 +270.  Nothing else is touched.
  UPLOAD THE CORRECTED FILE.  Then, in JLCPCB's placement preview (the
  "Confirm parts placement" step), check these against the assembly drawing
  before approving:
    U102  (74LVC1G80, SOT-23-5)  pin 1 = the D input, bottom-left at rot 0
    Q2001 (DMN6068SE, SOT-223)   tab = drain, the wide pad
    U5001 (TMP1075, SOIC-8)      pin 1 dot
    U3001 (Si5351A, MSOP-10)     pin 1 dot  (NOT corrected: no table entry)
    D2001 (SS34, SMA)            cathode band  (NOT corrected: no table entry)
  If the SOT-23-5 preview is wrong, upload the native file instead; one of
  the two is right for their machines on the day, and the preview says which.

FILES
  %(name)s_gerbers.zip ........ Gerber RS-274X + Excellon drill + drill map
  %(name)s_bom.csv ............ assembly BOM
  %(name)s_cpl.csv ............ assembly placement file, KiCad-native rotations
  %(name)s_cpl_jlc_corrected.csv  the same with JLCPCB rotation corrections
  %(name)s_assembly_top.pdf ... placement drawing, top
  %(name)s_assembly_bottom.pdf  placement drawing, bottom
  hand_solder_bom.csv ......... through-hole parts, NOT for assembly
  excluded_from_assembly.csv .. DNP parts and bare test pads
  annotated_bom.md / .csv ..... prices, stock and notes (for the buyer, not
                                for the fab)
""" % dict(w=m["size_mm"][0], h=m["size_mm"][1], nl=m["copper_layers"],
           mt=m["min_track_mm"],
           tw=", ".join("%.2f" % t for t in m["track_widths"]),
           vias=vias, nv=m["vias"], mvd=m["min_via_drill_mm"],
           pd=", ".join("%.2f" % d for d in m["pad_drills"]),
           mpd=m["min_pad_drill_mm"], name=NAME, qty=boards))
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
