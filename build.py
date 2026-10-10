#!/usr/bin/env python3
"""Build the whole project from source, in one command.

    python3 build.py                 everything: schematic, checks, board, release
    python3 build.py --clean         delete every generated file first
    python3 build.py --no-pcb        stop before the router (the 40-minute part)
    python3 build.py --no-release    stop before the manufacturing outputs
    python3 build.py --boards 5      how many boards the release is priced for (default 1)
    python3 build.py --list          print what is source and what is product

Nothing in this repository is hand-edited downstream of a generator.  The
schematic, the project file, the local footprints, the board and the whole
manufacturing release are products; delete all of them and this rebuilds them.
The only things you cannot delete are the Python under gen/, pcb/ and mfg/,
the datasheets, and the notes.

HOW REPRODUCIBLE, EXACTLY.  Round 30 ran `--clean` against a committed tree
and diffed everything, because round 29 had just found the DRC checking a
different file from the one being shipped and the claim deserved a number:

  * the schematic, the project file, the BOM, both CPL files and
    FABRICATION_NOTES.txt come back **byte-identical**;
  * `pcb/build_pcb.py` is deterministic -- run it twice and the boards are
    byte-identical;
  * the **gerbers and the drill file** are byte-identical apart from the
    creation-date line each one carries;
  * the shipped `.kicad_pcb` differs, and ONLY in `(uuid ...)` lines -- 7760
    of them, with not one geometric change.  Those come from pcbnew, which
    assigns fresh uuids as it pours the zones in step 5.  The proof that this
    is cosmetic is the gerbers: identical output from a "different" file.
  * `annotated_bom.*` and MANIFEST.txt legitimately differ -- they carry the
    time of their own JLCPCB price query.

So: reproducible in everything a fab is sent, and in everything a human
reads; not bit-for-bit in the board file itself, because pcbnew touches it
last.  Do not go looking for a bug in that diff -- check it is all uuids.
"""
import argparse, os, shutil, subprocess, sys, time, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "GPSDO-PYNQ-Z2"
BUILD = os.path.join(ROOT, "build")
NETLIST = os.path.join(BUILD, "netlist.net")

# Everything below is REGENERATED.  --clean removes exactly this list.
PRODUCTS = [
    "*.kicad_sch", NAME + ".kicad_pcb", NAME + ".kicad_pro",
    "sym-lib-table", "fp-lib-table", "library", "build",
    "mfg/release", "mfg/_netlist.net", "fp-info-cache", "HANDBOOK.md",
]
# ...and this is what is NOT a product, listed so the distinction is explicit.
SOURCES = ["gen/*.py", "pcb/*.py", "mfg/*.py (except release/)", "build.py",
           "datasheets/", "mechanical/", NAME + ".kicad_prl (KiCad's own UI state)"]


sys.path.insert(0, os.path.join(ROOT, "gen"))
import kicad_env                                   # noqa: E402  KiCad 10 (REVB item 14)


def cli():
    return kicad_env.kicad_cli()


class Step:
    def __init__(self, n):
        self.n, self.t0 = n, time.time()
        print("\n=== %s" % n, flush=True)

    def done(self, msg=""):
        print("    [%5.1fs] %s" % (time.time() - self.t0, msg), flush=True)


def run(args, ok=(0,), **kw):
    r = subprocess.run(args, capture_output=True, text=True, cwd=ROOT, **kw)
    if r.returncode not in ok:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("FAILED: %s" % " ".join(str(a) for a in args[:4]))
    return r.stdout + r.stderr


def clean():
    n = 0
    for pat in PRODUCTS:
        for p in glob.glob(os.path.join(ROOT, pat)):
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            n += 1
    print("removed %d generated paths" % n)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--no-pcb", action="store_true")
    ap.add_argument("--no-release", action="store_true")
    ap.add_argument("--no-drc", action="store_true")
    ap.add_argument("--boards", type=int, default=1)     # round 28: one first
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        print("SOURCES (never generated):")
        for s in SOURCES:
            print("   ", s)
        print("\nPRODUCTS (--clean deletes these):")
        for s in PRODUCTS:
            print("   ", s)
        return 0

    t0 = time.time()
    if a.clean:
        clean()
    os.makedirs(BUILD, exist_ok=True)

    s = Step("1/7  schematic, project file and local footprints  <- gen/")
    out = run([sys.executable, "gen/gen.py"])
    # REVB item 14: save every sheet in KiCad 10's own format, so that opening
    # the project in KiCad 10 rewrites nothing (the generator writes the
    # KiCad 9 dialect it was written against; KiCad converts it losslessly).
    for sch in sorted(glob.glob(os.path.join(ROOT, "*.kicad_sch"))):
        run(cli() + ["sch", "upgrade", sch])
    s.done(out.strip().replace("\n", "; ") + "; sheets saved in KiCad 10's format")

    s = Step("2/7  netlist and ERC  <- kicad-cli")
    run(cli() + ["sch", "export", "netlist", "-o", NETLIST, NAME + ".kicad_sch"])
    erc = run(cli() + ["sch", "erc", "--severity-error", "--exit-code-violations",
                       "-o", os.path.join(BUILD, "erc.rpt"), NAME + ".kicad_sch"])
    s.done("netlist written; ERC %s"
           % [l for l in erc.splitlines() if "violation" in l.lower()][0].strip())

    s = Step("3/7  schematic checks  <- gen/check*.py")
    msgs = []
    for script, args in (("gen/check.py", sorted(glob.glob(os.path.join(ROOT, "*.kicad_sch")))),
                         ("gen/check_netlist.py", [NETLIST]),
                         ("gen/check_paths.py", [NETLIST]),
                         ("gen/check_overlap.py", [])):
        o = run([sys.executable, script] + args)
        tail = [l for l in o.strip().splitlines() if l.strip()][-1]
        msgs.append("%-22s %s" % (os.path.basename(script), tail.strip()[:70]))
    s.done("\n    ".join(msgs))

    if a.no_pcb:
        print("\nstopping before the board (--no-pcb).  %.1fs" % (time.time() - t0))
        return 0

    s = Step("4/7  board  <- pcb/build_pcb.py   (this is the long one)")
    env = dict(os.environ, NLDIR=BUILD)
    os.rename(NETLIST, os.path.join(BUILD, "nl.net"))       # build_pcb expects nl.net
    o = run([sys.executable, "pcb/build_pcb.py"], env=env)
    os.rename(os.path.join(BUILD, "nl.net"), NETLIST)
    keep = [l for l in o.splitlines()
            if any(k in l for k in ("placed", "routed", "multi-terminal:",
                                    "courtyard", "bonded", "FAILED",
                                    "silkscreen:", "silkscreen boxes:",
                                    "look split", "SILK:",
                                    "two-point pass left", "dropped",
                                    "late hand route"))]
    # Round 41: every unit-tile part and designator inside its own silkscreen
    # box, checked again on the file actually written (build_pcb.py already
    # refuses to write one that fails; this reads it back independently).
    keep.append(run([sys.executable, "pcb/check_silk_boxes.py",
                     os.path.join(ROOT, NAME + ".kicad_pcb")]).strip().splitlines()[-1])
    # Rev B (2026-10-10): EVERY text on F.SilkS, owned or not, against the
    # unit boxes, with KiCad's own text boxes.  The in-tile heaters had no
    # home, so the check above never saw their designators land in the next
    # unit's box.  `python3 pcb/check_unit_labels.py --stamps DIR` draws it.
    o = run(kicad_env.kicad_python() + ["pcb/check_unit_labels.py",
                                        os.path.join(ROOT, NAME + ".kicad_pcb")], ok=(0, 1))
    keep += [l for l in o.splitlines() if l.startswith(("unit labels:", "UNIT LABEL:"))]
    s.done("\n    ".join(l.strip() for l in keep))
    if any(l.startswith("UNIT LABEL:") for l in keep):
        raise SystemExit("FAILED: silkscreen in the wrong unit's box")

    if not a.no_drc:
        s = Step("5/7  DRC, and the zones poured INTO the board")
        pcb = os.path.join(ROOT, NAME + ".kicad_pcb")
        pro = os.path.join(ROOT, NAME + ".kicad_pro")
        # ROUND 29.  The pours used to be written into a COPY, build/filled,
        # and the board this repository ships kept its zones unfilled -- so
        # opening it showed a board with no ground plane and a ratsnest of
        # several hundred ground connections, and the only thing that ever saw
        # the poured version was this DRC.  Fill the real board; keep the
        # unfilled one in build/ for the clearance-only pass, with a copy of
        # the project file beside it so it is checked against OUR rules and
        # not KiCad's defaults.
        unf = os.path.join(BUILD, "unfilled.kicad_pcb")
        shutil.copyfile(pcb, unf)
        shutil.copyfile(pro, os.path.join(BUILD, "unfilled.kicad_pro"))
        d1 = run(cli() + ["pcb", "drc", "--severity-error", "--format", "json",
                          "-o", os.path.join(BUILD, "drc.json"), unf])
        filled = os.path.join(BUILD, "filled.kicad_pcb")
        # fill_zones needs pcbnew, so it runs under KiCad's own interpreter
        fill_cmd = kicad_env.kicad_python()
        run(fill_cmd + [os.path.join(ROOT, "mfg", "fill_zones.py"), pcb, filled])
        shutil.copyfile(filled, pcb)
        d2 = run(cli() + ["pcb", "drc", "--severity-error", "--format", "json",
                          "-o", os.path.join(BUILD, "drcf.json"), pcb])
        # ...and once more at FULL severity.  Round 28 reported "0 violations"
        # from a --severity-error pass over a board carrying 639 warnings, 199
        # of them reference designators below the minimum printable height and
        # 199 of them silkscreen landing on solder-mask openings.  gen/jlc.py
        # promotes the ones that matter to errors; this prints what is left,
        # so that a warning has to be looked at rather than not asked about.
        run(cli() + ["pcb", "drc", "--severity-all", "--format", "json",
                     "-o", os.path.join(BUILD, "drc-all.json"), pcb])
        import json as _json
        allv = _json.load(open(os.path.join(BUILD, "drc-all.json")))["violations"]
        byt = {}
        for v in allv:
            byt[(v["severity"], v["type"])] = byt.get((v["severity"], v["type"]), 0) + 1
        rest = ", ".join("%s %s x%d" % (k[0], k[1], n)
                         for k, n in sorted(byt.items(), key=lambda kv: -kv[1]))

        def verdict(txt):
            return "; ".join(l.strip() for l in txt.splitlines()
                             if "violation" in l.lower() or "unconnected" in l.lower())
        # The unfilled pass is for CLEARANCES only.  Its unconnected count is
        # meaningless and large -- every ground pad on this board reaches the
        # plane through a pour, and unfilled there is no pour, so ~436 of them
        # report as unconnected.  The number that matters is the filled one.
        # A board with an unconnected net has no business producing a
        # manufacturing release.  Round 28's build could not tell: the DRC
        # step printed its verdict and carried on regardless, because
        # kicad-cli only sets an exit code when asked.  Round 29's second
        # build shipped one unconnected I2C_SDA past this point and the only
        # sign was a line of text in the middle of the log.
        drcf = _json.load(open(os.path.join(BUILD, "drcf.json")))
        nbad = len(drcf["violations"]) + len(drcf.get("unconnected_items", []))
        if nbad:
            for v in (drcf["violations"] + drcf.get("unconnected_items", []))[:10]:
                print("    DRC  %s: %s" % (v["type"], v["description"]))
                for it in v.get("items", [])[:2]:
                    print("         %s @ (%.2f, %.2f)"
                          % (it["description"], it["pos"]["x"], it["pos"]["y"]))
            raise SystemExit("FAILED: the poured board has %d DRC error(s); "
                             "no release was built" % nbad)
        s.done("unfilled (clearances):     %s\n"
               "    the board, poured:         %s\n"
               "    everything, all severities: %s\n"
               "    (KiCad reports at most 199 of any one type)"
               % (verdict(d1), verdict(d2), rest or "nothing at all"))

    if not a.no_release:
        s = Step("6/7  manufacturing release  <- mfg/")
        # exit 3: a DRAFT -- the files agree but the revision is not dated
        # yet (round 42: rev B until it is ordered), so carry on to step 7
        o = run([sys.executable, "mfg/build_release.py", str(a.boards)], ok=(0, 3))
        keep = [l for l in o.splitlines()
                if any(k in l for k in ("parts $", "agree", "FAIL", "DRAFT",
                                        "components:"))]
        s.done("\n    ".join(l.strip() for l in keep))

    s = Step("7/7  HANDBOOK.md  <- gen/handbook.py")
    s.done(run([sys.executable, "gen/handbook.py"]).strip())

    print("\nBUILT in %.1f s" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
