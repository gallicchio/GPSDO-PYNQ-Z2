#!/usr/bin/env python3
"""Join what the schematic knows to what the board knows, once, for everybody.

The two halves of a BOM live in different files and neither alone is enough:

  * the SCHEMATIC has the value, the LCSC code and the DNP flag,
  * the BOARD has the position, the rotation, the side and whether the
    footprint is surface mount or through hole.

They are joined on the reference designator.  Everything downstream -- the
JLCPCB BOM, the CPL, the annotated BOM -- reads this module so that all three
agree by construction.  Round 23 found that the PCB footprints carry NO LCSC
codes and NO DNP flags at all (KiCad does not push either into the board), so
a tool that read only the .kicad_pcb would have shipped 27 do-not-populate
parts and no part numbers.

Each component comes back classified:

  smt    surface mount, to be populated, has a part number  -> JLCPCB assembles
  tht    through hole, to be populated                      -> JLCPCB assembles
                                                               too (rev B), either side
  dnp    marked do-not-populate in the schematic            -> excluded
  nopart a bare pad (test points)                           -> excluded
"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "gen"))
sys.path.insert(0, HERE)
from sexp import parse, kids, kid, val          # noqa: E402
import parts_map                                # noqa: E402

PCB = os.path.join(ROOT, "GPSDO-PYNQ-Z2.kicad_pcb")
SCH = os.path.join(ROOT, "GPSDO-PYNQ-Z2.kicad_sch")


def _kicad_cli():
    """The kicad-cli this project builds with, wherever it lives."""
    sys.path.insert(0, os.path.join(ROOT, "gen"))
    import kicad_env
    return kicad_env.kicad_cli()                    # KiCad 10 (REVB item 14)


def netlist(path=None, regenerate=True):
    """Export and parse the netlist.  Cheap enough to do every time."""
    out = path or os.path.join(HERE, "_netlist.net")
    if regenerate or not os.path.exists(out):
        subprocess.run(_kicad_cli() + ["sch", "export", "netlist",
                                       "-o", out, SCH],
                       check=True, capture_output=True)
    return parse(open(out, encoding="utf-8").read())[0]


def from_schematic():
    """ref -> {value, footprint, lcsc, dnp}"""
    doc = netlist()
    out = {}
    for c in kids(kid(doc, "components"), "comp"):
        ref = val(kid(c, "ref"))
        props = {val(p[1]): (val(p[2]) if len(p) > 2 else "")
                 for p in kids(c, "property")}
        fp = val(kid(c, "footprint")) if kid(c, "footprint") else ""
        out[ref] = dict(value=val(kid(c, "value")),
                        footprint=fp,
                        fpshort=fp.split(":")[-1],
                        lcsc=props.get("LCSC", ""),
                        dnp="dnp" in props)
    return out


_PAD_RE = re.compile(r'\(footprint\s+"([^"]+)"')


def from_board():
    """ref -> {x, y, rot, side, smd, tht}  straight out of the .kicad_pcb.

    Read with the s-expression parser rather than pcbnew so that the release
    tooling does not need KiCad's Python bindings on the PATH.
    """
    doc = parse(open(PCB, encoding="utf-8").read())[0]
    out = {}
    for f in kids(doc, "footprint"):
        ref = None
        for pr in kids(f, "property"):
            if val(pr[1]) == "Reference":
                ref = val(pr[2])
        if not ref:
            continue
        at = kid(f, "at")
        x, y = float(val(at[1])), float(val(at[2]))
        rot = float(val(at[3])) if len(at) > 3 else 0.0
        layer = val(kid(f, "layer"))
        attrs = [val(a) for a in (kid(f, "attr") or [])[1:]]
        out[ref] = dict(x=x, y=y, rot=rot,
                        side="bottom" if layer.startswith("B.") else "top",
                        smd="smd" in attrs,
                        tht="through_hole" in attrs,
                        # plated holes JLCPCB solders: their per-pin THT fee
                        thpins=sum(1 for p in kids(f, "pad")
                                   if len(p) > 2 and val(p[2]) == "thru_hole"),
                        smdpads=sum(1 for p in kids(f, "pad")
                                    if len(p) > 2 and val(p[2]) == "smd"),
                        name=val(f[1]))
    return out


def board_box():
    """(min_x, min_y, max_x, max_y) of Edge.Cuts, for CPL origin conversion."""
    doc = parse(open(PCB, encoding="utf-8").read())[0]
    xs, ys = [], []
    for k in ("gr_line", "gr_rect", "gr_arc", "gr_circle"):
        for g in kids(doc, k):
            if not kid(g, "layer") or val(kid(g, "layer")) != "Edge.Cuts":
                continue
            for tag in ("start", "end", "center", "mid"):
                n = kid(g, tag)
                if n:
                    xs.append(float(val(n[1]))); ys.append(float(val(n[2])))
    if not xs:
        raise RuntimeError("no Edge.Cuts geometry found in %s" % PCB)
    return min(xs), min(ys), max(xs), max(ys)


def components():
    """Every component, joined and classified.  Sorted by reference."""
    sch, brd = from_schematic(), from_board()
    missing = sorted(set(sch) - set(brd))
    if missing:
        raise RuntimeError("in the schematic but not on the board: %s" % missing)
    rows = []
    for ref, s in sch.items():
        b = brd[ref]
        lcsc = s["lcsc"]
        why = ""
        if not lcsc:
            got = parts_map.MAP.get((s["value"], s["fpshort"]))
            if got:
                lcsc, why = got
        if s["fpshort"] in parts_map.NO_PART:
            cls = "nopart"
        elif s["dnp"]:
            cls = "dnp"
        elif b["tht"]:
            cls = "tht"
        else:
            cls = "smt"
        row = dict(s); row.update(b)
        row.update(ref=ref, cls=cls, lcsc=lcsc, why=why)
        rows.append(row)
    rows.sort(key=lambda r: (re.sub(r"\d", "", r["ref"]),
                            int(re.sub(r"\D", "", r["ref"]) or 0)))
    return rows


def summary(rows=None):
    rows = rows or components()
    from collections import Counter
    c = Counter(r["cls"] for r in rows)
    noc = [r for r in rows if r["cls"] in ("smt", "tht") and not r["lcsc"]]
    return dict(total=len(rows), by_class=dict(c), without_lcsc=noc)


if __name__ == "__main__":
    rows = components()
    s = summary(rows)
    print("components: %d   %s" % (s["total"], s["by_class"]))
    if s["without_lcsc"]:
        print("\nTO BE POPULATED BUT WITH NO PART NUMBER (%d):"
              % len(s["without_lcsc"]))
        from collections import defaultdict
        g = defaultdict(list)
        for r in s["without_lcsc"]:
            g[(r["value"], r["fpshort"], r["cls"])].append(r["ref"])
        for (v, fp, cls), refs in sorted(g.items()):
            print("   %-4s %-22s %-40s n=%-3d %s"
                  % (cls, v, fp, len(refs), refs[0]))
    else:
        print("\nevery part to be populated has an LCSC part number.")
