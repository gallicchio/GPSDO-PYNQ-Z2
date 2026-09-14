#!/usr/bin/env python3
"""Propose LCSC codes for the parts that do not carry one yet.

This is a REVIEW aid, not an oracle.  It searches JLCPCB for each specification
and prints the candidates Basic-first, because a Basic part carries no per-part
setup fee and an Extended one costs about $3 whatever the placement count.  A
human picks from the list; the choice then lives in parts_map.py with the
reason written down.

Usage:  python3 mfg/pick_parts.py            # show candidates for everything
        python3 mfg/pick_parts.py 0805 560R  # one ad-hoc query
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jlc_api

# (label, search keyword, required package, qty on this board, what it must be)
WANTED = [
    ("100n 0805",       "100nF 0805 X7R 50V",           "0805", 73,  "X7R, >=25 V"),
    ("10n 0805",        "10nF 0805 X7R 50V",            "0805", 69,  "X7R, >=25 V"),
    ("10n C0G 0805",    "10nF 0805 C0G NP0 50V",        "0805", 14,  "C0G/NP0 -- front-end AC coupling"),
    ("10u 0805",        "10uF 0805 X5R 25V",            "0805", 3,   "X5R/X7R, >=16 V"),
    ("600R ferrite",    "0805 600R 100MHz ferrite bead","0805", 70,  ">=200 mA; FB2001 carries 110 mA"),
    ("560R 2010",       "2010 560R 1%",                 "2010", 24,  "MUST be >=0.75 W -- 400 mW each"),
    ("0R 0805",         "0805 0R jumper",               "0805", 14,  "link"),
    ("22R 0805",        "0805 22R 1%",                  "0805", 1,   ""),
    ("33R 0805",        "0805 33R 1%",                  "0805", 14,  "series damping"),
    ("47R 0805",        "0805 47R 1%",                  "0805", 5,   ""),
    ("47R 1206",        "1206 47R 1%",                  "1206", 5,   ""),
    ("51R 0805",        "0805 51R 1%",                  "0805", 13,  ""),
    ("51R 1% 0805",     "0805 51R 1%",                  "0805", 13,  "termination"),
    ("100R 0805",       "0805 100R 1%",                 "0805", 1,   ""),
    ("330R 0805",       "0805 330R 1%",                 "0805", 14,  "sets the squarer edge rate"),
    ("1k 0805",         "0805 1K 1%",                   "0805", 13,  ""),
    ("2k2 0805",        "0805 2.2K 1%",                 "0805", 13,  ""),
    ("3k3 0805",        "0805 3.3K 1%",                 "0805", 1,   ""),
    ("10k 0805",        "0805 10K 1%",                  "0805", 12,  ""),
    ("100k 0805",       "0805 100K 1%",                 "0805", 1,   ""),
    ("1M 1% 0805",      "0805 1M 1%",                   "0805", 14,  "self-bias -- 1% matters"),
    ("SMAJ18A",         "SMAJ18A",                      "SMA",  1,   "unidirectional TVS, 18 V standoff"),
    ("25MHz 3225",      "25MHz 3225 crystal",           "SMD3225_4P", 1, "DNP alternative"),
]


def show(label, kw, pkg, qty, note):
    try:
        lst, ts = jlc_api.search(kw, page_size=25)
    except Exception as e:
        print("  !! %s: %s" % (label, e)); return
    rows = []
    for it in lst:
        spec = (it.get("componentSpecificationEn") or "")
        if pkg and pkg.lower() not in spec.lower().replace("-", ""):
            if pkg.lower() != spec.lower():
                continue
        rows.append(it)
    rows.sort(key=lambda it: (jlc_api.library_type(it) == "Extended",
                              -(it.get("stockCount") or 0)))
    print("\n=== %-14s qty %-4d %s" % (label, qty, ("-- " + note) if note else ""))
    print("    (search %r, queried %s)" % (kw, ts))
    if not rows:
        print("    NO CANDIDATE IN PACKAGE %s -- widen the search" % pkg)
    for it in rows[:6]:
        p = jlc_api.unit_price(it, jlc_api.order_qty(it, qty))
        print("    %-11s %-9s %-26s stock %-9d $%.4f  %s" % (
            it["componentCode"], jlc_api.library_type(it),
            (it.get("componentModelEn") or "")[:26],
            it.get("stockCount") or 0, p,
            (it.get("describe") or "")[:52]))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        show("ad-hoc", " ".join(sys.argv[1:]), "", 1, "")
    else:
        for row in WANTED:
            show(*row)
