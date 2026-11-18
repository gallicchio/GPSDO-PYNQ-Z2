#!/usr/bin/env python3
"""Validate a generated .kicad_sch: do symbol pins actually land on wires?

Reads the file back with no knowledge of how it was written, resolves every
placed symbol's pins from the embedded lib_symbols, and reports pins that do not
coincide with a wire endpoint, a junction, or a label anchor.  This is the check
that catches a schematic which looks right and netlists wrong.
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, head, kids, kid, val, num


def pins_of(libsym):
    out = []
    for sub in kids(libsym, "symbol"):
        for p in kids(sub, "pin"):
            at = kid(p, "at")
            out.append((val(kid(p, "number")), num(at, 1), num(at, 2)))
    return out


def check(path, sign=-1, verbose=True):
    doc = parse(open(path, encoding="utf-8").read())[0]
    libs = {val(s): s for s in kids(kid(doc, "lib_symbols"), "symbol")}
    pts = set()
    for w in kids(doc, "wire"):
        for xy in kids(kid(w, "pts"), "xy"):
            pts.add((round(num(xy, 1), 2), round(num(xy, 2), 2)))
    for j in kids(doc, "junction"):
        at = kid(j, "at"); pts.add((round(num(at, 1), 2), round(num(at, 2), 2)))
    for t in ("label", "global_label", "hierarchical_label", "no_connect"):
        for l in kids(doc, t):
            at = kid(l, "at"); pts.add((round(num(at, 1), 2), round(num(at, 2), 2)))
    bad, tot = [], 0
    for sym in kids(doc, "symbol"):
        lid = val(kid(sym, "lib_id"))
        if lid not in libs:
            continue
        at = kid(sym, "at"); X, Y, R = num(at, 1), num(at, 2), num(at, 3)
        mir = kid(sym, "mirror"); m = val(mir) if mir else None
        ref = "?"
        for pr in kids(sym, "property"):
            if val(pr) == "Reference":
                ref = val(pr, 2)
        for num_, px, py in pins_of(libs[lid]):
            tot += 1
            qx, qy = px, py
            if m == "y":
                qx = -qx
            elif m == "x":
                qy = -qy
            a = math.radians(sign * R)
            x = X + qx * math.cos(a) + qy * math.sin(a)
            y = Y + qx * math.sin(a) - qy * math.cos(a)
            if (round(x, 2), round(y, 2)) not in pts:
                bad.append((ref, num_, lid, R, m, round(x, 2), round(y, 2)))
    if verbose:
        print("%s: %d pins, %d not on a wire/junction/label" % (os.path.basename(path), tot, len(bad)))
        for b in bad[:20]:
            print("   %-12s pin %-3s %-28s rot=%-4g mir=%-4s -> (%.2f, %.2f)" % b)
    return len(bad), tot


if __name__ == "__main__":
    for f in sys.argv[1:]:
        check(f)
