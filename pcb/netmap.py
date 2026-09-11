"""ref -> footprint, and ref -> {pad: net}, straight from the exported netlist."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "gen"))
from sexp import parse, kids, kid, val


def load(path):
    doc = parse(open(path, encoding="utf-8").read())[0]
    fps, vals = {}, {}
    for c in kids(kid(doc, "components"), "comp"):
        r = val(kid(c, "ref"))
        f = kid(c, "footprint")
        fps[r] = val(f) if f else ""
        vals[r] = val(kid(c, "value"))
    nets, num = {}, {}
    n = 0
    for net in kids(kid(doc, "nets"), "net"):
        nm = val(kid(net, "name"))
        n += 1
        num[nm] = n
        for nd in kids(net, "node"):
            nets.setdefault(val(kid(nd, "ref")), {})[val(kid(nd, "pin"))] = nm
    return fps, vals, nets, num
