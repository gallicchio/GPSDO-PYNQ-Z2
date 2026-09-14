#!/usr/bin/env python3
"""Write the two files JLCPCB's assembly service actually reads, plus the
hand-solder list for everything it will not fit.

  <out>/GPSDO-PYNQ-Z2_bom.csv   Comment, Designator, Footprint, LCSC
  <out>/GPSDO-PYNQ-Z2_cpl.csv   Designator, Mid X, Mid Y, Layer, Rotation
  <out>/hand_solder_bom.csv     the through-hole parts, to order loose

Only surface-mount, non-DNP parts with a part number go into the first two.
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


def write(outdir, rows=None, quiet=False):
    rows = rows or bomdata.components()
    os.makedirs(outdir, exist_ok=True)
    smt = [r for r in rows if r["cls"] == "smt"]
    tht = [r for r in rows if r["cls"] == "tht"]
    dnp = [r for r in rows if r["cls"] == "dnp"]

    # ---- BOM: one line per distinct part, designators joined --------------
    by = collections.defaultdict(list)
    for r in smt:
        by[(r["lcsc"], r["value"], r["fpshort"])].append(r["ref"])
    bom = os.path.join(outdir, "%s_bom.csv" % NAME)
    with open(bom, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC"])
        for (lcsc, value, fp), refs in sorted(by.items(),
                                              key=lambda kv: -len(kv[1])):
            refs = sorted(refs, key=lambda s: (len(s), s))
            w.writerow([value, ",".join(refs), fp, lcsc])

    # ---- CPL --------------------------------------------------------------
    cpl = os.path.join(outdir, "%s_cpl.csv" % NAME)
    with open(cpl, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in sorted(smt, key=lambda r: r["ref"]):
            w.writerow([r["ref"], "%.4f" % r["x"], "%.4f" % (-r["y"]),
                        r["side"].capitalize(), "%.4f" % norm_rot(r["rot"])])

    # ---- hand-solder list --------------------------------------------------
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

    if not quiet:
        print("  %-34s %d distinct parts, %d placements"
              % (os.path.basename(bom), len(by), len(smt)))
        print("  %-34s %d placements" % (os.path.basename(cpl), len(smt)))
        print("  %-34s %d parts + %d extras"
              % (os.path.basename(hand), len(hby), len(parts_map.EXTRAS)))
        print("  %-34s %d DNP + %d bare pads"
              % (os.path.basename(excl), len(dnp),
                 sum(1 for r in rows if r["cls"] == "nopart")))
    return dict(bom=bom, cpl=cpl, hand=hand, excluded=excl,
                distinct=len(by), placements=len(smt))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "release")
    write(out)
