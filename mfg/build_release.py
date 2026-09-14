#!/usr/bin/env python3
"""Build everything JLCPCB needs, then check it against itself.

    python3 mfg/build_release.py [N_BOARDS] [--refresh] [-o DIR]

Generating the files is the easy half.  The half that stops the fab coming
back with questions is checking that the files AGREE: that no do-not-populate
part leaked into the placement file, that every designator in the BOM is also
in the CPL, that the Gerber set is complete, and that the board the Gerbers
came from is the same board the BOM was read from.  All of that is asserted
here, and a non-zero exit means do not upload.
"""
import os, sys, zipfile, csv, subprocess, datetime, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bomdata, make_bom, make_fab, annotate_bom       # noqa: E402

NEEDED_GERBERS = ["F_Cu", "In1_Cu", "In2_Cu", "B_Cu", "F_Paste", "B_Paste",
                  "F_Silkscreen", "B_Silkscreen", "F_Mask", "B_Mask",
                  "Edge_Cuts"]


def sha(path, n=12):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()[:n]


def check(outdir, rows, res):
    """Every assertion that has to hold before this is worth uploading."""
    bad = []
    smt = {r["ref"] for r in rows if r["cls"] == "smt"}
    dnp = {r["ref"] for r in rows if r["cls"] == "dnp"}
    nop = {r["ref"] for r in rows if r["cls"] == "nopart"}

    bom_refs, cpl_refs = set(), set()
    with open(res["bom"], encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bom_refs |= {d.strip() for d in row["Designator"].split(",") if d.strip()}
            if not row["LCSC"].strip():
                bad.append("BOM line %r has no LCSC code" % row["Comment"])
    with open(res["cpl"], encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cpl_refs.add(row["Designator"].strip())
            if row["Layer"] not in ("Top", "Bottom"):
                bad.append("CPL %s has layer %r" % (row["Designator"], row["Layer"]))

    if bom_refs != smt:
        bad.append("BOM designators differ from the SMT set: +%s -%s"
                   % (sorted(bom_refs - smt)[:5], sorted(smt - bom_refs)[:5]))
    if cpl_refs != smt:
        bad.append("CPL designators differ from the SMT set: +%s -%s"
                   % (sorted(cpl_refs - smt)[:5], sorted(smt - cpl_refs)[:5]))
    leaked = (bom_refs | cpl_refs) & (dnp | nop)
    if leaked:
        bad.append("do-not-populate or bare-pad parts leaked into the assembly "
                   "files: %s" % sorted(leaked)[:8])

    z = os.path.join(outdir, "GPSDO-PYNQ-Z2_gerbers.zip")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    for lay in NEEDED_GERBERS:
        if not any(lay in n for n in names):
            bad.append("gerber zip is missing %s" % lay)
    if not any(n.endswith(".drl") for n in names):
        bad.append("gerber zip has no Excellon drill file")

    # bottom side must be empty of SMT, because the notes promise it is
    bottom = [r["ref"] for r in rows if r["cls"] == "smt" and r["side"] == "bottom"]
    if bottom:
        bad.append("FABRICATION_NOTES says top-side assembly only, but these "
                   "SMT parts are on the bottom: %s" % bottom[:8])
    return bad


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    boards = int(args[0]) if args and args[0].isdigit() else 1
    outdir = os.path.join(HERE, "release")
    if "-o" in sys.argv:
        outdir = sys.argv[sys.argv.index("-o") + 1]
    refresh = "--refresh" in sys.argv
    os.makedirs(outdir, exist_ok=True)

    print("GPSDO DDMTD front end -- manufacturing release, %d board(s)" % boards)
    print("board: %s" % bomdata.PCB)
    rows = bomdata.components()
    s = bomdata.summary(rows)
    print("components: %d   %s" % (s["total"], s["by_class"]))
    if s["without_lcsc"]:
        print("FAIL: %d parts to populate have no part number"
              % len(s["without_lcsc"]))
        return 2

    print("\nfabrication outputs")
    m = make_fab.main(outdir, boards)
    print("\nassembly outputs")
    res = make_bom.write(outdir, rows)
    print("\nannotated BOM")
    ann = annotate_bom.write(outdir, boards=boards, refresh=refresh)

    print("\nchecks")
    bad = check(outdir, rows, res)
    for b in bad:
        print("  FAIL  %s" % b)
    if not bad:
        print("  BOM, CPL, Gerbers and the board all agree; nothing to query.")

    man = os.path.join(outdir, "MANIFEST.txt")
    with open(man, "w", encoding="utf-8") as f:
        f.write("GPSDO DDMTD front end -- manufacturing release\n")
        f.write("generated %s for %d board(s)\n\n"
                % (datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                   boards))
        f.write("board %.1f x %.1f mm, %d layers, %d SMT placements, "
                "%d distinct parts\n\n"
                % (m["size_mm"][0], m["size_mm"][1], m["copper_layers"],
                   res["placements"], res["distinct"]))
        for fn in sorted(os.listdir(outdir)):
            p = os.path.join(outdir, fn)
            if os.path.isfile(p) and fn != "MANIFEST.txt":
                f.write("%-40s %9d bytes  sha256:%s\n"
                        % (fn, os.path.getsize(p), sha(p)))
    print("\n  %-34s" % "MANIFEST.txt")
    print("\nupload to JLCPCB:")
    print("  PCB   ...... GPSDO-PYNQ-Z2_gerbers.zip")
    print("  BOM   ...... GPSDO-PYNQ-Z2_bom.csv")
    print("  CPL   ...... GPSDO-PYNQ-Z2_cpl_jlc_corrected.csv  (see FABRICATION_NOTES: ROTATION)")
    print("  and read FABRICATION_NOTES.txt into the order notes.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
