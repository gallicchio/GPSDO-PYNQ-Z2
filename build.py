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
    "mfg/release", "mfg/_netlist.net", "fp-info-cache",
]
# ...and this is what is NOT a product, listed so the distinction is explicit.
SOURCES = ["gen/*.py", "pcb/*.py", "mfg/*.py (except release/)", "build.py",
           "datasheets/", "mechanical/", NAME + ".kicad_prl (KiCad's own UI state)"]


def cli():
    for c in (os.environ.get("KICAD_CLI"),
              os.path.expanduser("~/.local/kicad9/AppDir/AppRun")):
        if c and os.path.exists(c):
            return [c, "kicad-cli"] if c.endswith("AppRun") else [c]
    return ["kicad-cli"]


class Step:
    def __init__(self, n):
        self.n, self.t0 = n, time.time()
        print("\n=== %s" % n, flush=True)

    def done(self, msg=""):
        print("    [%5.1fs] %s" % (time.time() - self.t0, msg), flush=True)


def run(args, **kw):
    r = subprocess.run(args, capture_output=True, text=True, cwd=ROOT, **kw)
    if r.returncode:
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

    s = Step("1/6  schematic, project file and local footprints  <- gen/")
    out = run([sys.executable, "gen/gen.py"])
    s.done(out.strip().replace("\n", "; "))

    s = Step("2/6  netlist and ERC  <- kicad-cli")
    run(cli() + ["sch", "export", "netlist", "-o", NETLIST, NAME + ".kicad_sch"])
    erc = run(cli() + ["sch", "erc", "--severity-error", "--exit-code-violations",
                       "-o", os.path.join(BUILD, "erc.rpt"), NAME + ".kicad_sch"])
    s.done("netlist written; ERC %s"
           % [l for l in erc.splitlines() if "violation" in l.lower()][0].strip())

    s = Step("3/6  schematic checks  <- gen/check*.py")
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

    s = Step("4/6  board  <- pcb/build_pcb.py   (this is the long one)")
    env = dict(os.environ, NLDIR=BUILD)
    os.rename(NETLIST, os.path.join(BUILD, "nl.net"))       # build_pcb expects nl.net
    o = run([sys.executable, "pcb/build_pcb.py"], env=env)
    os.rename(os.path.join(BUILD, "nl.net"), NETLIST)
    keep = [l for l in o.splitlines()
            if any(k in l for k in ("placed", "routed", "multi-terminal:",
                                    "courtyard", "bonded", "FAILED"))]
    s.done("\n    ".join(l.strip() for l in keep))

    if not a.no_drc:
        s = Step("5/6  DRC, unfilled and with the zones poured")
        pcb = os.path.join(ROOT, NAME + ".kicad_pcb")
        d1 = run(cli() + ["pcb", "drc", "--severity-error", "--format", "json",
                          "-o", os.path.join(BUILD, "drc.json"), pcb])
        filled = os.path.join(BUILD, "filled.kicad_pcb")
        # fill_zones needs pcbnew, so it runs under KiCad's own interpreter
        k = cli()
        fill_cmd = (k[:-1] + ["python3.11"] if k[0].endswith("AppRun")
                    else [sys.executable])
        run(fill_cmd + [os.path.join(ROOT, "mfg", "fill_zones.py"), pcb, filled])
        d2 = run(cli() + ["pcb", "drc", "--severity-error", "--format", "json",
                          "-o", os.path.join(BUILD, "drcf.json"), filled])

        def verdict(txt):
            return "; ".join(l.strip() for l in txt.splitlines()
                             if "violation" in l.lower() or "unconnected" in l.lower())
        # The unfilled pass is for CLEARANCES only.  Its unconnected count is
        # meaningless and large -- every ground pad on this board reaches the
        # plane through a pour, and unfilled there is no pour, so ~436 of them
        # report as unconnected.  The number that matters is the filled one.
        s.done("unfilled (clearances):     %s\n"
               "    filled (what counts):      %s\n"
               "    the unfilled unconnected count is expected: without the\n"
               "    pours, every ground pad looks unconnected."
               % (verdict(d1), verdict(d2)))

    if not a.no_release:
        s = Step("6/6  manufacturing release  <- mfg/")
        o = run([sys.executable, "mfg/build_release.py", str(a.boards)])
        keep = [l for l in o.splitlines()
                if any(k in l for k in ("parts $", "agree", "FAIL", "components:"))]
        s.done("\n    ".join(l.strip() for l in keep))

    print("\nBUILT in %.1f s" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
