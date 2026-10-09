"""Netlist sanity checks that ERC does not make.

Run after `kicad-cli sch export netlist --format kicadsexpr`.  These catch the
two mistakes this generator actually made, both of which ERC passes silently:

  * a two-terminal part with BOTH pins on the same net -- drawn as if it were
    there, doing nothing.  It happens when a wire's ENDPOINT lands on the part's
    other pin, so the wire shorts across the body.
  * a two-terminal part with only one pin on any net at all.
  * (round 21) a NAMED SIGNAL NET THAT HAS VANISHED, which is what happens when
    a power symbol's riser lands on a signal wire: the signal is absorbed into
    the rail, every pin that was on it is now on the rail, and ERC, the
    two-terminal checks and the power-path checks all pass.  The only symptom
    is that a net you expect by name is not in the netlist any more.
"""
import sys, os
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, kids, kid, val


def check(path):
    doc = parse(open(path, encoding="utf-8").read())[0]
    nets = kids(kid(doc, "nets"), "net")
    pins = defaultdict(dict)
    for n in nets:
        nm = val(kid(n, "name"))
        for nd in kids(n, "node"):
            pins[val(kid(nd, "ref"))][val(kid(nd, "pin"))] = nm
    bad = []
    for ref, p in sorted(pins.items()):
        if ref[0] not in "CRLD" or ref.startswith("#"):
            continue
        if len(p) == 2 and p.get("1") is not None and p.get("1") == p.get("2"):
            bad.append("%s shorted: both pins on %s" % (ref, p["1"]))
        elif ref[0] in "CRL" and len(p) == 1:
            bad.append("%s half connected: %s" % (ref, p))
    rails = {val(kid(n, "name")): len(kids(n, "node")) for n in nets}
    for a, b in (("+3V3_A", "GND"), ("+3V3_D", "GND"), ("+3V3_A", "+3V3_D"),
                 ("+5V_HDR", "+3V3_A"), ("+15V_HTR", "GND")):
        if a not in rails or b not in rails:
            bad.append("rail %s or %s has vanished -- probably merged into another net" % (a, b))
    print("%d components, %d nets" % (len(kids(kid(doc, "components"), "comp")), len(nets)))
    for k in sorted(rails):
        if k.startswith(("+", "GND")):
            print("   %-10s %4d nodes" % (k, rails[k]))
    if bad:
        print("\nFAIL:")
        for m in bad:
            print("   " + m)
        return 1
    # ---- round 21: every net the design names must still exist ----------
    import design as D
    required = {"GND", "+3V3_A", "+3V3_D", "+5V_HDR", "+15V_HTR",
                "I2C_SCL", "I2C_SDA", "ONEWIRE", "HTR_DRIVE",
                "HELPER_CLK", "HELPER_SRC"}     # rev B: SI_XA/SI_XB gone (XA, XB float)
    for u in D.UNITS:
        required.add(u[1])
        if u[2]:
            required.add(u[2])
    have = {val(kid(n, "name")) for n in nets}
    missing = sorted(required - have)
    if missing:
        print("\nFAIL: named nets that no longer exist in the netlist:")
        for m in missing:
            print("   %s  -- absorbed into another net?  Look for a power symbol "
                  "or label landing on its wire." % m)
        return 1
    print("\nOK: no shorted or half-connected two-terminal parts; all rails distinct;")
    print("    all %d named nets present." % len(required))
    return 0


if __name__ == "__main__":
    sys.exit(check(sys.argv[1]))
