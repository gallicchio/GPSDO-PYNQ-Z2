#!/usr/bin/env python3
"""Build everything JLCPCB needs, then check it against itself.

    python3 mfg/build_release.py [N_BOARDS] [--refresh] [-o DIR]

Generating the files is the easy half.  The half that stops the fab coming
back with questions is checking that the files AGREE: that no do-not-populate
part leaked into the placement file, that every designator in the BOM is also
in the CPL, that the Gerber set is complete, and that the board the Gerbers
came from is the same board the BOM was read from.  All of that is asserted
here, and a non-zero exit means do not upload.

Exit 3 is a DRAFT: the files agree, but the revision has no order date yet
(gen/design.py DATE), so it is not the thing to upload.  build.py accepts it.
"""
import os, re, sys, zipfile, csv, subprocess, datetime, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "gen"))
import bomdata, make_bom, make_fab, annotate_bom       # noqa: E402
import design as D                                     # noqa: E402

DRAFT = 3

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
    # rev B: the through-hole parts are assembled too (make_bom.py), and
    # since 2026-10-10 the bottom socket J4001 as well
    smt = {r["ref"] for r in rows if r["cls"] in ("smt", "tht")}
    dnp = {r["ref"] for r in rows if r["cls"] == "dnp"}
    nop = {r["ref"] for r in rows if r["cls"] == "nopart"}

    bom_refs, cpl_refs = set(), set()
    seen_lcsc = {}
    with open(res["bom"], encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bom_refs |= {d.strip() for d in row["Designator"].split(",") if d.strip()}
            code = row["LCSC"].strip()
            if not code:
                bad.append("BOM line %r has no LCSC code" % row["Comment"])
            elif code in seen_lcsc:
                # ROUND 32.  JLCPCB matches a BOM line to a part by its code,
                # so the same code on two lines is "Multiple lines in the BOM
                # have been matched to the same part": it zeroes both
                # quantities and waits for someone to tick two boxes.  This
                # shipped once, as C17738 on a `51R 1%` line and a `51R` line.
                bad.append("BOM has LCSC %s on two lines (%r and %r) -- "
                           "JLCPCB will match both to the same part, zero "
                           "both quantities and ask a human to sort it out"
                           % (code, seen_lcsc[code], row["Comment"]))
            else:
                seen_lcsc[code] = row["Comment"]
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

    # ROUND 42.  A dated revision must be the board that prints that
    # revision and date; one set in gen/design.py after the board was last
    # built would ship the old silkscreen.
    if not undated():
        pcb = open(bomdata.PCB, encoding="utf-8").read()
        for what, pat in (("rev %s" % D.REV, r"\brev %s" % re.escape(D.REV)),
                          (D.DATE, re.escape(D.DATE))):
            if not re.search(r'gr_text "[^"]*%s"' % pat, pcb):
                bad.append("the board's silkscreen does not print %r: it was "
                           "built before gen/design.py said so; rebuild it" % what)
    return bad


def placement_checks(outdir, rows):
    """Rev B: JLCPCB's own land pattern of every assembled code, fitted to the
    board (footprint_check.py, from ECP5), and the CPL's correction against
    the fit's prediction.  Writes PLACEMENT_CHECKS.txt; returns failures.

    A failure is a part that does not fit (a hole the board lacks, pads that
    miss by more than LAND_WARN), or a per-part correction in parts_map.py
    that disagrees with what the fit predicts.  CLAUDE_PCB.md section 8."""
    import collections
    import footprint_check as FC
    import parts_map
    fps, drills = FC.read_board(bomdata.PCB)
    by_ref = {f["ref"]: f for f in fps}
    placed = [r for r in rows if r["cls"] in ("smt", "tht")]
    groups = collections.defaultdict(list)
    for r in placed:
        groups[(r["lcsc"], r["fpshort"], r["side"])].append(r["ref"])
    lines, bad = [], []
    lines.append("PLACEMENT CHECKS -- rev %s, %s" % (D.REV, D.DATE))
    lines.append("JLCPCB's land pattern of each code, fitted to our pads by pin number.")
    lines.append("'predicted' is the CPL correction the fit implies (minus its turn);")
    lines.append("'CPL' is what the upload file applies.  Read every PREDICTED row in")
    lines.append("JLCPCB's placement preview: pin 1 where 'look' says.  Nothing is on the")
    lines.append("back but J4001, the through-hole socket, which is in the CPL as Bottom.")
    lines.append("")
    lines.append("%-9s %-34s %4s %5s %5s  %-9s %s" % ("code", "footprint", "n", "pred", "CPL", "status", "refs / look"))
    for (code, fp, side), refs in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        f = by_ref.get(refs[0])
        if f is None:
            bad.append("%s: not on the board" % refs[0]); continue
        if fp in parts_map.JLC_ROTATION_NA:
            continue
        try:
            probs, lp, ts = FC.check(code, [by_ref[r] for r in refs if r in by_ref], drills)
        except Exception as e:          # no land pattern published, or offline
            lines.append("%-9s %-34s %4d %5s %5s  %-9s %s" % (code, fp[:34], len(refs), "?", "?", "NO FIT", e))
            continue
        fit = FC.FITS.get((code, side == "bottom"), {})
        pred = (-int(fit.get("deg", 0))) % 360
        e = parts_map.JLC_ROTATION_BY_PART.get(code) or parts_map.JLC_ROTATION.get(fp)
        cpl = (e[0] % 360) if e else 0
        how = ("read" if code not in parts_map.JLC_ROTATION_BY_PART and fp in parts_map.JLC_ROTATION
               else "PREDICTED" if code in parts_map.JLC_ROTATION_BY_PART else "none")
        hard = [p for p in probs if p[0] in ("HOLE", "LAND", "PADS")]
        status = how
        if hard:
            status = "FAIL"
            bad.append("%s (%s): %s" % (code, refs[0], "; ".join("%s %s" % p for p in hard)))
        elif how == "PREDICTED" and pred != cpl:
            status = "DISAGREES"
            bad.append("%s (%s): parts_map gives %d, the fit predicts %d" % (code, refs[0], cpl, pred))
        elif how == "read" and pred != cpl:
            status = "read/fit"     # a preview reading wins; say they differ
        look = (parts_map.JLC_ROTATION_BY_PART.get(code) or (0, "", ""))[2] or (e[2] if e else "")
        lines.append("%-9s %-34s %4d %5d %5d  %-9s %s%s" % (
            code, fp[:34], len(refs), pred, cpl, status,
            ",".join(sorted(refs, key=lambda x: (len(x), x))[:6]) + ("..." if len(refs) > 6 else ""),
            ("  -- " + look) if look else ""))
        for p in probs:
            if p[0] not in ("HOLE", "LAND", "PADS"):
                lines.append("          %s: %s" % p)
    with open(os.path.join(outdir, "PLACEMENT_CHECKS.txt"), "w", encoding="utf-8") as fo:
        fo.write("\n".join(lines) + "\n")
    return bad


def undated():
    """Why this revision is not yet for upload, or '' if it is.

    Round 42: rev A is locked (git tag GPSDO-PYNQ-Z2-revA) and the work since
    is rev B, which is locked on the day it is ordered, by giving it that
    date.  Until then a release is a draft, however well its files agree."""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", D.DATE):
        return ""
    return ("rev %s is not dated (gen/design.py DATE = %r); set DATE to the "
            "order date, rebuild, and it becomes uploadable" % (D.REV, D.DATE))


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
    bad += placement_checks(outdir, rows)
    print("  %-34s written" % "PLACEMENT_CHECKS.txt")
    draft = undated()
    for b in bad:
        print("  FAIL  %s" % b)
    if not bad:
        print("  BOM, CPL, Gerbers and the board all agree; nothing to query.")
    if draft:
        print("  DRAFT  %s" % draft)

    man = os.path.join(outdir, "MANIFEST.txt")
    with open(man, "w", encoding="utf-8") as f:
        if draft:
            f.write("DRAFT -- NOT FOR UPLOAD: %s\n\n" % draft)
        f.write("GPSDO DDMTD front end -- manufacturing release, rev %s, %s\n"
                % (D.REV, D.DATE))
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
    print("  CPL   ...... GPSDO-PYNQ-Z2_cpl_jlcpcb_upload.csv  (see FABRICATION_NOTES: ROTATION)")
    print("  and read FABRICATION_NOTES.txt into the order notes.")
    if draft and not bad:
        print("\nDRAFT: do not upload this one -- rev %s is not dated yet." % D.REV)
    return 1 if bad else (DRAFT if draft else 0)


if __name__ == "__main__":
    sys.exit(main())
