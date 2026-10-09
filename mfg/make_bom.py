#!/usr/bin/env python3
"""Write the two files JLCPCB's assembly service actually reads, plus the
hand-solder list for everything it will not fit.

  <out>/GPSDO-PYNQ-Z2_bom.csv   Comment, Designator, Footprint, LCSC
  <out>/GPSDO-PYNQ-Z2_cpl_kicad_native.csv   Designator, Mid X, Mid Y, Layer, Rotation
  <out>/hand_solder_bom.csv     the through-hole parts, to order loose

Rev B: every non-DNP part with a part number goes into the first two,
THROUGH-HOLE INCLUDED -- JLCPCB fits the SMAs, headers, socket, jack and
terminals (CLAUDE_PCB.md section 8: nothing hand-soldered), so the hand-solder
list carries only what is not on the board (the jumper shunts).
Rev A put only surface-mount parts in them.
That matters: KiCad does NOT copy the schematic's DNP flag into the board, so
`kicad-cli pcb export pos --exclude-dnp` silently exports all 27 do-not-populate
parts on this design.  Everything here is filtered from bomdata.components()
instead, where the flag actually lives.

Coordinates follow kicad-cli's own convention -- X as-is, Y negated, rotation
normalised to (-180, 180] -- so the CPL and the Gerbers share one origin, the
board's own, which for this board is its lower-left corner at (0, 0).
"""
import csv, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bomdata, parts_map                                  # noqa: E402

NAME = "GPSDO-PYNQ-Z2"


def norm_rot(r):
    r = float(r) % 360.0
    return r - 360.0 if r > 180.0 else r


# ---------------------------------------------------------------------------
# JLCPCB rotation corrections.  Round 28.
#
# KiCad's footprint zero-orientation and JLCPCB's feeder zero-orientation
# differ per package family, so a CPL in KiCad's native convention has some
# packages loaded turned.  Round 23 declined to correct because no vetted table
# was to hand; the round-28 reviews all raised it, and one supplied a table
# (SOT-23: +180) that DISAGREES with the table used by the two most widely
# used KiCad->JLCPCB tools (SOT-23: -90).  So no table can be applied blind.
#
# What is done: TWO placement files are written.  `_cpl_kicad_native.csv` is KiCad-native,
# as before.  `_cpl_jlcpcb_upload.csv` applies the table below, which is the
# subset of matthewlai/JLCKicadTools `cpl_rotations_db.csv` (also imported by
# Bouni/kicad-jlcpcb-tools) that matches a footprint on this board, fetched
# 2026-09-14.  Its convention, from that tool's source: for a TOP-side part
# rotation = (kicad_rotation + correction) mod 360.  Everything here is top
# side.  FABRICATION_NOTES says which file to upload and which five packages to
# look at in JLCPCB's placement preview -- that preview, not this table, is the
# thing that actually guarantees a part goes down the right way round.
#
# Packages on this board with NO entry in that database (MSOP-10, SMA/SMB
# diodes, SOD-323, the FT5H oscillator, all passives) are left at KiCad's
# native rotation in both files.
# ---------------------------------------------------------------------------
def jlc_rotation(fpshort, rot, lcsc=None, side="top"):
    """(corrected rotation, correction applied) for one placement.

    Rev B: the PART's entry (parts_map.JLC_ROTATION_BY_PART) first, then the
    footprint's.  A bottom-side part is mirrored first, rot -> 180 - rot
    (CLAUDE_PCB.md section 8, confirmed on Icepi's ten), then corrected.  A
    part with no entry is left alone, and `unchecked()` below is what stops
    that being silent."""
    base = (180.0 - float(rot)) if side == "bottom" else float(rot)
    e = parts_map.JLC_ROTATION_BY_PART.get(lcsc) or parts_map.JLC_ROTATION.get(fpshort)
    if e is None:
        return norm_rot(base), 0
    return norm_rot(base + e[0]), e[0]


def jlc_datum(r):
    """Where JLCPCB's origin of this part lands on the board (x, y; y down).

    parts_map.JLC_DATUM gives it in our footprint's frame AS THE FILE STORES
    IT -- a bottom part's pads are already mirrored there, and footprint_check
    fits in that frame -- so it is only turned with the footprint, as KiCad
    does (angle counter-clockwise on screen, y down).  Checked against the
    board: every shifted point lands on the middle of its own pads, J4001's on
    the bottom included (a second mirror put it 48.26 mm off)."""
    import math
    d = parts_map.JLC_DATUM.get(r["lcsc"])
    if not d:
        return r["x"], r["y"]
    dx, dy = d
    a = math.radians(float(r["rot"]))
    return (r["x"] + dx * math.cos(a) + dy * math.sin(a),
            r["y"] - dx * math.sin(a) + dy * math.cos(a))


def unchecked(smt):
    """SMT footprints nobody has confirmed against a placement preview.

    Not a failure -- a new footprint starts here and that is correct.  It is
    reported because round 28's MSOP-10 and FT5H were silently uncorrected for
    five rounds, which is the same thing as being silently wrong."""
    known = (set(parts_map.JLC_ROTATION) | set(parts_map.JLC_ROTATION_OK)
             | set(parts_map.JLC_ROTATION_NA))
    n = collections.Counter(r["fpshort"] for r in smt
                            if r["lcsc"] not in parts_map.JLC_ROTATION_BY_PART)
    return sorted((fp, c) for fp, c in n.items() if fp not in known)


def write(outdir, rows=None, quiet=False):
    rows = rows or bomdata.components()
    os.makedirs(outdir, exist_ok=True)
    # Rev B: through-hole parts are assembled too; `smt` is now "placed".
    # Except the one through-hole part on the BOTTOM, the Raspberry Pi socket:
    # whether JLCPCB fits a bottom-side through-hole part on a top-side
    # assembly order, or needs the dearer both-sides service, is not
    # established, so it stays on the hand-solder list (as on rev A) until
    # somebody asks them.  FABRICATION_NOTES says so.
    smt = [r for r in rows if r["cls"] == "smt"
           or (r["cls"] == "tht" and r["side"] == "top")]
    tht = [r for r in rows if r["cls"] == "tht" and r["side"] == "bottom"]
    dnp = [r for r in rows if r["cls"] == "dnp"]

    # ---- BOM: one line per distinct part, designators joined --------------
    # ONE LINE PER LCSC CODE -- not per (code, value string), which is what
    # this did until round 32 and is a real defect rather than a cosmetic one.
    # JLCPCB matches a BOM line to a part BY ITS CODE, so two lines carrying
    # the same code are two lines matched to the same part: it refuses to
    # guess, sets BOTH quantities to zero, and waits for a human to tick two
    # boxes.  A BOM whose correctness depends on someone remembering to tick a
    # box is a BOM that will one day be uploaded by someone who does not.
    #
    # What shipped: C17738 on two lines, because the thirteen channel
    # terminations are drawn `51R 1%` and the external helper's is drawn
    # `51R`.  They are the same 0805 51 ohm part -- parts_map.py has said so
    # in its own comment since it was written -- and 13 + 1 = 14 pieces.
    #
    # A value string is a LABEL.  The code is the PART.  Group on the part,
    # label the line with the most specific of the strings, and say out loud
    # that the merge happened rather than doing it silently.
    by = collections.defaultdict(list)
    for r in smt:
        by[r["lcsc"]].append(r)
    lines, merged = [], []
    for lcsc, group in sorted(by.items()):
        fps = sorted({g["fpshort"] for g in group})
        if len(fps) > 1:
            raise SystemExit(
                "BOM: LCSC %s is used with %d different footprints (%s).  One "
                "code is one part, so this is a parts_map.py error, not "
                "something to merge." % (lcsc, len(fps), ", ".join(fps)))
        # most specific label first: longest string, ties broken alphabetically
        vals = sorted({g["value"] for g in group}, key=lambda v: (-len(v), v))
        if len(vals) > 1:
            merged.append((lcsc, vals))
        lines.append((vals[0],
                      sorted((g["ref"] for g in group),
                             key=lambda s: (len(s), s)),
                      fps[0], lcsc))
    bom = os.path.join(outdir, "%s_bom.csv" % NAME)
    with open(bom, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC"])
        for value, refs, fp, lcsc in sorted(lines, key=lambda t: -len(t[1])):
            w.writerow([value, ",".join(refs), fp, lcsc])
    if merged and not quiet:
        for lcsc, vals in merged:
            print("    BOM: %s is one part drawn with %d value strings (%s) "
                  "-- one line, labelled %r"
                  % (lcsc, len(vals), ", ".join(repr(v) for v in vals),
                     vals[0]))

    # ---- CPL, twice: KiCad-native and JLCPCB-corrected ---------------------
    cpl = os.path.join(outdir, "%s_cpl_kicad_native.csv" % NAME)
    with open(cpl, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in sorted(smt, key=lambda r: r["ref"]):
            w.writerow([r["ref"], "%.4f" % r["x"], "%.4f" % (-r["y"]),
                        r["side"].capitalize(), "%.4f" % norm_rot(r["rot"])])
    cplj = os.path.join(outdir, "%s_cpl_jlcpcb_upload.csv" % NAME)
    un = unchecked(smt)
    ncorr = collections.Counter()
    with open(cplj, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in sorted(smt, key=lambda r: r["ref"]):
            rot, corr = jlc_rotation(r["fpshort"], r["rot"], r["lcsc"], r["side"])
            if corr:
                ncorr[(r["fpshort"], corr)] += 1
            jx, jy = jlc_datum(r)
            w.writerow([r["ref"], "%.4f" % jx, "%.4f" % (-jy),
                        r["side"].capitalize(), "%.4f" % rot])

    # ---- hand-solder list --------------------------------------------------
    # This one DOES group by value string, on purpose, and must keep doing so.
    # Nobody uploads it: it is a shopping list and a bench list for a person,
    # and "10MHz IN / 1pps IN / EXT HELPER IN / CLK1 OUT" are four useful rows
    # even though all four are C496549, the same SMA jack.  C2337 is the same
    # 1x40 header strip snapped to 1x01 and to 1x02, so it legitimately
    # appears under two footprints as well.  The rule that one LCSC code gets
    # one line belongs to the assembly BOM above, where a machine matches it.
    hby = collections.defaultdict(list)
    for r in tht:
        hby[(r["lcsc"], r["value"], r["fpshort"], r["why"])].append(r["ref"])
    hand = os.path.join(outdir, "hand_solder_bom.csv")
    with open(hand, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC", "Qty", "Note"])
        for (lcsc, value, fp, why), refs in sorted(hby.items(),
                                                   key=lambda kv: -len(kv[1])):
            w.writerow([value, ",".join(sorted(refs, key=lambda s: (len(s), s))),
                        fp, lcsc, len(refs), why])
        for code, qty, note in parts_map.EXTRAS:
            w.writerow(["(not on the board)", "", "", code, qty, note])

    # ---- what was deliberately left out -----------------------------------
    excl = os.path.join(outdir, "excluded_from_assembly.csv")
    with open(excl, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Value", "Footprint", "Why",
                    "If you ever fit it"])
        for r in sorted(dnp, key=lambda r: r["ref"]):
            # the note is keyed on the first of a repeated group (D101, R106)
            code, note = parts_map.DNP_NOTES.get(
                r["ref"], parts_map.DNP_NOTES.get(
                    re.sub(r"^([A-Z]+)\d*(\d\d)$", r"\g<1>1\g<2>", r["ref"]),
                    (None, "")))
            w.writerow([r["ref"], r["value"], r["fpshort"],
                        "DNP in the schematic",
                        ((code + " -- ") if code else "") + (note or "")])
        for r in sorted([r for r in rows if r["cls"] == "nopart"],
                        key=lambda r: r["ref"]):
            w.writerow([r["ref"], r["value"], r["fpshort"],
                        parts_map.NO_PART.get(r["fpshort"], "no component")])

    if un and not quiet:
        print("    ROTATION: %d footprint(s) never checked against a "
              "placement preview: %s"
              % (len(un), ", ".join("%s x%d" % (f, c) for f, c in un)))
    if not quiet:
        print("  %-34s %d distinct parts, %d placements"
              % (os.path.basename(bom), len(by), len(smt)))
        print("  %-34s %d placements" % (os.path.basename(cpl), len(smt)))
        print("  %-34s %d placements, %d rotated: %s"
              % (os.path.basename(cplj), len(smt), sum(ncorr.values()),
                 ", ".join("%s %+d x%d" % (k[0], k[1], n)
                           for k, n in sorted(ncorr.items()))))
        print("  %-34s %d parts + %d extras"
              % (os.path.basename(hand), len(hby), len(parts_map.EXTRAS)))
        print("  %-34s %d DNP + %d bare pads"
              % (os.path.basename(excl), len(dnp),
                 sum(1 for r in rows if r["cls"] == "nopart")))
    return dict(bom=bom, cpl=cpl, cpl_jlc=cplj, hand=hand, excluded=excl,
                distinct=len(by), placements=len(smt),
                rotated=sum(ncorr.values()))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "release")
    write(out)
